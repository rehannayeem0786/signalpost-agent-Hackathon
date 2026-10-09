"""Signalpost web product — secure FastAPI application.

Routes follow the challenge's preferred interface: ``/companies/:org``,
``/research``, ``/refresh``. Security posture is documented in RULES.md and
regressed by tests/test_security.py: session JWT lives only in an httpOnly
cookie (never localStorage), every POST carries a CSRF token, every data row is
tenant-scoped server-side, uploads are validated, webhooks are HMAC-signed,
outbound fetches are SSRF-guarded, CORS is an explicit allowlist, and rate
limits apply to credential and research endpoints.
"""

from __future__ import annotations

import logging
import os
import re
import secrets
import threading
from pathlib import Path

from fastapi import FastAPI, Depends, Form, Request, Response, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from norway_company_agent.news import fetch_news  # noqa: F401 (kept for parity checks)
from norway_company_agent.runner import research_company
from norway_company_agent.store import Store
from norway_company_agent.refresh import diff_profile
from norway_company_agent.website import assert_public_url

from . import security
from .db import IdentityStore, validate_upload

logger = logging.getLogger("webapp")

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("WEBAPP_DATA_DIR", str(BASE_DIR / "data")))
DATA_DIR.mkdir(parents=True, exist_ok=True)

ORG_RE = re.compile(r"^\d{9}$")
SESSION_COOKIE = "sp_session"
SID_COOKIE = "sp_sid"
PENDING_COOKIE = "sp_pending"
CSRF_FIELD = "csrf"

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
templates.env.autoescape = True  # XSS: all template output is escaped

identity = IdentityStore(DATA_DIR / "identity.db")
store = Store(DATA_DIR / "profiles.db")

_job_lock = threading.Lock()


# --- auth dependencies -------------------------------------------------------

def _decode_cookie(request: Request, name: str) -> str | None:
    value = request.cookies.get(name)
    if not value:
        return None
    return value


def current_user(request: Request) -> dict | None:
    token = _decode_cookie(request, SESSION_COOKIE)
    if not token:
        return None
    payload = security.decode_token(token)
    if not payload:
        return None
    return {
        "user_id": payload.get("sub"),
        "tenant_id": payload.get("tenant"),
        "role": payload.get("role", "user"),
        "email": payload.get("email", ""),
    }


def require_user(request: Request) -> dict:
    user = current_user(request)
    if not user:
        raise _unauthorized()
    return user


def require_admin(request: Request) -> dict:
    user = current_user(request)
    if not user:
        raise _unauthorized()
    if user.get("role") != "admin":
        # Server-side permission enforcement: no client-side role can bypass this.
        raise _forbidden()
    return user


def _unauthorized():
    from fastapi import HTTPException
    return HTTPException(status_code=401, detail="authentication required")


def _forbidden():
    from fastapi import HTTPException
    return HTTPException(status_code=403, detail="forbidden")


def check_csrf(request: Request, csrf: str = Form(default="")) -> None:
    sid = _sid_of(request)
    if not sid or not security.csrf_validate(sid, csrf):
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="CSRF validation failed")


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _rate_limit(request: Request, bucket: str, limit: int, window: int) -> None:
    if not security.limiter.allow(bucket, _client_ip(request), limit, window):
        from fastapi import HTTPException
        raise HTTPException(status_code=429, detail="rate limit exceeded")


def _set_session(response: Response, user: dict, *, max_age: int = 3600 * 8) -> None:
    token = security.issue_token(user["user_id"], user["tenant_id"], user["role"],
                                 expires_seconds=max_age, email=user.get("email", ""))
    response.set_cookie(SESSION_COOKIE, token, httponly=True, samesite="strict",
                        secure=os.environ.get("WEBAPP_SECURE_COOKIES", "1") == "1",
                        max_age=max_age, path="/")
    response.delete_cookie(PENDING_COOKIE, path="/")


def _ensure_sid(response: Response, request: Request) -> str:
    """Ensure a session-id exists for CSRF derivation.

    The cookie itself is attached by the middleware after the handler runs:
    FastAPI drops headers set on the injected ``Response`` when a handler
    returns its own response object, so we stage the value on ``request.state``.
    """
    return _sid_of(request)


def _sid_of(request: Request) -> str:
    existing = request.cookies.get(SID_COOKIE)
    if existing:
        return existing
    state_sid = getattr(request.state, "sid", None)
    if state_sid:
        return state_sid
    request.state.sid = secrets.token_urlsafe(24)
    return request.state.sid


