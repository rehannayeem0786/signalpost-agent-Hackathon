# Signalpost research agent — competition entry

An agent that turns a Norwegian organisation number into an evidence-backed
company profile: official identity, filed financials, registered leadership,
locations, verified website facts, and dated public activity — every fact
linked to a source with retrieval time and reporting period, honest
availability states, and an idempotent refresh loop.

Built for the [Builderr Signalpost challenge](https://builderr.ai/challenges/signalpost)
($2,500 · closes 21 Oct 2026 · qualify at 65/100).

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

Input: a JSON/JSONL/text list of 9-digit organisation numbers (Builderr supplies
the official batch at run time). Output: exactly one terminal JSONL envelope per
input company, plus a machine-readable run report. Exit code 0 only when every
contract check passes.

## Setup (reproducible, pinned)

```bash
git clone <repo> && cd <repo>
python3.12 -m venv .venv            # Python 3.12+ required
.venv/bin/pip install -r requirements.txt
curl -LO https://builderr.ai/signalpost-company-universe-2025.jsonl.gz
# place it at data/signalpost-company-universe-2025.jsonl.gz
python scripts/run_batch.py ...      # the one command above
```

Optional LLM synthesis (evidence-bounded; deterministic fallback without keys):

```bash
export LLM_PROVIDER=groq            # or openrouter
export GROQ_API_KEY=...             # / OPENROUTER_API_KEY=...
```

Keys are read server-side only, never emitted into outputs or templates.

## Local verification (offline, no keys, no network)

```bash
pip install -r requirements.txt
python -m pytest tests -q           # 149 tests: contract + gates + security
```

The committed smoke test: `reports/smoke-100/report.json` — 100/100 envelopes,
all contract checks passed, ~226 s wall, 846 requests, $0.00 third-party cost.

## Web product (UX layer)

```bash
python scripts/gen_secrets.py       # paste into .env
python -m uvicorn webapp.app:app --port 8000
```

Preferred routes per the challenge interface: `/companies/:organisation_number`,
`/research`, `/refresh`. Session JWT lives only in an httpOnly cookie (never
localStorage); every POST is CSRF-protected; every row is tenant-scoped
server-side. Full matrix: [SECURITY.md](SECURITY.md).

## Repository map

| Path | Purpose |
|---|---|
| `src/norway_company_agent/` | agent core: official modules, crawler, gates, claims, runner |
| `scripts/run_batch.py` | the single evaluator command |
| `webapp/` | secure FastAPI product (auth, MFA, research/refresh) |
| `tests/` | 149 contract, gate and security regression tests |
| `reports/smoke-100/` | committed 100-company smoke-test report |
| `docs/` | agent policy, crawlers, identity, schema, refresh, eval, limits |
| `PRD.md` `ARCHITECTURE.md` `RULES.md` `DESIGN.md` `TASKS.md` `MEMORY.md` | project docs |

## Submission checklist (submit@builderr.ai)

- [x] repository URL + exact commit hash
- [x] 100-company smoke-test report (`reports/smoke-100/report.json`)
- [x] one run command (above)
- [x] pinned dependencies (`requirements.txt`) + reproducible setup
- [x] models/APIs used: optional Groq/OpenRouter for synthesis only (deterministic fallback), official BRREG/NLOD endpoints, Google News RSS
- [x] expected cost per official batch: ≈ $0.00 without LLM keys; ≈$0.005/company with Groq synthesis
- [x] source rights + secrets + safe URL handling declared: `RULES.md`, `SECURITY.md`, `docs/LIMITATIONS.md`
