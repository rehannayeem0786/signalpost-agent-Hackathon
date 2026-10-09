"""Live webapp check: register -> research job (real pipeline) -> profile page."""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("WEBAPP_SECURE_COOKIES", "0")

from fastapi.testclient import TestClient  # noqa: E402

from webapp import security  # noqa: E402
from webapp.app import app  # noqa: E402

ORG = sys.argv[1] if len(sys.argv) > 1 else "810034882"
client = TestClient(app, follow_redirects=False)

client.get("/")
sid = client.cookies.get("sp_sid")
email = f"live-{int(time.time())}@example.com"
client.post("/register", data={"email": email, "password": "Str0ngPassphrase!",
                               "csrf": security.csrf_token_for(sid)})
sid = client.cookies.get("sp_sid")
started = time.monotonic()
resp = client.post("/research", data={"organisation_number": ORG,
                                      "csrf": security.csrf_token_for(sid)},
                   headers={"Accept": "text/html"})
print(f"research POST -> {resp.status_code} Location={resp.headers.get('location')}")
job_url = resp.headers.get("location", "")
body = ""
deadline = time.monotonic() + 120
steps_seen = set()
while time.monotonic() < deadline:
    page = client.get(job_url, headers={"Accept": "text/html"})
    body = page.text
    for marker in ("Resolve company identity", "Official registry", "Website crawl",
                   "Dated public activity", "Claims &amp; evidence", "Decision-useful brief"):
        if "step done" in body and marker in body:
            steps_seen.add(marker)
    if "completed" in body or "failed" in body:
        break
    time.sleep(1.0)
elapsed = time.monotonic() - started
status = "completed" if "completed" in body else ("failed" if "failed" in body else "timeout")
print(f"job {status} in {elapsed:.1f}s")
profile = client.get(f"/companies/{ORG}", headers={"Accept": "text/html"})
print(f"profile page -> {profile.status_code}")
if profile.status_code == 200:
    cov = "Coverage:" in profile.text
    gate = "exact-entity verified" in profile.text or "site withheld" in profile.text
    export = client.get(f"/companies/{ORG}/envelope.json")
    print(f"coverage_meter={cov} gate_badge={gate} export={export.status_code}")
    if export.status_code == 200:
        env = export.json()
        avail = sum(1 for c in env["claims"] if c["availability"] == "available")
        print(f"envelope claims available={avail}/{len(env['claims'])} status={env['status']}")
sys.exit(0 if status == "completed" and profile.status_code == 200 else 1)