def _csrf_of(request: Request) -> str:
    return security.csrf_token_for(_sid_of(request))


def create_app() -> FastAPI:
    app = FastAPI(title="Signalpost company research", docs_url=None, redoc_url=None, openapi_url=None)
    app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

    @app.middleware("http")
    async def hardening(request: Request, call_next):
        response = await call_next(request)
        for header, value in security.security_headers():
            response.headers[header] = value
        # Stage a session-id cookie for CSRF when the visitor has none yet.
        staged_sid = getattr(request.state, "sid", None)
        if staged_sid and not request.cookies.get(SID_COOKIE):
            response.set_cookie(SID_COOKIE, staged_sid, httponly=True, samesite="strict",
                                secure=os.environ.get("WEBAPP_SECURE_COOKIES", "1") == "1",
                                max_age=3600 * 12, path="/")
        origin = request.headers.get("origin")
        allowed = security.cors_allowlist()
        if origin and origin in allowed:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Vary"] = "Origin"
        if request.method == "OPTIONS" and origin and origin not in allowed:
            return JSONResponse(status_code=403, content={"detail": "origin not allowed"})
        return response

    @app.on_event("startup")
    def _startup() -> None:
        security.install_log_redaction()
        bootstrap = identity.ensure_bootstrap_admin()
        if bootstrap:
            # Printed exactly once; the account must rotate the password at first login.
            logger.warning("bootstrap admin created: %s one-time password: %s",
                           bootstrap["email"], bootstrap["password"])

    @app.get("/healthz", response_class=JSONResponse)
    def healthz() -> dict:
        return {"status": "ok"}

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request, response: Response):
        user = current_user(request)
        _ensure_sid(response, request)
        recent = store.list_profiles(user["tenant_id"], limit=20) if user else []
        return templates.TemplateResponse(request, "index.html", {
            "user": user, "recent": recent, "csrf": _csrf_of(request), "flash": request.query_params.get("msg"),
        })

    @app.get("/companies/{organisation_number}", response_class=HTMLResponse)
    def company(request: Request, organisation_number: str, response: Response):
        user = require_user(request)
        _ensure_sid(response, request)
        if not ORG_RE.match(organisation_number):
            return templates.TemplateResponse(request, "error.html", {
                "user": user, "csrf": _csrf_of(request), "status": 400,
                "message": "Organisation number must be exactly 9 digits."}, status_code=400)
        # Row-level access: only the caller's tenant rows are visible, ever.
        profile = store.get_profile(user["tenant_id"], organisation_number)
        if not profile:
            return templates.TemplateResponse(request, "error.html", {
                "user": user, "csrf": _csrf_of(request), "status": 404,
                "message": "No profile for this company in your workspace yet. Use Research to create one."}, status_code=404)
        changes = store.list_changes(user["tenant_id"], organisation_number, limit=25)
        profile = _render_ready(profile)
        return templates.TemplateResponse(request, "company.html", {
            "user": user, "csrf": _csrf_of(request), "profile": profile, "changes": changes,
        })

    @app.get("/search", response_class=HTMLResponse)
    def search(request: Request, response: Response, q: str = ""):
        user = require_user(request)
        _ensure_sid(response, request)
        query = q.strip()
        rows = store.list_profiles(user["tenant_id"], limit=50)
        matches = [row for row in rows if query in row.get("organisation_number", "")]
        return templates.TemplateResponse(request, "search.html", {
            "user": user, "csrf": _csrf_of(request), "query": query, "matches": matches,
        })

    @app.post("/research", response_class=HTMLResponse)
    def research(request: Request,
                 organisation_number: str = Form(...), csrf: str = Form(default="")):
        user = require_user(request)
        _rate_limit(request, "research", 30, 60)
        check_csrf(request, csrf)
        org = "".join(ch for ch in organisation_number if ch.isdigit())
        if not ORG_RE.match(org):
            return _page_error(request, user, 400, "Organisation number must be exactly 9 digits.")
        job_id = "job-" + secrets.token_urlsafe(8)
        store.create_job(user["tenant_id"], job_id, "research")
        try:
            envelope = research_company(
                _seed_profile(org), list(MODULES),
                run_id=job_id, started_at=envelope_now(), offline=False, use_llm=True)
            store.upsert_profile(user["tenant_id"], envelope["profile"])
            store.update_job(user["tenant_id"], job_id, "completed", envelope.get("status"))
        except Exception as exc:
            logger.warning("research failed for org=%s error=%s", org, type(exc).__name__)
            store.update_job(user["tenant_id"], job_id, "failed", type(exc).__name__)
            return _page_error(request, user, 500,
                               "Research failed for this company; no partial data was stored.")
        return _redirect_with_session(f"/companies/{org}?msg=researched", user)

    @app.post("/refresh", response_class=HTMLResponse)
    def refresh(request: Request,
                organisation_number: str = Form(...), csrf: str = Form(default="")):
        user = require_user(request)
        _rate_limit(request, "refresh", 30, 60)
        check_csrf(request, csrf)
        org = "".join(ch for ch in organisation_number if ch.isdigit())
        if not ORG_RE.match(org):
            return _page_error(request, user, 400, "Organisation number must be exactly 9 digits.")
        previous = store.get_profile(user["tenant_id"], org)
        if not previous:
            return _page_error(request, user, 404, "Nothing to refresh: research the company first.")
        job_id = "job-" + secrets.token_urlsafe(8)
        store.create_job(user["tenant_id"], job_id, "refresh")
        try:
            envelope = research_company(
                dict(previous), list(MODULES),
                run_id=job_id, started_at=envelope_now(), offline=False, use_llm=True)
            current = envelope["profile"]
            changes = diff_profile(previous, current)
            store.upsert_profile(user["tenant_id"], current)
            # Idempotent: replaying the same snapshot records no duplicate change rows.
            store.record_changes(user["tenant_id"], org, changes)
            store.update_job(user["tenant_id"], job_id, "completed", f"{len(changes)} change(s)")
        except Exception as exc:
            logger.warning("refresh failed for org=%s error=%s", org, type(exc).__name__)
            store.update_job(user["tenant_id"], job_id, "failed", type(exc).__name__)
            return _page_error(request, user, 500,
                               "Refresh failed; the previous supported value was preserved.")
        return _redirect_with_session(f"/companies/{org}?msg=refreshed", user)

    # --- authentication (rate-limited; session only in httpOnly cookie) ------

    @app.get("/login", response_class=HTMLResponse)
    def login_page(request: Request, response: Response):
        _ensure_sid(response, request)
        return templates.TemplateResponse(request, "login.html", {
            "user": current_user(request), "csrf": _csrf_of(request), "error": None})

    @app.post("/login", response_class=HTMLResponse)
    def login(request: Request,
              email: str = Form(...), password: str = Form(...), csrf: str = Form(default="")):
        _rate_limit(request, "login", 10, 60)  # credential stuffing brake
        check_csrf(request, csrf)
        user_row = identity.authenticate(email, password)
        if not user_row:
            return templates.TemplateResponse(request, "login.html", {
                "user": None, "csrf": _csrf_of(request),
                "error": "Invalid credentials."}, status_code=401)
        if user_row["mfa_enabled"]:
            pending = security.issue_token(user_row["user_id"], user_row["tenant_id"], user_row["role"],
                                           expires_seconds=300, email=user_row["email"])
            resp = RedirectResponse(url="/login/mfa", status_code=303)
            resp.set_cookie(PENDING_COOKIE, pending, httponly=True, samesite="strict",
                            secure=os.environ.get("WEBAPP_SECURE_COOKIES", "1") == "1", max_age=300, path="/")
            return resp
        return _start_session(user_row)

    @app.get("/login/mfa", response_class=HTMLResponse)
    def mfa_page(request: Request, response: Response):
        _ensure_sid(response, request)
        if not _decode_cookie(request, PENDING_COOKIE):
            return RedirectResponse(url="/login", status_code=303)
        return templates.TemplateResponse(request, "mfa.html", {
            "user": None, "csrf": _csrf_of(request), "error": None})

    @app.post("/login/mfa", response_class=HTMLResponse)
    def mfa_verify(request: Request, code: str = Form(...), csrf: str = Form(default="")):
        _rate_limit(request, "mfa", 10, 60)
        check_csrf(request, csrf)
        pending_token = _decode_cookie(request, PENDING_COOKIE)
        payload = security.decode_token(pending_token) if pending_token else None
        if not payload:
            return RedirectResponse(url="/login", status_code=303)
        secret = identity.get_totp_secret(payload["sub"], payload.get("tenant", ""))
        if not secret or not security.totp_verify(secret, code):
            return templates.TemplateResponse(request, "mfa.html", {
                "user": None, "csrf": _csrf_of(request),
                "error": "Invalid code."}, status_code=401)
        return _start_session({"user_id": payload["sub"], "tenant_id": payload.get("tenant"),
                               "role": payload.get("role", "user"), "email": payload.get("email", "")})

    @app.get("/register", response_class=HTMLResponse)
    def register_page(request: Request, response: Response):
        _ensure_sid(response, request)
        return templates.TemplateResponse(request, "register.html", {
            "user": None, "csrf": _csrf_of(request), "error": None})

    @app.post("/register", response_class=HTMLResponse)
    def register(request: Request,
                 email: str = Form(...), password: str = Form(...), csrf: str = Form(default="")):
        _rate_limit(request, "register", 5, 300)
        check_csrf(request, csrf)
        if not security.password_policy_ok(password):
            return templates.TemplateResponse(request, "register.html", {
                "user": None, "csrf": _csrf_of(request),
                "error": "Password must be 12+ characters with upper, lower and a digit."}, status_code=400)
        if identity.find_by_email(email):
            return templates.TemplateResponse(request, "register.html", {
                "user": None, "csrf": _csrf_of(request),
                "error": "Account already exists."}, status_code=409)
        # Each account gets its own tenant: profiles are isolated by construction.
        tenant = "t-" + secrets.token_urlsafe(9)
        identity.create_user(tenant, email, password, role="user")
        user_row = identity.authenticate(email, password)
        if not user_row:
            return RedirectResponse(url="/login", status_code=303)
        return _start_session(user_row)

    @app.post("/logout")
    def logout(request: Request, csrf: str = Form(default="")):
        check_csrf(request, csrf)
        resp = RedirectResponse(url="/login", status_code=303)
        resp.delete_cookie(SESSION_COOKIE, path="/")
        resp.delete_cookie(PENDING_COOKIE, path="/")
        return resp

    @app.get("/account", response_class=HTMLResponse)
    def account(request: Request, response: Response):
        user = require_user(request)
        _ensure_sid(response, request)
        row = identity.find_by_email(_email_of(user)) or {}
        return templates.TemplateResponse(request, "account.html", {
            "user": user, "csrf": _csrf_of(request),
            "mfa_enabled": bool(row.get("mfa_enabled")),
            "message": request.query_params.get("msg")})

    @app.post("/account/password", response_class=HTMLResponse)
    def change_password(request: Request,
                        current_password: str = Form(...), new_password: str = Form(...),
                        csrf: str = Form(default="")):
        user = require_user(request)
        _rate_limit(request, "password", 10, 300)
        check_csrf(request, csrf)
        row = identity.find_by_email(user.get("email") or "")
        if not row or not security.verify_password(row["password_hash"], current_password):
            return _page_error(request, user, 403, "Current password is incorrect.")
        if not security.password_policy_ok(new_password):
            return _page_error(request, user, 400,
                               "Password must be 12+ characters with upper, lower and a digit.")
        identity.set_password(row["user_id"], row["tenant_id"], new_password)
        return _redirect_with_session("/account?msg=password-updated", user)

    @app.post("/account/mfa/setup", response_class=HTMLResponse)
    def mfa_setup(request: Request, csrf: str = Form(default="")):
        user = require_user(request)
        check_csrf(request, csrf)
        row = identity.find_by_email(user.get("email") or "")
        if not row:
            return _page_error(request, user, 404, "Account not found.")
        secret = identity.enable_mfa(row["user_id"], row["tenant_id"])
        uri = security.totp_uri(secret, row["email"])
        return templates.TemplateResponse(request, "mfa_setup.html", {
            "user": user, "csrf": _csrf_of(request), "secret": secret, "otpauth_uri": uri})

    @app.post("/account/mfa/confirm", response_class=HTMLResponse)
    def mfa_confirm(request: Request, code: str = Form(...), csrf: str = Form(default="")):
        user = require_user(request)
        _rate_limit(request, "mfa-confirm", 10, 60)
        check_csrf(request, csrf)
        secret = identity.get_totp_secret(user["user_id"], user["tenant_id"])
        if not secret or not security.totp_verify(secret, code):
            return _page_error(request, user, 401, "Invalid code; MFA stays active until verified.")
        return _redirect_with_session("/account?msg=mfa-verified", user)

    # --- administration (server-side role check, never template-side) ---------

    @app.get("/admin", response_class=HTMLResponse)
    def admin_page(request: Request, response: Response):
        user = require_admin(request)
        _ensure_sid(response, request)
        return templates.TemplateResponse(request, "admin.html", {
            "user": user, "csrf": _csrf_of(request), "users": identity.list_users(user["tenant_id"]),
            "message": request.query_params.get("msg")})

    @app.post("/admin/upload", response_class=HTMLResponse)
    async def admin_upload(request: Request, csrf: str = Form(default=""),
                           file: UploadFile = File(...)):
        user = require_admin(request)
        _rate_limit(request, "upload", 10, 300)
        # CSRF comes from the multipart form itself.
        form = await request.form()
        check_csrf(request, str(form.get(CSRF_FIELD, "")))
        content = await file.read()
        ok, reason = validate_upload(file.filename or "", content)
        if not ok:
            return _page_error(request, user, 400, f"Upload rejected: {reason}")
        return _redirect_with_session("/admin?msg=upload-ok", user)

    @app.post("/webhooks/builderr", response_class=JSONResponse)
    async def builderr_webhook(request: Request):
        _rate_limit(request, "webhook", 60, 60)
        body = await request.body()
        signature = request.headers.get("X-Signature")
        if not security.verify_webhook_signature(body, signature):
            return JSONResponse(status_code=401, content={"detail": "invalid signature"})
        return JSONResponse(content={"received": True})

    @app.post("/admin/preview-url", response_class=JSONResponse)
    def preview_url(request: Request, url: str = Form(...), csrf: str = Form(default="")):
        """Outbound fetch preview — SSRF-guarded (private/loopback/metadata blocked)."""
        user = require_admin(request)
        check_csrf(request, csrf)
        try:
            assert_public_url(url)
        except ValueError as exc:
            return JSONResponse(status_code=400, content={"detail": f"blocked: {exc}"})
        return JSONResponse(content={"allowed": True})

    return app


