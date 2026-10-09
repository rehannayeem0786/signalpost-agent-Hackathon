# ARCHITECTURE

## 1. System overview

```
                 ┌──────────────────────────────────────────────────────────┐
 Builderr batch  │  scripts/run_batch.py   (THE one evaluator command)      │
 (org numbers) ─▶│  └─ norway_company_agent.runner.run_batch                │
                 │      ├─ universe.profiles_from_universe   (identity)     │
                 │      ├─ official.fetch_official_modules   (BRREG APIs)   │
                 │      ├─ website.fetch_website + identity.apply_*_gate    │
                 │      ├─ news.fetch_news                   (exact gate)   │
                 │      ├─ claims.build_claims                (fact↔evidence)│
                 │      ├─ synth.synthesize                   (Groq/Ollm…)  │
                 │      └─ batch.validate_envelopes + harness checks        │
                 └───────────┬──────────────────────────────┬───────────────┘
                             ▼                              ▼
                  out/envelopes.jsonl (1/input)    reports/<run>/report.json
                             │
                 ┌───────────▼───────────────────────────────────────────────┐
                 │  webapp (FastAPI + Jinja2)                                │
                 │  auth (argon2+TOTP+JWT httpOnly) ─ store.Store (SQLite)   │
                 │  /companies/:org · /research · /refresh (CSRF+RLS+rate)   │
                 └───────────────────────────────────────────────────────────┘
```

## 2. Source ladder (per playbook)

1. **Official registers** — frozen Builderr universe (identity anchor, SHA-256
   `1c89710e…f5a0384`) + live Brreg: entity, roller, regnskapsregisteret,
   underenheter, konsernstruktur (NLOD 2.0).
2. **Company-owned sources** — registry-listed website; if absent, bounded
   deterministic slug candidates (`guess_website_candidates`), each requiring
   the exact-entity gate; static HTML first (robots respected, SSRF-guarded),
   JSON-LD/OpenGraph/og tags via extruct, readable text via trafilatura.
3. **Permitted public feeds** — Google News RSS (headline-level, two-tier exact
   legal-name gate; publisher bodies never stored).
4. **Discovery-only** — search APIs (Brave) are candidates, never evidence; the
   slug guesser is likewise candidate generation gated before publication.

## 3. Data flow: one company

```
org# ─▶ frozen snapshot row ─▶ evidence.registry (+ accounting rule path)
     ─▶ live BRREG modules (financials, history, roles, group, locations)
     ─▶ website fetch ─▶ identity gate (score ≥ 0.9 publishable) ─▶ pages/socials/JSON-LD
     ─▶ news RSS ─▶ two-tier name gate ─▶ items (title/publisher/date/url)
     ─▶ build_claims: field → {value, availability, confidence, evidence_ids, period}
     ─▶ synthesize: brief over published claims only (evidence-id guard)
     ─▶ build_envelope: dual state vocabularies + run/identity/claims/evidence/
        changes/errors/operations  ─▶ validate ─▶ JSONL row (exactly one)
```

## 4. Envelope contract (superset, both vocabularies)

```jsonc
{
  "run_id": "...", "organisation_number": "810034882",
  "state": "complete",              // starter vocabulary (validated)
  "status": "available",            // harness vocabulary (6 legal states)
  "started_at": "...", "completed_at": "...",
  "modules": { "<m>": {"state": "...", "retry_count": 0, "final_timestamp": "..."} },
  "profile": { ...starter profile + evidence{module records}... },
  "run": {"run_id", "started_at", "completed_at", "terminal_status"},
  "identity": {"organisation_number", "legal_name", "legal_form", "municipality", "anchor"},
  "claims": [{"field","value","availability","confidence","evidence_ids","reporting_period"}],
  "evidence": [{"id","source_url","source_class","retrieved_at","content_sha256","reporting_period","claim_span"}],
  "changes": [{"field","old_value","new_value",...}],
  "errors": [{"module","error"}],
  "operations": {"requests","runtime_ms","third_party_cost_usd"}
}
```

## 5. Failure & budget model

- Every per-company step is exception-isolated; a crash maps to an honest
  module state, never to a missing row.
- Wall-clock `--budget-seconds` (default 3600): when the deadline passes, the
  remaining companies get registry-anchored envelopes with `not_applicable`
  deferred modules (status stays `available` if identity resolved).
- Checkpoint every N profiles (`--checkpoint-every`), `--resume` supported.
- Timed-out orgs are reported explicitly in the run report.

## 6. Storage & tenancy (web layer)

SQLite, WAL mode, all statements parameterized:

- `profiles(tenant_id, org, payload, content_sha256, updated_at)` PK(tenant, org)
- `snapshots(...)` content-addressed immutable history (idempotent upserts)
- `changes(...)` idempotency_key = H(tenant|org|field|old|new) ⇒ replay-safe
- `users(...)` argon2id hashes, sealed TOTP secrets (HMAC-derived key)
- `jobs(...)` research/refresh audit trail

Row-level security is enforced **in the data layer**: no function accepts a
query without its `tenant_id`. Postgres deployments should additionally set
`ENABLE ROW LEVEL SECURITY` policies mirroring these predicates (draft in
SECURITY.md §14).

## 7. Concurrency

ThreadPoolExecutor (default 8 workers) over companies; each company's official
fetches are sequential (polite to Brreg); store writes serialized by a module
lock. News/website fetches are bounded by per-request timeouts.

## 8. Extension points (strategy registry)

`MODULES` tuple in `webapp/app.py` and `--modules` in the runner gate every
family. New connectors must (1) register a stable name/version, (2) produce
evidence records with url/time/hash, (3) pass the identity gate, (4) pass
`promotion_gate` criteria in EVAL.md before becoming default.
