"""Security regression suite — every checklist item has a failing-first test.

Covers: SQL injection, XSS, CSRF, file-upload validation, broken object-level
authorization (BOLA), rate limiting, JWT handling, MFA, CORS, server-side
permissions, row-level security, webhook signatures, SSRF, source maps,
default credentials, log redaction, and password hashing.
"""

from __future__ import annotations

import os
import secrets
import sys
import tempfile
from pathlib import Path

import pytest

# Environment must be configured BEFORE the app module is imported.
_TMP = tempfile.mkdtemp(prefix="signalpost-webapp-test-")
os.environ.setdefault("WEBAPP_DATA_DIR", _TMP)
os.environ["WEBAPP_SECURE_COOKIES"] = "0"
os.environ["JWT_SECRET"] = "test-jwt-secret-" + secrets.token_urlsafe(24)
os.environ["CSRF_PEPPER"] = "test-csrf-pepper-" + secrets.token_urlsafe(24)
os.environ["SESSION_SECRET"] = "test-session-secret-" + secrets.token_urlsafe(24)
os.environ["WEBHOOK_SECRET"] = "test-webhook-secret-" + secrets.token_urlsafe(24)
os.environ["CORS_ALLOW_ORIGINS"] = ""
os.environ.pop("ADMIN_BOOTSTRAP_PASSWORD", None)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from webapp import security  # noqa: E402
from webapp.app import app  # noqa: E402
from webapp.db import IdentityStore, validate_upload  # noqa: E402

client = TestClient(app, follow_redirects=False)


@pytest.fixture(autouse=True)
def _reset_limiter():
    security.limiter.reset()
    client.cookies.clear()  # isolate cookie state between tests
    yield
    security.limiter.reset()


def _sid_csrf(cookies: dict[str, str]) -> dict[str, str]:
    """Derive the expected CSRF token for a session id cookie."""
    sid = cookies.get("sp_sid", "")
    return {"csrf": security.csrf_token_for(sid)}


def _register(email: str, password: str = "Str0ngPassphrase!") -> dict[str, str]:
    resp = client.get("/")
    sid = client.cookies.get("sp_sid") or resp.cookies.get("sp_sid")
    assert sid, "session id cookie must be issued"
    resp = client.post("/register", data={
        "email": email, "password": password, "csrf": security.csrf_token_for(sid)},)
    assert resp.status_code in (303, 307), resp.text
    return dict(client.cookies)


def _login(email: str, password: str) -> "object":
    client.get("/")  # establishes the sp_sid cookie needed for CSRF
    sid = client.cookies.get("sp_sid")
    return client.post("/login", data={
        "email": email, "password": password, "csrf": security.csrf_token_for(sid)})


# --- 1. SQL injection --------------------------------------------------------

def test_sql_injection_login_rejected():
    resp = _login("admin' OR '1'='1' --", "irrelevant")
    assert resp.status_code == 401


def test_sql_injection_in_organisation_number_rejected():
    _register(f"sql-{secrets.token_hex(4)}@example.com")
    sid = client.cookies.get("sp_sid")
    resp = client.get("/companies/1' OR '1'='1")
    assert resp.status_code == 400
    resp = client.post("/research", data={
        "organisation_number": "999999999' OR 1=1--",
        "csrf": security.csrf_token_for(sid)})
    assert resp.status_code == 400


def test_store_parameterized_lookup():
    store = _store()
    store.ensure_tenant("t-a")
    assert store.get_profile("t-a", "1'; DROP TABLE profiles; --") is None


def _store():
    from norway_company_agent.store import Store
    return Store(Path(_TMP) / "profiles.db")


# --- 2. XSS ------------------------------------------------------------------

def test_xss_script_tag_rejected_in_org_field():
    _register(f"xss-{secrets.token_hex(4)}@example.com")
    sid = client.cookies.get("sp_sid")
    resp = client.post("/research", data={
        "organisation_number": "<script>alert(1)</script>",
        "csrf": security.csrf_token_for(sid)})
    assert resp.status_code == 400
    assert "<script>alert(1)</script>" not in resp.text


