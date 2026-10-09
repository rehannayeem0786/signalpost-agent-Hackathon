# TASKS — build board

Legend: ✅ done · 🔄 in progress · ⬜ planned. Dates in Oct 2026.

## Phase 0 — Deep brief comprehension ✅
- ✅ Extracted challenge spec (`/api/challenge/signalpost`), evaluation contract,
  participant brief, source policy, agent playbook, learning harness
- ✅ Analyzed live board: 37 submissions, 0 qualified, top 60.80 — **recall is
  the bottleneck (≤17.5/50)**; precision/synthesis/UX are nearly maxed by leaders
- ✅ Downloaded starter kit + 411,160-company universe (SHA-256 verified against
  the published contract hash)

## Phase 1 — Agent core ✅
- ✅ `.venv` (Python 3.12.14) + 91 pinned dependencies
- ✅ Vendored starter core; fixed Windows `resource` import
- ✅ `universe.py` — frozen-snapshot identity anchor (no bulk CSV dependency)
- ✅ `runner.py` — batch orchestrator: per-company isolation, wall-clock budget,
  checkpoint/resume, dual state vocabularies, harness validation, run report
- ✅ `claims.py` — claims↔evidence flattening (registry-live fallback, null-not-zero)
- ✅ `news.py` — Google News RSS connector, two-tier exact-name gate + possessives
- ✅ `synth.py` — Groq/OpenRouter synthesis with evidence-id guard + deterministic fallback
- ✅ `store.py` — SQLite, RLS-style tenant scoping, content-addressed snapshots, idempotent changes
- ✅ Website: SSRF/robots-safe crawler + bounded slug discovery behind the exact-entity gate
- ✅ Expired-TLS bounded fallback (recorded in evidence)

## Phase 2 — Verification ✅
- ✅ Offline 3-company contract run (all checks green)
- ✅ Live runs (3 + 5 companies) validating BRREG/website/news paths
- ✅ **100-company live smoke** → `reports/smoke-100/report.json`:
  100/100 envelopes, all 10 contract checks pass, 226 s, 846 requests, $0.00
- ✅ `official_website` 2→11 via slug discovery; metrics (p50/p95/requests) populated
- ✅ 149 tests green: 104 starter regression + 30 security + 7 contract + 8 gates

## Phase 3 — Secure web product ✅
- ✅ FastAPI + Jinja2: `/companies/:org`, `/research`, `/refresh`, auth, admin
- ✅ Full security checklist implemented → SECURITY.md (20/20 with tests)
- ✅ pip-audit: no known vulnerabilities (9 Oct)

## Phase 4 — Documentation ✅
- ✅ PRD.md · ARCHITECTURE.md · RULES.md · DESIGN.md · TASKS.md · MEMORY.md
- ✅ README.md (submission checklist) · SECURITY.md
- 🔄 docs/ playbook set (AGENT, CRAWLERS, IDENTITY_RESOLUTION, DATA_SCHEMA,
  REFRESH, EVAL, LIMITATIONS) — in progress this session

## Phase 5 — Knowledge graph (graphify) ✅
- ✅ Cloned Graphify-Labs/graphify (reference) + installed CLI (`uv tool install graphifyy`)
- ✅ `graphify . --code-only --no-label` → `graphify-out/`: 805 nodes,
  2,232 edges, 33 communities; GRAPH_REPORT.md + graph.json committed
- ✅ Verified `graphify query` / `god-nodes` (hubs: create_app, run_batch,
  fetch_website, utc_now, _csrf_of)

## Phase 4b — Judge-facing product round ✅ (9 Oct)
- ✅ Async research/refresh **jobs with live step-by-step progress** (zero-JS
  meta-refresh polling) — `/jobs/{id}` page, tenant-scoped, BOLA-tested
- ✅ **Coverage meter** (7 information families, rubric-aligned) + **exact-entity
  gate badge** ("✓ verified · gate 0.95" / "site withheld by gate")
- ✅ **One-click envelope export** `/companies/:org/envelope.json` (the exact
  competition artifact — lets judges verify facts in seconds)
- ✅ Landing hero + how-it-works + sample company quick-links (`/?org=` prefill, sanitized)
- ✅ **Careers deep-crawl**: gated sites' careers pages → `job_posting` claims
  (robots+SSRF guarded, pure extractor tested)
- ✅ **Workforce claim**: official sum of subunit employees (`registered_workforce`)
- ✅ Browser-friendly auth redirects (401→login with safe `next`, JSON for APIs)
- ✅ Test suite now **168 passed**; live web checks: job 21.5 s / 25.8 s,
  coverage+gate badges render, envelope export 31/43 claims

## Phase 6 — Submission ⬜
- ✅ Final full test pass (149) + pip-audit re-run (0 vulns) + live uvicorn boot check
- ✅ Git commit (v1) → **`a5dd848376e33044f261a74f29280578a574db18`** (120 files)
- ⬜ Email submit@builderr.ai: repo URL, commit, smoke report, run command,
  models/APIs, expected cost (draft checklist in README)
- ⬜ v2 ideas ranked by expected recall gain (see MEMORY.md §7)

## Revision budget (max 5 versions, revisions freeze 18 Oct)
| Version | Planned content | Status |
|---|---|---|
| v1 | full pipeline + gates + security + docs | ready to commit |
| v2 | Brave discovery when key available; careers-page extraction depth | ⬜ |
| v3 | financial_history→claims; underenheter employees merge | ⬜ |
| v4 | promotion-gate eval on gold set; threshold tuning | ⬜ |
| v5 | final freeze before 18 Oct | ⬜ |
