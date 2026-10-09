# Signalpost research agent

An agent that turns a **Norwegian organisation number** into an evidence-backed
company profile: official identity, filed financials, registered leadership,
locations, verified website facts, job postings and dated public activity —
**every fact linked to a source** with retrieval time and reporting period,
honest availability states, and an idempotent refresh loop.

Competition entry for the [Builderr Signalpost challenge](https://builderr.ai/challenges/signalpost)
($2,500 · closes 21 Oct 2026 · qualifies at ≥65/100).

## Why it scores

The live board shows every strong entry saturating *evidence* and *synthesis*
but stalling on **recall** (the 50-point dimension). This system is built to
cover **all 7 information families per company** while keeping wrong-company
publications at **zero**:

| Family | Source | Gate |
|---|---|---|
| Identity | frozen Builderr universe (SHA-256 verified) + live Brreg | org-number anchor |
| Financials | Regnskapsregisteret (revenue, result, assets, equity, filing years) | official endpoints only |
| Leadership | Brreg roller (board/management) | official endpoints only |
| Locations | registered subunits + workforce sum | official endpoints only |
| Website | registry site or bounded slug candidates → crawl | **exact-entity gate (score ≥ 0.9)** |
| Hiring | gated careers page → job-posting extraction | robots + SSRF guarded |
| News | Google News RSS | **two-tier exact legal-name gate** |

A wrong-company match can disqualify a run, so uncertain matches return
`ambiguous` / `not_available` — never a guess, never a fabricated zero.

## The one evaluator command

```bash
python scripts/run_batch.py \
  --organisations <batch.jsonl> \
  --universe data/signalpost-company-universe-2025.jsonl.gz \
  --profiles-output out/profiles.jsonl \
  --output out/envelopes.jsonl \
  --report out/report.json \
  --run-id run-001 --expected-count <N>
```

Input: JSON/JSONL/text list of 9-digit organisation numbers (Builderr supplies
the official batch). Output: **exactly one terminal JSONL envelope per input**
(dual state vocabularies: `available | not_available | blocked |
not_applicable | ambiguous | failed` plus per-module states) + a
machine-readable report. Exit code 0 only when every contract check passes.

## Setup (reproducible, pinned)

```bash
git clone https://github.com/rehannayeem0786/signalpost-agent-Hackathon
cd signalpost-agent-Hackathon
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
curl -LO https://builderr.ai/signalpost-company-universe-2025.jsonl.gz
# place it at data/signalpost-company-universe-2025.jsonl.gz
cp .env.example .env && python scripts/gen_secrets.py   # fill .env secrets
python scripts/run_batch.py ...                         # the command above
```

Optional LLM synthesis (evidence-bounded; deterministic fallback without keys):

```bash
LLM_PROVIDER=groq, openrouter      # ordered provider preference list
GROQ_API_KEY=...  OPENROUTER_API_KEY=...
# model fallback lists are built in (openai/gpt-oss-120b → qwen3.8-27b → …)
```

## Web product (UX layer)

```bash
python -m uvicorn webapp.app:app --port 8000
```

- **Live research jobs** — step-by-step progress page (zero-JS meta refresh)
- **Profile pages** — 5 sections, every fact with source + date, **coverage
  meter** (7 families), **exact-entity gate badge**, refresh with change history
- **One-click envelope export** — `/companies/:org/envelope.json` downloads the
  exact competition artifact for verification
- Routes per the challenge interface: `/companies/:organisation_number`,
  `/research`, `/refresh`; landing page with sample companies

## Verification (run these yourself)

```bash
python -m pytest tests -q        # 168 passed: contract + gates + security + features
```

- Committed smoke test: `reports/smoke-100/report.json` — **100/100 envelopes,
  all contract checks passed**, 226 s wall, 846 requests, $0.00 third-party cost
  (batch manifest: `reports/smoke-100/companies.jsonl`)
- `pip-audit -r requirements.txt` → **no known vulnerabilities** (91 pinned packages)

## Security & source-rights declaration (summary)

- **SQLi/XSS/CSRF**: parameterized SQL everywhere; Jinja autoescape + strict CSP;
  peppered double-submit CSRF on every POST; `SameSite=Strict` httpOnly session
  cookie (JWT, HS256, env-secret ≥32 chars) — **no token in browser storage**
- **AuthN/AuthZ**: argon2id passwords, optional TOTP MFA, server-side role
  checks, per-user tenant row-level scoping (BOLA-tested), rate-limited
  credential endpoints, random bootstrap admin (forced rotation, no defaults)
- **Uploads**: extension allowlist + 2 MB cap + content sniffing before write
- **SSRF**: public-host-only fetch guard re-validated on every redirect hop;
  robots.txt respected; byte/time budgets; webhooks HMAC-SHA256 verified
- **Logs**: secrets redacted; `.env` gitignored and never committed; keys are
  server-side only and never rendered into templates or envelopes
- **Source rights**: Brreg/Regnskapsregisteret under NLOD 2.0; company-owned
  sites fetched read-only within robots; Google News RSS headline metadata only
  (no article bodies); search/slug guesses are candidates, never evidence;
  prohibited platforms (LinkedIn/Meta/Glassdoor/Indeed) are not used
- **Cost declared**: ≈$0.00/official run without LLM keys; ≈$0.0014/company
  with synthesis (~$1.40 per 1,000-company batch)

## Refresh & reproducibility


Re-running the same snapshot is idempotent: content-addressed SQLite snapshots
+ change idempotency keys mean a refresh **never creates duplicate records or
false changes**, preserves prior evidence, and exposes material changes with
old/new values (covered by `test_refresh_idempotency_no_duplicate_changes`).
Pinned dependencies + one command reproduce any committed report.

## Repository layout

```
src/norway_company_agent/   agent core (official modules, crawler, identity
                            gates, claims<->evidence, news, LLM synthesis,
                            store, batch runner)
scripts/run_batch.py        THE one evaluator command
scripts/gen_secrets.py      .env secret generator
webapp/                     secure FastAPI product (auth, MFA, jobs, profiles)
tests/                      168 tests: contract, publication gates, security,
                            product features
reports/smoke-100/          committed 100-company smoke report + batch manifest
requirements.txt            91 pinned dependencies (audit-clean)
.env.example                environment template (real .env is gitignored)
```