# --- shared route helpers (resolved at request time) -------------------------

MODULES = ("registry", "accounting_obligation", "registry_live", "financials",
           "financial_history", "roles", "group", "locations", "website", "news")


def envelope_now() -> str:
    from norway_company_agent.evidence import utc_now
    return utc_now()


def _seed_profile(org: str) -> dict:
    """Registry-anchored seed profile; live enrichment happens inside research_company."""
    from norway_company_agent.batch import accounting_obligation_assessment
    from norway_company_agent.evidence import evidence, utc_now
    from norway_company_agent.runner import unresolved_profile
    from norway_company_agent.universe import iter_universe, normalize_universe_row

    universe = os.environ.get("SIGNALPOST_UNIVERSE", str(DATA_DIR / "universe.jsonl.gz"))
    if Path(universe).exists():
        for row in iter_universe(universe):
            if str(row.get("organisation_number")) == org:
                profile = normalize_universe_row(row)
                profile["evidence"] = {
                    "registry": evidence(
                        "registry", "available", "official_registry_bulk",
                        "https://builderr.ai/signalpost-company-universe-2025.jsonl.gz",
                        value=dict(row), retrieved_at=utc_now(), source_row_key=org,
                        as_of=str(row.get("latest_submitted_accounts") or "") or None),
                    "accounting_obligation": accounting_obligation_assessment(profile),
                }
                return profile
    return unresolved_profile(org, "universe file unavailable; live registry module will anchor identity")


