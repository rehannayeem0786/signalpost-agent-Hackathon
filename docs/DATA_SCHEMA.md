# DATA_SCHEMA — envelopes, claims, evidence

## Envelope (one JSONL row per input org number)

Top-level keys:

| Key | Meaning |
|---|---|
| `run_id`, `started_at`, `completed_at` | run identity/timing |
| `organisation_number` | 9-digit key (echoes the input) |
| `state` | starter vocabulary: `complete, not_applicable, not_found, blocked_policy, blocked_robots, source_error, budget_exhausted, submission_error` |
| `status` | harness vocabulary: `available, not_available, blocked, not_applicable, ambiguous, failed` |
| `modules.<m>` | per-module `{state, retry_count, final_timestamp}` |
| `profile` | full enriched profile incl. `evidence.<module>` records |
| `run` | `{run_id, started_at, completed_at, terminal_status}` |
| `identity` | `{organisation_number, legal_name, legal_form, municipality, anchor}` |
| `claims[]` | fact rows (below) |
| `evidence[]` | evidence rows (below) |
| `changes[]` | refresh diffs vs `--previous` profiles |
| `errors[]` | honest per-module errors (never a substitute for a row) |
| `operations` | `{requests, runtime_ms, third_party_cost_usd}` |

## Claim

```json
{"field": "revenue", "value": 12345000, "availability": "available",
 "confidence": 1.0, "evidence_ids": ["ev-financials"],
 "reporting_period": "2025"}
```

- `availability` ∈ the six harness states.
- `value` is `null` unless `availability == "available"` (never zero-for-missing).
- Field families (v1): registry identity (10+), accounting_obligation,
  financials (revenue, operating_result, annual_result, total_assets,
  total_debt, equity, reporting_period, available_filing_years),
  registered_role (one per active holder), registered_subunit (one per
  subunit), group_structure, website block (official_website, website_title,
  company_description, contact_phone, contact_email, registered_address,
  founding_date, social_profile_*, careers_page, news_page), recent_activity
  (one per news item), company_brief (synthesis).

## Evidence row

```json
{"id": "ev-financials", "source_url": "https://data.brreg.no/regnskapsregisteret/regnskap/810034882",
 "source_class": "official_annual_accounts", "retrieved_at": "2026-10-09T14:47:31Z",
 "content_sha256": "…", "reporting_period": "2025",
 "claim_span": "records[0].period=2025"}
```

Reserved ids: `ev-registry`, `ev-registry-live`, `ev-accounting-obligation`,
`ev-financials`, `ev-financial-history`, `ev-roles[-n]`, `ev-locations[-n]`,
`ev-group`, `ev-website[-title|-description|-careers|-news|-phone|-email]`,
`ev-social-<platform>`, `ev-jsonld-<field>`, `ev-news[-n]`, `ev-synthesis`.

## Profile (inside `profile`)

Starter-compatible: `organisation_number, name, legal_form, employees,
bankrupt, liquidating, municipality, municipality_number, industry_code,
industry_label, website, latest_submitted_accounts, evidence{module→record}`,
plus `run_metrics` on batch profiles.

Module record (from `evidence()`): `{field, status, source_type, source_class,
source_url, retrieved_at, value, as_of, note, content_sha256, source_row_key,
effective_at}` where `status ∈ {available, not_found, not_applicable,
not_fetched, source_error, blocked}`.

## Run report (`--report`)

`expected_count, emitted_envelopes, resolved_profiles, unresolved_*, timed_out_*,
modules, status_counts, available_claim_counts, registry{sha256, scanned…},
operations{wall_seconds, requests_total, p50_ms, p95_ms, third_party_cost_usd},
validation{passed, starter.checks, harness.checks}`.
