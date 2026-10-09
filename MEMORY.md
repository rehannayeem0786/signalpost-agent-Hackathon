# MEMORY — persistent project memory

_Last updated: 9 Oct 2026 (session 1). Read this first in any new session._

## 1. What we're doing and why

Win **#1** in Builderr's **Signalpost** challenge (`$2,500`, closes **21 Oct
2026**, revisions freeze **18 Oct**): agent takes a Norwegian org number →
evidence-backed company profile. Qualify at **65/100** (50 recall · 30
precision/evidence · 12 synthesis · 8 UX).

**Decisive board facts (review of 5 Oct 2026):** 37 submissions, **0 qualified**,
top **60.80** (Nikita). Leaders saturate Evidence (~27–29/30), Synthesis (12/12),
UX (8/8) but stall at **Recall 9–17.5/50**. → Winning = more covered field
families per company **without** a single wrong-company publication (a material
mismatch makes the run unofficial).

## 2. Environment (verified)

- Windows 11, PowerShell; Python 3.11.9 system + **3.12.14** via `py -V:3.12` (starter needs 3.12+)
- `uv 0.12.13`, `git 2.53`, `node v24` available; venv at `.venv`
- BRREG API reachable
- **.env now carries REAL keys**: `GROQ_API_KEY` (gsk_…) + `OPENROUTER_API_KEY` (sk-or-…),
  `LLM_PROVIDER=groq, openrouter` (preference list, comma-separated — supported
  since commit below). Model defaults: Groq `openai/gpt-oss-120b` → `qwen/qwen3.8-27b`
  → `llama-3.3-70b-versatile`; OpenRouter `meta-llama/llama-3.3-70b-instruct`.
  **Measured**: ~$0.0007–0.0027/company (5-company live run: $0.0067 total);
  Groq `gpt-oss-120b` hit transient failures on 3/5 calls → qwen fallback
  worked automatically. Model catalogs rotate — that's why candidates are lists.
  Probe tools: `scripts/probe_llm.py`, `scripts/check_llm_live.py`,
  `scripts/diag_synthesis.py`.
- Universe file at `data/signalpost-company-universe-2025.jsonl.gz`, SHA-256
  matches the contract (`1c89710e5b01f8617e86d09fbdff4a52f2f8dbbba297e74f7164b5984f5a0384`)

## 3. Key URLs

- Spec: `https://builderr.ai/api/challenge/signalpost` · tasks: `/tasks/signalpost.json`
- Contract: `/docs/signalpost-evaluation-harness.md` · brief: `/starter-briefs/signalpost.md`
- Sources: `/starter-briefs/signalpost-sources.md` · playbook: `signalpost-agent-playbook.md`
- Harness: `signalpost-learning-harness.md` · starter: `/signalpost-starter-kit.tar.gz`
- Universe: `/signalpost-company-universe-2025.jsonl.gz` · submit: `submit@builderr.ai`
- Sample product: `https://builderr.ai/signalpost` · board: `/challenges/signalpost`

## 4. Architecture decisions (locked for v1)

1. Vendored starter core (`src/norway_company_agent/`) + our modules:
   `universe, claims, news, synth, store, runner`. Envelope = superset of both
   vocabularies (`state` for starter validation, `status` six-state harness).
2. Identity anchor = frozen universe JSONL (no brreg bulk CSV needed).
3. Website: registry URL first; if missing → bounded slug guesses; **always**
   through `apply_website_identity_gate` (publishable ≥ 0.9 score).
4. News: Google News RSS, two-tier exact gate (full name OR ≥2-token stem +
   possessive tolerance); single-token stems **never** match alone (precision).
5. Synthesis: deterministic template by default; LLM only via
   `LLM_PROVIDER=groq|openrouter` env; output must cite valid evidence ids.
6. Runner guarantees: budget (`--budget-seconds`), per-company isolation,
   checkpoint/resume, exit code = validation result.
7. Web: FastAPI + Jinja2 (no JS), JWT httpOnly cookie, per-user tenant (RLS),
   argon2 + TOTP, HMAC webhooks, SSRF-guarded preview. 30 security tests.

## 5. Lessons learned (cost us time — don't repeat)

- FastAPI **drops** headers/cookies set on the injected `Response` when the
  handler returns its own response → stage sid in `request.state`, set cookie in
  middleware.
- `hmac.new(key, …)` needs **bytes** — encode env secrets.
- PowerShell inline `python -c "…"` breaks on quotes → write a script file.
- `resource` module is Unix-only → guarded import for Windows.
- Editor tool: max ~6000 chars per edit; sentinel comments keep multi-part files sane.
- `pip-audit` exits 1 via stderr even when clean → read the message, not the code.
- Shared TestClient cookie jar leaks across tests → `client.cookies.clear()` in fixture.

## 6. Measured results (commit these numbers, not claims)

- `reports/smoke-100/report.json` (run smoke-002, live): 100/100 envelopes,
  all checks pass, wall 225.8 s, 846 requests, p50 19.98 s / p95 41.26 s,
  $0.00; available claims: roles 386, financials ~100/100 (revenue 71),
  subunits 76, official_website **11** (was 2 pre-discovery), descriptions 7.
- Tests: **149 passed** (104 starter + 30 security + 7 contract + 8 gate).
- pip-audit: **0 known vulnerabilities** (91 pinned packages).

## 7. Next moves (ranked by expected recall gain)

1. **Careers depth**: crawl `/career|karriere|jobb|stilling` links found on
   gated sites; extract posting titles/dates → "Working here" family.
2. **News for notable companies**: keep gate; add `publisher` + date filters;
   consider RSS `when:1y` + `site:`-free query variants A/B on dev set.
3. **Underenheter employees** merge into workforce claim (official subunits
   already carry `employees` — currently only surfaced as subunit rows).
4. **financial_history years → per-year revenue claims** (family depth).
5. **Brave discovery** behind `BRAVE_API_KEY` (transient, per source policy)
   for the ~93% of companies without registry websites — biggest single lever.
6. If GROQ key arrives: set `LLM_PROVIDER=groq`, re-run smoke, compare briefs.

## 8. Submission state

- v1 ready: run command in README, smoke report + 100-company manifest
  committed (`reports/smoke-100/`), docs complete (root set + docs/ playbook set).
- **Graphify**: `uv tool install graphifyy` (CLI at `C:\Users\91984\.local\bin`,
  add to PATH) → `graphify . --code-only --no-label` produced
  `graphify-out/` (graph.json 805 nodes / 2232 edges / 33 communities,
  GRAPH_REPORT.md, graph.html). God nodes: `create_app()`, `utc_now()`,
  `fetch_website()`, `run_batch()`, `_csrf_of()`. Rebuild after refactors with
  `graphify cluster-only . --no-label`; query with `graphify query "…"`.
  Docs need an LLM key (`--code-only` skips them).
- **Pending:** submission email (README checklist), then v2 work per §7.
- **v1 commit hash: `a5dd848376e33044f261a74f29280578a574db18`** (9 Oct 2026,
  120 files). Submission must cite this exact hash; revisions are new hashes
  (max 4 more, freeze 18 Oct).

