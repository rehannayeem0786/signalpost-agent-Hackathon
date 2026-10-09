# EVAL — corpus split, metrics, thresholds

## Corpus discipline
- **Public universe (411,160)** = development ground. The 100-company smoke
  batch is deterministic (`select_entry_batch.py --seed 20260823`).
- **Hidden official batches** = the exam; never tune against them.
- Freeze before each official run: dependency lockfile, module list, gate
  thresholds, prompts/models, source allowlist, budgets.

## Metrics (from the evaluation contract — measured in the run report)
- exact-company precision & wrong-company publications (hard gate)
- per-field precision / recall / coverage; coverage = 70% company recall +
  30% claim recall per external field family
- evidence-span validity (every published claim → source row)
- crawl completion, refresh correctness, false-change rate
- cost per company, request count, p50/p95 runtime
- abstention reported separately (cannot satisfy coverage)

## Local proxies we can compute today
```bash
python -m pytest tests -q                  # 149 invariants (contract+gates+security)
python scripts/run_batch.py … --report …   # per-family available_claim_counts
python scripts/diag_websites.py out/<run>-envelopes.jsonl   # gate outcomes
python scripts/diag_news.py    out/<run>-envelopes.jsonl    # news gate outcomes
```

## Promotion gate (challenge → default, per learning harness)
A challenger strategy is promoted only when ALL hold:
1. zero new material wrong-company publications (manual review of publishes);
2. supported-claim precision does not fall;
3. evidence completeness stays 100% for published material claims;
4. coverage/recall improves on the development batch (declare a minimum, e.g.
   +3 companies with ≥1 new available family claim);
5. runtime and cost stay within the official budget.

Otherwise: keep the previous strategy, record the decision here.

## v1 measured baseline (run smoke-002, 9 Oct 2026)
- 100/100 envelopes, all contract checks pass, wall 225.8 s, 846 requests,
  p50 19.98 s / p95 41.26 s, $0.00.
- available claims: roles 386 · financial family ~100/100 (revenue 71) ·
  subunits 76 · official_website 11 · description 7 · contacts 3 · news 0.
- News = 0 on this batch: small firms produce no RSS items (verified
  `rss_items=0` for sampled companies) — not a gate defect (gate passes 3/10
  on a known-newsworthy control, `scripts/diag_news_one.py EQUINOR ASA`).

## Next experiments (in promotion order)
1. Careers-page depth on gated sites (Working-here family).
2. Brave discovery behind `BRAVE_API_KEY` for the 93% without registry sites.
3. Underenheter employees merged into workforce claims.
4. `financial_history` → per-year revenue claims.
