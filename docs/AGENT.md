# AGENT — research & abstention policy

## Mission
Turn an org number into a decision-useful, source-linked profile without ever
publishing a fact under the wrong company.

## Research order (deterministic ladder)
1. Frozen universe row (identity anchor, SHA-256 verified)
2. Live Brreg: entity → roller → regnskapsregisteret → underenheter → konsernstruktur
3. Registry-listed website (or bounded slug candidates) behind the exact-entity gate
4. Google News RSS behind the two-tier exact-name gate
5. (Optional, key-gated) LLM synthesis over published claims only

## Publication gates (in order, all must hold)
1. Organisation number resolved in the frozen snapshot → else `ambiguous`
2. For site/brand content: `identity_assessment.score ≥ 0.9` (`exact`) → else withhold
3. For news: full legal name window OR ≥2-token stem window (+ possessive tolerance)
4. Claim has an evidence row with url + retrieved_at + content_sha256 (+ period when relevant)
5. Value is never fabricated: missing ⇒ `not_available` + `null`

## Abstention rules
- Uncertain identity → `ambiguous`, publish nothing from that source.
- Source refused / robots → `blocked` (state recorded, profile unaffected).
- Endpoint 404/410 → `not_available` (evidence of no returned record, NOT zero).
- Timeout/error → `failed` for the module; last supported values preserved.
- LLM response citing unknown evidence ids → dropped, deterministic brief published.

## Non-negotiables
- Never store birth dates from role records; person data only in company-centric roles.
- Never treat search results or slug guesses as evidence.
- Never collapse parent/subsidiary/brand relationships.
- One envelope per input, always — including when the run breaks.