def _page_error(request: Request, user: dict | None, status: int, message: str):
    return templates.TemplateResponse(request, "error.html", {
        "user": user, "csrf": _csrf_of(request), "status": status, "message": message},
        status_code=status)


def _render_ready(profile: dict) -> dict:
    """Attach claims, evidence rows, brief and status for the template layer."""
    from norway_company_agent.batch import evidence_terminal_state
    from norway_company_agent.claims import build_claims
    from norway_company_agent.runner import harness_status

    claims, rows = build_claims(profile)
    synthesis = (profile.get("evidence") or {}).get("synthesis") or {}
    states = {module: {"state": evidence_terminal_state(record)}
              for module, record in (profile.get("evidence") or {}).items()
              if isinstance(record, dict)}
    profile["_claims"] = claims
    profile["_evidence_rows"] = rows
    profile["_brief"] = (synthesis.get("value") or {}).get("brief")
    profile["_status"] = harness_status(profile, states)
    return profile


def _set_user_cookie(response: Response, user: dict) -> None:
    _set_session(response, user)


def _redirect_with_session(url: str, user: dict):
    resp = RedirectResponse(url=url, status_code=303)
    _set_session(resp, user)
    return resp


def _start_session(user_row: dict):
    user = {
        "user_id": user_row.get("user_id") or user_row.get("sub"),
        "tenant_id": user_row.get("tenant_id") or user_row.get("tenant"),
        "role": user_row.get("role", "user"),
        "email": user_row.get("email", ""),
    }
    url = "/account?msg=must-change" if user_row.get("must_change_password") else "/"
    resp = RedirectResponse(url=url, status_code=303)
    _set_session(resp, user)
    return resp


app = create_app()

