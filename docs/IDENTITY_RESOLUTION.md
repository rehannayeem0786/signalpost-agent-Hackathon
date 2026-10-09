# IDENTITY_RESOLUTION — candidate and publication gates

## Principle
The organisation number is the only stable key. A brand, domain or social
handle is a *candidate* until it resolves back to the exact entity.

## Evidence graph we walk

```
legal entity (org#, frozen snapshot)
  → official site candidate (registry URL | bounded slug guess)
    → page claims org# or strong corroboration (legal name + address/phone/leadership)
      → public brand/aliases (gated social links from the verified domain)
        → leaders bridge (official role ↔ public profile)   [v2, discovery only]
```

## Gate: `assess_website_identity` (vendored from starter, unmodified)

Score composition (representative): org# present on page → 1.0; full legal-name
match in structured/text content → 0.95; strong corroboration combos → 0.85–0.95;
weak/parent-brand similarity → ≤0.65.

- `score ≥ 0.9` ⇒ status `exact` ⇒ **publishable**
- `0.8 ≤ score < 0.9` ⇒ `review` ⇒ withheld in v1 (no silent publishes)
- `< 0.8` ⇒ `related_or_uncertain` ⇒ withheld
- Social links inherit the gate (`publishable ≥ 0.9`) and require a canonical
  company path (`/company/<slug>`, `@handle`, `/channel/…`).

## Gate: news exact-name (our implementation)

- Tier 1: full legal-name token window (incl. legal form) in the headline,
  contiguous, at start or after allowed predecessors (av/fra/til/…).
- Tier 2: stem window (legal-form tokens removed) **only if ≥ 2 tokens**.
- Norwegian possessive tolerance: `want+s|ens|es` accepted (≥4 char tokens).
- Single-token stems never match alone (e.g. "Equinors årsrapport" without
  "ASA" does not pass) — precision-first per the brief: *"better to miss some
  information than publish it under the wrong company."*

## Failure handling
- Gate fails ⇒ content withheld, website claim gets `ambiguous` with an
  explanatory note; the profile itself stays `available` on official facts.
- Registry row missing ⇒ whole envelope `ambiguous` (identity could not be
  confirmed), claims all non-available.

## Measured behaviour (v1 smoke, 100 companies)
- Storebrand-subsidiary-on-parent-domain correctly blocked (score 0.3).
- Expired-cert sites recovered via recorded insecure-TLS fallback, then gated.
- Slug discovery published 4 extra sites; zero wrong-company publishes observed
  in manual review of the 11 published websites.
