# LIMITATIONS — known gaps, licences, source restrictions

## Coverage gaps (honest, scored as missing — never filled with guesses)
- ~86% of universe rows carry no registry website; slug discovery recovers a
  minority (v1: 11/100 published vs 7 registry-provided). No search API key is
  configured, so candidate discovery is bounded to deterministic guesses.
- Public annual accounts do not exist for every entity (ENK and others) —
  `revenue` available for 71/100 in the smoke batch; absence is published as
  `not_available`, never 0.
- News RSS returns nothing for companies that make no headlines (most small
  firms) — `rss_items=0` is recorded in the note so the state is auditable.
- Careers/jobs depth is limited to links discovered on gated sites in v1
  (no external job-board connectors enabled).
- Browser-rendered JS shells are recorded as `js_fallback_candidate` but not
  rendered in v1 (static-first ladder).

## Licence / rights posture
- Brreg + Regnskapsregisteret: **NLOD 2.0** open data; person data used only in
  company-centric role context; birth dates never stored.
- Google News RSS: headline metadata only (title/publisher/date/link); article
  bodies are not fetched or stored; if publisher terms for the access pattern
  change, the connector flips to `blocked` (declared in CRAWLERS.md).
- Search providers (Brave et al.): candidates only, transient, never evidence —
  enabled only with a key and a declared plan that permits the access pattern.
- Restricted platforms (LinkedIn, Meta, Glassdoor, Indeed): **not used**; no
  unofficial clients. Any future experiment must be declared and cannot be the
  sole support for a published claim.
- Company-owned sites: fetched read-only under our declared UA, within robots
  and byte/time budgets; public pages only.
- Starter-kit code is vendored as provided by Builderr for entrant use
  (clean-room verified by Builderr, 24 Aug 2026).

## Security / ops caveats
- SQLite data layer enforces tenant isolation in code (Postgres RLS draft in
  SECURITY.md for production).
- Rate limiter is in-process (single-node); a multi-node deployment needs a
  shared store.
- Expired-TLS fallback disables certificate verification for that one fetch —
  recorded in evidence (`insecure_tls: true` + note) so auditors can exclude
  those claims if policy requires.

## Cost & reproducibility
- Official run cost without LLM keys: **$0.00** third-party (public endpoints
  + RSS). With `LLM_PROVIDER=groq`: ≈$0.0006/company for the synthesis call.
- Pinned requirements (91 packages), pip-audit clean (9 Oct 2026), one command
  to reproduce any committed report.
