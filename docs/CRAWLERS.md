# CRAWLERS — connectors, budgets, fallback rules

## Connectors (stable names = strategy registry)

| Name | Source | Budget / limits | Fallback |
|---|---|---|---|
| `registry_anchor` | Builderr universe JSONL(.gz) | one sequential scan | error ⇒ `ambiguous` envelope |
| `brreg_entity` | data.brreg.no/enheter/{org} | timeout 20 s, 3 attempts, backoff | `source_error` state |
| `brreg_financials` | regnskapsregisteret/{org} | timeout 20 s | `not_found` on 404 (never 0) |
| `brreg_history` | aarsregnskap/kopi/{org}/aar | ~30 req/min server limit honored | `not_found`/`source_error` |
| `brreg_roles` | enheter/{org}/roller | timeout 20 s | `not_found` |
| `brreg_group` / `brreg_subunits` | konsernstruktur, underenheter?size=1000 | timeout 20 s | `not_found` |
| `site_static` | company homepage + priority pages | robots.txt, SSRF guard, 2 MB/page, 15 s, same-registered-domain only | expired-TLS insecure fallback (recorded) |
| `site_slug_guess` | www.<slug>.no candidates | max 2 candidates, only when registry website missing | candidate must pass identity gate or discarded |
| `news_rss` | news.google.com/rss/search | 2 MB, 25 s, exact-title gate | `not_found` with rss_items count |
| `llm_synthesis` | Groq/OpenRouter (env-gated) | 25 s, temperature 0.1, max 400 tokens | deterministic template |

## Ladder rules
- Static HTML first; browser rendering only after a deterministic
  `js_fallback_candidate` completeness check (not enabled in v1).
- PDF/layout/OCR: deferred to v2 (`financial_history` → claims).
- Search providers: candidates only; provider output discarded after the
  accepted candidate is independently fetched (declared transient mode).

## Global outbound policy
- User-Agent: `SignalpostResearchAgent/1.0 (https://builderr.ai; bounded qualification run)`
- Every URL passes `assert_public_url` (scheme + DNS-resolved public IP), and
  again after each redirect; private/loopback/link-local/metadata blocked.
- robots.txt disallow ⇒ `blocked` (recorded), not silently ignored.
- Byte caps: homepage 2 MB, secondary 1 MB, RSS 2 MB.
- Batch wall-clock: `--budget-seconds` (default 3600); unfinished companies
  still emit registry-anchored envelopes.

## Retry policy
- 3 attempts with 0.4 s × 2^n backoff for transient network/5xx errors.
- 404/410: no retry (terminal `not_found`).
- Writes (store upserts): idempotent, safe to replay after crash/resume.
