# PRD — Signalpost research agent & product

**Status:** v1 complete, iteration open until revisions close 18 Oct 2026.
**Owner:** competition entry (Builderr Signalpost, Round 1).

## 1. Problem

Buyers, employers, partners and investors in Norway need to understand a company
before they act: what it does, who leads it, where it operates, how its latest
filed numbers look, whether it is hiring, and what dated public activity exists
— with every fact traceable to a source. Official registers answer part of this;
web presence answers another part; neither is joined, verified for exact-entity
match, or kept current.

## 2. Goal & success metrics

Primary: **rank #1** on the Builderr Signalpost board (qualification bar 65/100).

| Rubric | Points | Target for v1 | How we earn it |
|---|---|---|---|
| Recall & coverage | 50 | maximize: cover ALL field families | official modules 100%, website discovery, news gate, careers/news pages |
| Precision & evidence | 30 | 30/30 — zero wrong-company publications | exact-entity gates, evidence spans, honest states |
| Decision-useful synthesis | 12 | 12/12 | evidence-bounded brief (LLM w/ guard, deterministic fallback) |
| UX & interaction | 8 | 8/8 | `/companies/:org`, `/research`, `/refresh`, evidence table |

Board context at build time (5 Oct 2026 review): 37 submissions, 0 qualified,
top score 60.80 — recall is the universal bottleneck (top recall ≈14/50).

## 3. Users & personas

1. **The evaluator (Builderr harness)** — machine consumer of envelopes; must
   receive exactly one terminal result per input within budget.
2. **The researcher (human)** — uses the web product to check a supplier,
   employer or partner; needs sources and dates visible per fact.
3. **The builder (us)** — needs fast, measurable iteration (strategy registry,
   promotion gates, cost/runtime telemetry).

## 4. Functional requirements

- **R1 Input contract** — accept any 9-digit Norwegian organisation number from a
  batch file at run time; never choose our own companies.
- **R2 Identity anchor** — resolve identity against the frozen 2025 universe
  snapshot (SHA-256 verified) and the live Brreg registry; 410 ⇒ drop cache.
- **R3 Evidence collection (field families)**
  - registry: name, form, addresses, municipality, industry, employees, status
  - financials: revenue, operating/annual result, assets, debt, equity, period,
    available filing years, accounting-obligation rule path
  - roles: board/management holders with dates
  - locations: registered subunits; group structure
  - website: title, description, contacts, socials, careers/news pages — only
    after the exact-entity gate
  - news: dated public mentions behind a two-tier exact-name gate
- **R4 Publication rules** — every claim carries evidence id(s); evidence rows
  carry source URL/class, retrieval time, content hash, span, reporting period;
  missing ⇒ `not_available` with null (never 0).
- **R5 One envelope per input** — states: `available | not_available | blocked |
  not_applicable | ambiguous | failed` (+ starter module states); budget-exhausted
  rows still emit a registry-anchored envelope.
- **R6 Refresh** — idempotent upsert against content-addressed snapshots;
  material changes recorded with old/new values; failed refresh keeps last
  supported value.
- **R7 Synthesis** — 3–4 sentence brief from published claims only; LLM output
  must cite valid evidence ids or it is dropped; deterministic fallback.
- **R8 Web product** — register/login (+TOTP MFA), research/refresh jobs,
  profile pages with sources, admin uploads (validated), webhook receiver.

## 5. Non-functional requirements

- Reproducible: pinned deps, one command, clean-machine install.
- Budget-aware: fixed wall-clock budget; per-source timeouts; checkpoints.
- Safe outbound: SSRF guard (public hosts only), robots respected, per-domain
  budgets, secure-by-default TLS with a recorded insecure-TLS fallback.
- Security: see SECURITY.md (full checklist + test coverage).
- Cost: declared per run; official run target ≈ $0.00 without LLM keys.

## 6. Out of scope (v1)

- Browser rendering (Playwright) — static-first ladder retained as a strategy.
- Prohibited platforms (LinkedIn/Meta/Glassdoor/Indeed direct scraping).
- Precomputed profile submission (explicitly not scored).

## 7. Acceptance (v1 done when)

1. `pytest -q` green (contract + gates + security).
2. 100-company live smoke: 100/100 envelopes, all contract checks pass,
   report committed.
3. Docs set complete (this file, ARCHITECTURE, RULES, DESIGN, TASKS, MEMORY).
4. pip-audit reports no known vulnerabilities.