def test_security_headers_and_csp_present():
    resp = client.get("/login")
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"
    assert resp.headers.get("X-Frame-Options") == "DENY"
    csp = resp.headers.get("Content-Security-Policy", "")
    assert "default-src 'self'" in csp and "script-src 'self'" in csp


def test_no_localstorage_token_usage():
    for path in ("/", "/login", "/register"):
        body = client.get(path).text
        assert "localStorage" not in body and "sessionStorage" not in body


# --- 3. CSRF -----------------------------------------------------------------

def test_csrf_missing_token_rejected():
    _register(f"csrf-{secrets.token_hex(4)}@example.com")
    resp = client.post("/research", data={"organisation_number": "810034882"})
    assert resp.status_code == 403


def test_csrf_wrong_token_rejected():
    _register(f"csrf2-{secrets.token_hex(4)}@example.com")
    resp = client.post("/research", data={
        "organisation_number": "810034882", "csrf": "wrong-token"})
    assert resp.status_code == 403


def test_csrf_logout_requires_token():
    _register(f"csrf3-{secrets.token_hex(4)}@example.com")
    resp = client.post("/logout", data={})
    assert resp.status_code == 403


# --- 4. File upload validation ----------------------------------------------

def test_upload_rejects_executable_extension():
    ok, reason = validate_upload("evil.exe", b"MZ\x90\x00")
    assert not ok and "extension" in reason


def test_upload_rejects_oversized_and_binary():
    ok, _ = validate_upload("big.json", b"x" * (2 * 1024 * 1024 + 1))
    assert not ok
    ok, _ = validate_upload("blob.json", b"\xff\xfe\x00binary")
    assert not ok


def test_upload_rejects_invalid_json_and_accepts_valid():
    ok, _ = validate_upload("report.json", b"{not json")
    assert not ok
    ok, _ = validate_upload("report.json", b'{"passed": true}')
    assert ok


def test_upload_endpoint_requires_admin_and_validates():
    _register(f"up-{secrets.token_hex(4)}@example.com")
    sid = client.cookies.get("sp_sid")
    csrf = security.csrf_token_for(sid)
    resp = client.post("/admin/upload", files={"file": ("x.exe", b"MZ")},
                       data={"csrf": csrf})
    assert resp.status_code in (401, 403)  # not admin


# --- 5. Broken object-level authorization (BOLA) & row-level security --------

def test_bola_other_tenant_cannot_read_profile():
    store = _store()
    store.ensure_tenant("tenant-a")
    store.ensure_tenant("tenant-b")
    store.upsert_profile("tenant-a", {"organisation_number": "810034882", "name": "SECRET AS"})
    assert store.get_profile("tenant-a", "810034882")["name"] == "SECRET AS"
    assert store.get_profile("tenant-b", "810034882") is None  # RLS: cross-tenant read blocked
    assert store.list_profiles("tenant-b") == []


def test_bola_web_404_for_other_tenant_profile():
    store = _store()
    store.ensure_tenant("tenant-web-owner")
    store.upsert_profile("tenant-web-owner", {"organisation_number": "810059672", "name": "Owner AS"})
    _register(f"bola-{secrets.token_hex(4)}@example.com")  # new tenant ≠ owner
    resp = client.get("/companies/810059672")
    assert resp.status_code == 404


# --- 6. Rate limiting --------------------------------------------------------

def test_login_rate_limit_triggers():
    for _ in range(10):
        _login("victim@example.com", "wrong-password")
    resp = _login("victim@example.com", "wrong-password")
    assert resp.status_code == 429


# --- 7. JWT & session handling ----------------------------------------------

def test_session_cookie_is_httponly_and_strict():
    resp = client.get("/login")
    set_cookie = resp.headers.get("set-cookie", "")
    assert "HttpOnly" in set_cookie
    assert "samesite=strict" in set_cookie.lower()


