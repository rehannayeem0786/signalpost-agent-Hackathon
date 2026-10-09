# Graph Report - Build An Agent Hack  (2026-10-09)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 805 nodes · 2232 edges · 33 communities (29 shown, 4 thin omitted)
- Extraction: 99% EXTRACTED · 1% INFERRED · 0% AMBIGUOUS · INFERRED: 26 edges (avg confidence: 0.88)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- Community 0
- Community 1
- Community 2
- Community 3
- Community 4
- Community 5
- Community 6
- Community 7
- Community 8
- Community 9
- Community 10
- Community 11
- Community 12
- Community 13
- Community 14
- Community 15
- Community 16
- Community 17
- Community 18
- Community 19
- Community 20
- Community 21
- Community 22
- Community 23
- Community 24
- Community 25
- Community 26
- Community 27
- Community 28
- Community 29
- Community 30
- Community 31

## God Nodes (most connected - your core abstractions)
1. `ExternalFootprintTests` - 28 edges
2. `create_app()` - 26 edges
3. `utc_now()` - 23 edges
4. `fetch_website()` - 22 edges
5. `run_batch()` - 19 edges
6. `_csrf_of()` - 17 edges
7. `extract_profile()` - 15 edges
8. `extract_page_event()` - 15 edges
9. `check_csrf()` - 15 edges
10. `IdentityStore` - 14 edges

## Surprising Connections (you probably didn't know these)
- `test_refresh_idempotency_no_duplicate_changes()` --uses--> `Store`  [INFERRED]
  tests/test_contract.py → src/norway_company_agent/store.py
- `RefreshTests` --uses--> `SnapshotFetcher`  [INFERRED]
  tests/test_poc.py → src/norway_company_agent/snapshots.py
- `_store()` --uses--> `Store`  [INFERRED]
  tests/test_security.py → src/norway_company_agent/store.py
- `main()` --uses--> `SignalpostWebsiteSpider`  [INFERRED]
  scripts/run_scrapy_websites.py → src/norway_company_agent/scrapy_crawler.py
- `materialize()` --uses--> `SnapshotFetcher`  [INFERRED]
  scripts/run_refresh_replay.py → src/norway_company_agent/snapshots.py

## Import Cycles
- None detected.

## Communities (33 total, 4 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.05
Nodes (52): discover_one(), discovery_identity(), job_company_urls(), main(), normalized_full_name(), official_site_aliases(), parse_exact_typeahead(), profile_leaders() (+44 more)

### Community 1 - "Community 1"
Cohesion: 0.06
Nodes (34): main(), evidence_terminal_state(), profile_complete_for_modules(), profiles_from_bulk(), read_organisation_inputs(), read_organisation_numbers(), terminal_envelope(), validate_envelopes() (+26 more)

### Community 2 - "Community 2"
Cohesion: 0.07
Nodes (23): error_page_event(), extract_page_event(), merge_profile_events(), missing_seed_error_events(), PublicNetworkMiddleware, SignalpostWebsiteSpider, assert_public_url(), _extraction_state() (+15 more)

### Community 3 - "Community 3"
Cohesion: 0.11
Nodes (40): check_csrf(), _client_ip(), create_app(), account(), admin_page(), admin_upload(), builderr_webhook(), change_password() (+32 more)

### Community 4 - "Community 4"
Cohesion: 0.09
Nodes (21): fetch_json(), FetchResult, _utc_now(), accounting_obligation_assessment(), _classified(), _fetch_history(), fetch_official_modules(), _get() (+13 more)

### Community 5 - "Community 5"
Cohesion: 0.09
Nodes (11): development_score(), run_company_control(), strategy_history(), strategy_order(), aggregate_footprint(), _as_datetime(), _host(), publishable_observation() (+3 more)

### Community 6 - "Community 6"
Cohesion: 0.08
Nodes (18): brave_search(), main(), percentile(), read_jsonl(), write_jsonl(), enrich(), build_company_search_query(), choose_search_candidate() (+10 more)

### Community 7 - "Community 7"
Cohesion: 0.13
Nodes (14): plan_external_tasks(), add(), _task_id(), deterministic_extension_sample(), deterministic_financial_filer_sample(), deterministic_sample(), deterministic_website_audit_sample(), financial_filer_eligible() (+6 more)

### Community 8 - "Community 8"
Cohesion: 0.12
Nodes (13): test_log_redaction_strips_secrets(), test_webhook_rejects_bad_signature_accepts_good(), csrf_pepper(), csrf_validate(), install_log_redaction(), new_csrf_token(), RedactingFilter, _secret() (+5 more)

### Community 9 - "Community 9"
Cohesion: 0.17
Nodes (13): classify(), label_token_ids(), load_model(), main(), normalize_generated_label(), read_jsonl(), write_jsonl(), aggregate_company_sentiment() (+5 more)

### Community 10 - "Community 10"
Cohesion: 0.18
Nodes (12): main(), main(), read_jsonl(), main(), build(), main(), main(), observation() (+4 more)

