"""Feature tests: live job flow, envelope export, coverage UI, careers extraction.

Network is mocked out (``research_company`` is monkeypatched) so these stay
fast and deterministic; live behaviour is covered by the smoke runs.
"""

from __future__ import annotations

import os
import secrets
import sys
import time
from pathlib import Path

import pytest

os.environ.setdefault("WEBAPP_SECURE_COOKIES", "0")
os.environ.setdefault("JWT_SECRET", "feat-jwt-secret-" + secrets.token_urlsafe(24))
os.environ.setdefault("CSRF_PEPPER", "feat-csrf-secret-" + secrets.token_urlsafe(24))
os.environ.setdefault("SESSION_SECRET", "feat-session-secret-" + secrets.token_urlsafe(24))
os.environ.setdefault("WEBHOOK_SECRET", "feat-webhook-secret-" + secrets.token_urlsafe(24))

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from webapp import security  # noqa: E402
from webapp.app import app  # noqa: E402

client = TestClient(app, follow_redirects=False)


@pytest.fixture(autouse=True)
def _reset():
    security.limiter.reset()
    client.cookies.clear()
    yield
    security.limiter.reset()


def _register(email: str) -> None:
    client.get("/")
    sid = client.cookies.get("sp_sid")
    resp = client.post("/register", data={
        "email": email, "password": "Str0ngPassphrase!",
        "csrf": security.csrf_token_for(sid)})
    assert resp.status_code == 303


def _fake_research(profile, modules, *, run_id, started_at, offline=False, use_llm=True, progress=None):
    from norway_company_agent.runner import build_envelope
    if progress:
        for step in ("identity", "official", "website", "news", "claims"):
            progress(step)
    return build_envelope(profile, run_id=run_id, modules=list(modules),
                          started_at=started_at, completed_at=started_at,
                          requests=1, runtime_ms=5, third_party_cost_usd=0.0, errors=[])


def _wait_for_job(url: str, timeout: float = 10.0) -> str:
    deadline = time.monotonic() + timeout
    body = ""
    while time.monotonic() < deadline:
        resp = client.get(url, headers={"Accept": "text/html"})
        body = resp.text
        if "completed" in body or "failed" in body:
            return body
        time.sleep(0.1)
    return body


def test_research_job_flow_and_profile_page(monkeypatch):
    monkeypatch.setattr("webapp.app.research_company", _fake_research)
    _register(f"job-{secrets.token_hex(4)}@example.com")
    sid = client.cookies.get("sp_sid")
    resp = client.post("/research", data={
        "organisation_number": "810034882", "csrf": security.csrf_token_for(sid)},
        headers={"Accept": "text/html"})
    assert resp.status_code == 303
    job_url = resp.headers["location"]
    assert job_url.startswith("/jobs/job-")
    body = _wait_for_job(job_url)
    assert "completed" in body
    profile = client.get("/companies/810034882", headers={"Accept": "text/html"})
    assert profile.status_code == 200
    assert "Coverage:" in profile.text
    assert "information families" in profile.text
    assert "Download envelope JSON" in profile.text
    # meter is class-based (no template expressions inside CSS contexts)
    assert 'class="fill lvl-' in profile.text
    assert 'style="width:' not in profile.text


def test_job_page_rejects_other_tenant(monkeypatch):
    monkeypatch.setattr("webapp.app.research_company", _fake_research)
    _register(f"owner-{secrets.token_hex(4)}@example.com")
    sid = client.cookies.get("sp_sid")
    resp = client.post("/research", data={
        "organisation_number": "810034882", "csrf": security.csrf_token_for(sid)})
    job_url = resp.headers["location"]
    _wait_for_job(job_url)
    client.cookies.clear()
    _register(f"intruder-{secrets.token_hex(4)}@example.com")
    assert client.get(job_url, headers={"Accept": "text/html"}).status_code == 404


