# RULES — challenge rules of engagement & compliance map

Sources of truth: the [challenge page](https://builderr.ai/challenges/signalpost),
the [evaluation contract](https://builderr.ai/docs/signalpost-evaluation-harness.md),
the [participant brief](https://builderr.ai/starter-briefs/signalpost.md), the
[source policy](https://builderr.ai/starter-briefs/signalpost-sources.md) and the
[agent playbook](https://builderr.ai/starter-briefs/signalpost-agent-playbook.md).
If our summary conflicts with those, the challenge page wins.

## 1. The hard rules and how this repo satisfies them

| Rule | Our compliance |
|---|---|
| One terminal envelope per supplied company, always | `runner.run_batch` exception-isolates per company; budget-exhausted rows still emit; contract tests assert no drops |
| Distinct states (`available/not_available/blocked/not_applicable/ambiguous/failed`) | emitted as `status`, plus starter `state` vocabulary for module-level validation |
| Never pick our own companies | batch file is the only input; `--organisations` required |
| No fabricated financials / wrong-company publication | values only from official endpoints or gated site content; missing ⇒ `not_available` null; identity gates tested |
| Claim-level source, retrieval time, reporting period | `claims.evidence_ids` → `evidence[]` rows with url/retrieved_at/content_sha256/span/period; contract tests enforce |
| Missing ≠ zero | `build_claims` writes null + state; contract test `test_missing_values_never_zero` |
| Idempotent refresh, prior snapshots preserved | content-addressed `snapshots` + idempotency keys; `test_refresh_idempotency_no_duplicate_changes` |
| Reproducible setup, pinned deps, one command | `requirements.txt` + README one-command + clean-venv verified |
| Declared source rights, server-side secrets, safe URL handling | this file §2–4, SECURITY.md, docs/LIMITATIONS.md |
| Fixed time/resource budget | `--budget-seconds`, per-request timeouts, workers cap; report records p50/p95 |
| Revisions: 1 initial + 4 commit hashes by **18 Oct** | versioning plan in TASKS.md |
| Submit by email to submit@builderr.ai | checklist in README |

## 2. Source rights (summary of the source policy)

- **Allowed:** Brreg/Regnskapsregisteret NLOD 2.0 endpoints; company-owned
  sites whose robots permit our UA; official/licensed platform APIs; public
  pages whose terms permit the access pattern; Google News RSS headlines for
  exact-name discovery (headline metadata only, publisher bodies not stored).
- **Candidate-only (never evidence):** search results, slug guesses.
- **Prohibited and not used:** unofficial LinkedIn/Meta/Glassdoor/Indeed
  scrapers; search-rank snippets as claim support; publishing parent/brand/
  franchise content under a subsidiary's identity.
- Group/parent/sister relationships are labelled, never collapsed.

## 3. Secrets & outbound safety

- All keys (GROQ/OPENROUTER/JWT/CSRF/WEBHOOK/SESSION) come from environment
  variables, minimum 32 chars; no key is committed (`.gitignore` covers `.env`);
  keys never enter templates, envelopes or logs (redaction filter + tests).
- Outbound requests: `assert_public_url` blocks private/loopback/link-local/
  metadata hosts, validates every redirect hop; robots.txt respected; byte and
  time limits; `file://` and non-HTTP schemes rejected.

## 4. Integrity & honesty rules we impose on ourselves

1. Abstention over invention: an uncertain match returns `ambiguous` or
   `not_available`, never a best guess.
2. Evidence before volume: no claim without a source row.
3. Measured claims only: scores/metrics in docs come from committed reports.
4. Freezes before official runs: dependency lock, module list, gates and
   thresholds change only between versions; hidden scores never tune a frozen
   version.
5. Declared costs: report includes `third_party_cost_usd` per run.

## 5. Timeline & versions

| Milestone | Date |
|---|---|
| Round 1 window | 23 Aug – 21 Oct 2026 |
| v1 submission (this repo) | 9 Oct 2026 |
| Revisions close (4 more commit hashes) | 18 Oct 2026 |
| Final close | 21 Oct 2026 |
| Qualification bar | official run ≥ 65/100 |