def test_jwt_rejects_tampered_token():
    token = security.issue_token("usr-1", "t-1", "user")
    tampered = token[:-2] + ("aa" if token[-2:] != "aa" else "bb")
    assert security.decode_token(tampered) is None
    assert security.decode_token(token)["sub"] == "usr-1"


def test_jwt_alg_confusion_blocked():
    import base64
    import json as _json

    def _b64(data: dict) -> str:
        raw = _json.dumps(data, separators=(",", ":")).encode()
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    forged = f"{_b64({'alg': 'none', 'typ': 'JWT'})}.{_b64({'sub': 'attacker', 'tenant': 't-evil', 'role': 'admin', 'exp': 9999999999})}."
    assert security.decode_token(forged) is None  # only HS256 is accepted


# --- 8. MFA ------------------------------------------------------------------

def test_mfa_enable_and_verify_flow():
    import re as _re

    import pyotp

    _register(f"mfa-{secrets.token_hex(4)}@example.com")
    sid = client.cookies.get("sp_sid")
    csrf = security.csrf_token_for(sid)
    resp = client.post("/account/mfa/setup", data={"csrf": csrf})
    assert resp.status_code == 200
    match = _re.search(r'<p class="mono">([A-Z2-7]+)</p>', resp.text)
    assert match, "TOTP secret must be rendered"
    totp_secret = match.group(1)
    code = pyotp.TOTP(totp_secret).now()
    resp = client.post("/account/mfa/confirm", data={"code": code, "csrf": csrf})
    assert resp.status_code == 303
    resp = client.post("/account/mfa/confirm", data={"code": "000000", "csrf": csrf})
    assert resp.status_code in (401, 403)


# --- 9. Server-side permissions ---------------------------------------------

def test_non_admin_cannot_access_admin_pages():
    _register(f"norm-{secrets.token_hex(4)}@example.com")
    assert client.get("/admin").status_code == 403
    sid = client.cookies.get("sp_sid")
    resp = client.post("/admin/preview-url", data={
        "url": "https://example.com", "csrf": security.csrf_token_for(sid)})
    assert resp.status_code == 403


# --- 10. Webhook signatures ---------------------------------------------------

def test_webhook_rejects_bad_signature_accepts_good():
    body = b'{"event":"score.updated"}'
    resp = client.post("/webhooks/builderr", content=body,
                       headers={"X-Signature": "sha256=" + "0" * 64})
    assert resp.status_code == 401
    resp = client.post("/webhooks/builderr", content=body)  # missing header
    assert resp.status_code == 401
    resp = client.post("/webhooks/builderr", content=body,
                       headers={"X-Signature": security.sign_payload(body)})
    assert resp.status_code == 200
    assert security.verify_webhook_signature(body, "sha256=" + "0" * 64) is False


# --- 11. SSRF -----------------------------------------------------------------

def test_ssrf_blocks_private_and_metadata_targets():
    from norway_company_agent.website import assert_public_url
    for url in ("http://127.0.0.1/admin", "http://localhost:8080/",
                "http://169.254.169.254/latest/meta-data/", "http://0.0.0.0/",
                "file:///etc/passwd"):
        with pytest.raises(ValueError):
            assert_public_url(url)


# --- 12. CORS ------------------------------------------------------------------

def test_cors_no_allowlist_no_acao_header():
    resp = client.get("/login", headers={"Origin": "https://evil.example"})
    assert "Access-Control-Allow-Origin" not in resp.headers


def test_cors_preflight_foreign_origin_forbidden():
    resp = client.request("OPTIONS", "/login", headers={"Origin": "https://evil.example"})
    assert resp.status_code == 403


# --- 13. Source maps ------------------------------------------------------------

def test_no_source_maps_shipped():
    static_dir = ROOT / "webapp" / "static"
    assert not list(static_dir.rglob("*.map"))
    for path in static_dir.rglob("*"):
        if path.is_file():
            assert "sourceMappingURL" not in path.read_text(encoding="utf-8", errors="ignore")