def test_envelope_export(monkeypatch):
    monkeypatch.setattr("webapp.app.research_company", _fake_research)
    _register(f"exp-{secrets.token_hex(4)}@example.com")
    sid = client.cookies.get("sp_sid")
    resp = client.post("/research", data={
        "organisation_number": "810034882", "csrf": security.csrf_token_for(sid)})
    _wait_for_job(resp.headers["location"])
    export = client.get("/companies/810034882/envelope.json")
    assert export.status_code == 200
    assert "attachment" in export.headers.get("content-disposition", "")
    envelope = export.json()
    assert envelope["organisation_number"] == "810034882"
    assert envelope["status"] in {"available", "not_available", "blocked",
                                  "not_applicable", "ambiguous", "failed"}
    assert isinstance(envelope["claims"], list) and envelope["claims"]


def test_envelope_export_bola_404(monkeypatch):
    monkeypatch.setattr("webapp.app.research_company", _fake_research)
    _register(f"exp2-{secrets.token_hex(4)}@example.com")
    sid = client.cookies.get("sp_sid")
    resp = client.post("/research", data={
        "organisation_number": "810034882", "csrf": security.csrf_token_for(sid)})
    _wait_for_job(resp.headers["location"])
    client.cookies.clear()
    _register(f"other-{secrets.token_hex(4)}@example.com")
    assert client.get("/companies/810034882/envelope.json").status_code == 404


def test_index_prefills_sample_and_sanitizes():
    _register(f"pre-{secrets.token_hex(4)}@example.com")
    resp = client.get("/?org=810324562")
    assert 'value="810324562"' in resp.text
    resp = client.get("/?org=<script>alert(1)</script>")
    assert "<script>alert(1)</script>" not in resp.text


def test_careers_extraction_pure():
    from norway_company_agent.website import extract_job_postings, find_careers_url

    html = """
    <html><body>
      <a href="/karriere/servicetekniker">Servicetekniker søkes til Oslo</a>
      <a href="/karriere/leder">Driftsleder for nattstilling</a>
      <a href="/about">About us</a>
      <a href="https://other.example/job">Developer at OtherCo</a>
      <a href="/jobs/1">Hi</a>
    </body></html>
    """
    postings = extract_job_postings(html, "https://example.no/karriere")
    titles = [p["title"] for p in postings]
    assert any("Servicetekniker" in t for t in titles)
    assert any("Driftsleder" in t for t in titles)
    assert not any(t == "About us" for t in titles)
    assert all(p["url"].startswith("https://") for p in postings)

    value = {"pages": [{"url": "https://example.no/about"}, {"url": "https://example.no/career/jobs"}]}
    assert find_careers_url(value) == "https://example.no/career/jobs"
    assert find_careers_url({"pages": [{"url": "https://example.no/about"}]}) is None


def test_workforce_claim_from_subunits():
    from norway_company_agent.claims import build_claims

    profile = {
        "organisation_number": "810034882", "name": "X AS",
        "evidence": {
            "registry": {"status": "available", "value": {"name": "X AS"},
                         "source_url": "u", "retrieved_at": "t"},
            "locations": {"status": "available", "source_url": "u", "retrieved_at": "t",
                          "value": {"locations": [
                              {"name": "A", "employees": 4},
                              {"name": "B", "employees": 6},
                              {"name": "C", "employees": None},
                          ]}},
        },
    }
    claims, _rows = build_claims(profile)
    workforce = [c for c in claims if c["field"] == "registered_workforce"]
    assert workforce and workforce[0]["availability"] == "available"
    assert workforce[0]["value"] == 10  # 4 + 6; None never inflates the total

    profile["evidence"]["locations"]["value"]["locations"][0]["employees"] = None
    profile["evidence"]["locations"]["value"]["locations"][1]["employees"] = None
    claims, _ = build_claims(profile)
    workforce = [c for c in claims if c["field"] == "registered_workforce"]
    assert workforce[0]["availability"] == "not_available"
    assert workforce[0]["value"] is None