### Community 11 - "Community 11"
Cohesion: 0.17
Nodes (4): Evidence, utc_now(), _connect(), Store

### Community 12 - "Community 12"
Cohesion: 0.11
Nodes (12): _login(), _reset_limiter(), _sid_csrf(), _store(), test_bola_other_tenant_cannot_read_profile(), test_login_rate_limit_triggers(), test_sql_injection_login_rejected(), test_store_parameterized_lookup() (+4 more)

### Community 13 - "Community 13"
Cohesion: 0.18
Nodes (8): test_bootstrap_admin_has_random_password_and_must_rotate(), test_password_hashing_is_argon2_and_verifies(), _connect(), IdentityStore, _now(), hash_password(), needs_rehash(), verify_password()

### Community 14 - "Community 14"
Cohesion: 0.21
Nodes (9): answer_profile(), _claim(), _compare(), _latest_financial(), _numeric_operator(), parse_screen_query(), screen_profiles(), _screen_value() (+1 more)

### Community 15 - "Community 15"
Cohesion: 0.21
Nodes (8): main(), read_jsonl(), terminal_events_for_run(), write_jsonl(), domain_request_summary(), latency_summary(), peak_rss_bytes(), percentile()

### Community 16 - "Community 16"
Cohesion: 0.17
Nodes (3): write_jsonl(), main(), materialize()

### Community 17 - "Community 17"
Cohesion: 0.28
Nodes (12): _register(), test_bola_web_404_for_other_tenant_profile(), test_csrf_logout_requires_token(), test_csrf_missing_token_rejected(), test_csrf_wrong_token_rejected(), test_mfa_enable_and_verify_flow(), test_non_admin_cannot_access_admin_pages(), test_password_policy_enforced_endpoint() (+4 more)

### Community 18 - "Community 18"
Cohesion: 0.27
Nodes (11): candidate_score(), main(), meaningful_name_tokens(), normalize_company(), normalized_phone(), read_jsonl(), registered_domain(), result_hash() (+3 more)

### Community 19 - "Community 19"
Cohesion: 0.21
Nodes (10): exact_title_match(), guess_website_candidates(), test_full_legal_name_matches_headline(), test_generic_word_company_not_matched(), test_parent_brand_does_not_claim_subsidiary(), test_possessive_stem_matches_two_token_company(), test_reversed_or_partial_words_do_not_match(), test_single_token_stem_never_matches_alone() (+2 more)

### Community 20 - "Community 20"
Cohesion: 0.22
Nodes (6): build(), compact(), normalize_independent_score(), qualification_copy(), read_jsonl(), PrototypeTests

### Community 21 - "Community 21"
Cohesion: 0.26
Nodes (5): deterministic_brief(), _guard(), _provider(), _record(), synthesize()

### Community 22 - "Community 22"
Cohesion: 0.42
Nodes (5): main(), empty_workspace(), load_workspace(), record_screen(), save_workspace()

### Community 23 - "Community 23"
Cohesion: 0.44
Nodes (7): enrichment_components(), foundation_components(), main(), module_present(), read_jsonl(), score_rows(), summarize()

### Community 24 - "Community 24"
Cohesion: 0.28
Nodes (3): main(), ratio(), read_jsonl()

### Community 25 - "Community 25"
Cohesion: 0.32
Nodes (5): test_jwt_alg_confusion_blocked(), test_jwt_rejects_tampered_token(), decode_token(), issue_token(), jwt_secret()

### Community 26 - "Community 26"
Cohesion: 0.43
Nodes (5): domain(), main(), norm(), read_jsonl(), utc_now()

### Community 27 - "Community 27"
Cohesion: 0.52
Nodes (4): _derive_key(), jwt_fallback_secret(), _open_secret(), _seal_secret()

### Community 28 - "Community 28"
Cohesion: 0.52
Nodes (5): capped(), load(), main(), ratio(), rows()

## Knowledge Gaps
- **4 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `ExternalFootprintTests` connect `Community 5` to `Community 0`, `Community 6`, `Community 7`?**
  _High betweenness centrality (0.047) - this node is a cross-community bridge._
- **Should `Community 0` be split into smaller, more focused modules?**
  _Cohesion score 0.051756785188302123 - nodes in this community are weakly interconnected._
- **Why does `create_app()` connect `Community 3` to `Community 12`?**
  _High betweenness centrality (0.023) - this node is a cross-community bridge._
- **Should `Community 1` be split into smaller, more focused modules?**
  _Cohesion score 0.05555555555555555 - nodes in this community are weakly interconnected._
- **Why does `utc_now()` connect `Community 11` to `Community 0`, `Community 1`, `Community 2`, `Community 4`, `Community 6`, `Community 9`, `Community 22`?**
  _High betweenness centrality (0.023) - this node is a cross-community bridge._
- **Should `Community 2` be split into smaller, more focused modules?**
  _Cohesion score 0.07086247086247087 - nodes in this community are weakly interconnected._
- **Should `Community 3` be split into smaller, more focused modules?**
  _Cohesion score 0.10957910014513789 - nodes in this community are weakly interconnected._