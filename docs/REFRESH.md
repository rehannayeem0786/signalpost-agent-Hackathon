# REFRESH — scheduling, snapshots, diffs

## Model
Refresh is a **diff over preserved evidence**, never an overwrite.

1. Research produces a profile document whose `evidence.<module>` records carry
   `retrieved_at`, `content_sha256`, `source_url`, `as_of/effective_at`.
2. `Store.upsert_profile(tenant, profile)`:
   - writes the new payload keyed by (tenant, org) — content hash updated;
   - appends an immutable row to `snapshots` keyed by
     (tenant, org, content_sha256) → replaying the same snapshot inserts
     nothing (`INSERT OR IGNORE` ⇒ idempotent).
3. `diff_profile(previous, current)` walks `TRACKED_FIELDS` (name, legal form,
   employees, municipality, website, latest accounts, financial records, filing
   years, roles, subunits, site title/description/socials) and emits typed
   changes with old/new values, both sides' hashes and the current source.
4. `Store.record_changes` upserts with
   `idempotency_key = H(tenant|org|field|old|new)` ⇒ the same detected change
   is recorded exactly once across replays (verified by
   `test_refresh_idempotency_no_duplicate_changes`).

## Failure semantics
- A failed refresh **keeps** the last supported value and records a job
  `failed` with the error class; no change rows are written for unfetched
  modules (absence of evidence is not evidence of change).
- Missing → present transitions are `new_value` changes; present → missing is
  an explicit change to `null` with `not_available` state (not a deletion).

## Change vocabulary (for the UI and audit)
`new_role`, `closed_role`, `changed_employees`, `changed_financials`,
`new_subunit`, `changed_description`, `changed_website`, `new_filing`,
`changed_social` — emitted via the tracked-field name (`registry.employees`,
`roles.roles`, `financials.records`, …).

## Scheduling guidance (source volatility)
- Official annual accounts: refresh weekly (they change yearly).
- Registry identity/roles: refresh daily during official evaluation.
- Website/news: refresh per run (they are the volatile families).
Batch mode re-crawls whatever the module list contains; per-family schedules
are a v2 optimization gated by the promotion rules in EVAL.md.

## Web layer
`POST /refresh` re-runs the full pipeline for one org, diffs against the stored
profile, upserts, and records changes tenant-scoped; the profile page renders
the last ≤25 changes with timestamps.
