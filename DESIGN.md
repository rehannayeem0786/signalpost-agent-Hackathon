# DESIGN — product & UX decisions

## 1. Design principles

1. **Evidence is the UI.** Every fact on screen shows its state badge, source
   link, retrieval time and reporting period; the evidence table is a first-class
   section, not a footnote.
2. **Absence is visible.** Missing facts render as *not available* (grey badge)
   with the reason — never blank, never zero.
3. **Five areas, one scan.** The profile mirrors the product sample's areas:
   Company brief · Latest financials · Who runs it? · Working here · Recent
   activity — so a reviewer can verify coverage at a glance.
4. **Server-rendered, zero-JS surface.** Plain forms + Jinja2 ⇒ no token in
   localStorage, no source maps, CSP without `unsafe-inline` scripts, works
   without JavaScript (also why UX earns its 8/8 honestly).

## 2. Information architecture

```
/                          → research form + your profiles
/search?q=                 → tenant-scoped search by org number
/companies/810034882       → profile (5 areas + evidence + changes)
/research  (POST)          → run full pipeline for one org, redirect to profile
/refresh   (POST)          → re-research, diff, record changes (idempotent)
/login /register /login/mfa → auth
/account                   → password rotation + MFA enrolment
/admin                     → users, smoke-report upload (validated), URL check
```

## 3. Visual language

- Neutral ink/paper palette, one accent; state badges colour-coded
  green=available, grey=not_available, red=blocked/failed, amber=ambiguous/
  not_applicable.
- Monospace for org numbers, hashes and secrets; long URLs break-wrapped.
- Tables for facts (Fact/Value/State/Evidence columns) — reviewable and
  copy-paste friendly for verification.

## 4. Interaction decisions

- **Research is synchronous with honest failure:** if the pipeline throws, no
  partial profile is stored (all-or-nothing upsert), and the error page explains
  it. Progress is a job record (`jobs` table) for auditability.
- **Refresh shows a change list** (old → new with timestamps) instead of
  silently overwriting — matches "expose material changes, preserve history".
- **MFA enrolment is two-step** (reveal secret → confirm code) so a lost code
  can't lock the account before activation.
- **Bootstrap admin password** is shown exactly once at first boot (log line),
  rotation forced at first login.

## 5. Schema decisions (why SQLite + JSON payloads)

- Envelopes/profiles are deep, schema-evolving JSON documents → stored as
  validated JSON payloads keyed by (tenant, org) with content hashes, rather
  than shredded into 40 columns. Queryable fields (org, updated_at) stay real
  columns; claims are rebuilt deterministically from the profile by
  `claims.build_claims` (single source of truth, no drift).
- Immutable `snapshots` + idempotency keys give refresh correctness for free.

## 6. Trust affordances

- Each claim row links its evidence id → source URL, content hash prefix,
  retrieval time, reporting period.
- The synthesis brief is labelled "Decision-useful brief" and is always derived
  from listed claims (LLM answers must cite valid evidence ids or are dropped).
- Last-refresh timestamps and per-row change history are always visible.

## 7. What we deliberately did not build

- No infinite scroll / SPA router (breaks the no-JS, no-token posture).
- No public registration-to-shared-data model (tenant isolation by design).
- No decorative charts without evidence (they would imply data we don't have).