# --- 14. Default credentials -----------------------------------------------------

def test_bootstrap_admin_has_random_password_and_must_rotate():
    identity = IdentityStore(Path(_TMP) / "identity-extra.db")
    bootstrap = identity.ensure_bootstrap_admin()
    assert bootstrap is not None
    assert bootstrap["must_change_password"] is True
    assert len(bootstrap["password"]) >= 16
    assert bootstrap["password"] not in ("admin", "password", "admin123")
    # No default-credential backdoor: a second bootstrap call is a no-op.
    assert identity.ensure_bootstrap_admin() is None


# --- 15. Log redaction -----------------------------------------------------------

def test_log_redaction_strips_secrets():
    import io
    import logging

    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(message)s"))
    handler.addFilter(security.RedactingFilter())
    logger = logging.getLogger("redaction-test")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.info("using Bearer abcdef123456 token and password: hunter2secret")
    logger.warning("GROQ_API_KEY=gsk_super_secret_value")
    logger.removeHandler(handler)
    output = stream.getvalue()
    assert "abcdef123456" not in output
    assert "hunter2secret" not in output
    assert "gsk_super_secret_value" not in output


# --- 16. Password hashing & policy ------------------------------------------------

def test_password_hashing_is_argon2_and_verifies():
    stored = security.hash_password("Str0ngPassphrase!")
    assert stored.startswith("$argon2")
    assert "Str0ngPassphrase!" not in stored
    assert security.verify_password(stored, "Str0ngPassphrase!")
    assert not security.verify_password(stored, "wrong-passphrase")


def test_password_policy_enforced_endpoint():
    _register(f"pol-{secrets.token_hex(4)}@example.com")
    sid = client.cookies.get("sp_sid")
    csrf = security.csrf_token_for(sid)
    resp = client.post("/account/password", data={
        "current_password": "Str0ngPassphrase!", "new_password": "short", "csrf": csrf})
    assert resp.status_code == 400


# --- 17. Browser-friendly auth UX (redirects for HTML, JSON for APIs) --------

def test_anonymous_browser_research_redirects_to_login():
    resp = client.post("/research", data={"organisation_number": "810034882"},
                       headers={"Accept": "text/html,application/xhtml+xml"})
    assert resp.status_code == 303
    assert resp.headers["location"].startswith("/login?next=")


def test_anonymous_browser_page_visit_redirects_to_login():
    resp = client.get("/companies/810034882",
                      headers={"Accept": "text/html,application/xhtml+xml"})
    assert resp.status_code == 303
    assert resp.headers["location"].startswith("/login?next=")


def test_anonymous_api_post_gets_json_401():
    resp = client.post("/research", data={"organisation_number": "810034882"})
    assert resp.status_code == 401
    assert resp.json() == {"detail": "authentication required"}


def test_login_next_roundtrip_and_open_redirect_blocked():
    email = f"nx-{secrets.token_hex(4)}@example.com"
    _register(email)
    client.post("/logout", data={"csrf": security.csrf_token_for(client.cookies.get("sp_sid"))})
    client.cookies.clear()
    # login page receives the next target
    resp = client.get("/login?next=/search")
    assert 'name="next" value="/search"' in resp.text
    # successful login returns to the target
    sid = client.cookies.get("sp_sid")
    resp = client.post("/login", data={"email": email, "password": "Str0ngPassphrase!",
                                       "csrf": security.csrf_token_for(sid), "next": "/search"})
    assert resp.status_code == 303
    assert resp.headers["location"] == "/search"
    # open-redirect attempts are neutralized to "/"
    client.cookies.clear()
    client.get("/login")
    sid = client.cookies.get("sp_sid")
    resp = client.post("/login", data={"email": email, "password": "Str0ngPassphrase!",
                                       "csrf": security.csrf_token_for(sid),
                                       "next": "//evil.example/steal"})
    assert resp.status_code == 303
    assert resp.headers["location"] == "/"



