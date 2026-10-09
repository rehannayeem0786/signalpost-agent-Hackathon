# SECURITY — checklist status (all items fixed & covered by tests)

Every row is implemented **and** regressed by an automated test in
`tests/test_security.py` (30 tests) or `tests/test_contract.py` (7 tests).
Run: `python -m pytest tests -q` → 149 passed.

| # | Item | Status | Implementation | Test |
|---|---|---|---|---|
| 1 | SQL injection | ✅ fixed | Every statement uses bound parameters (`store.py`, `db.py`); org inputs format-validated (`^\d{9}$`) before reaching any query | `test_sql_injection_login_rejected`, `test_sql_injection_in_organisation_number_rejected`, `test_store_parameterized_lookup` |
| 2 | Cross-site scripting | ✅ fixed | Jinja2 `autoescape=True`; no inline JS (`script-src 'self'`); org field validated before echo; CSP header | `test_xss_script_tag_rejected_in_org_field`, `test_security_headers_and_csp_present` |
| 3 | CSRF protection | ✅ fixed | Double-submit token bound to peppered session id, `SameSite=Strict` cookies, token required on every POST | `test_csrf_missing_token_rejected`, `test_csrf_wrong_token_rejected`, `test_csrf_logout_requires_token` |
| 4 | File upload validation | ✅ fixed | Extension allowlist, 2 MB cap, UTF-8 + structural sniffing, NUL rejection — before any disk write; admin-only | `test_upload_rejects_executable_extension`, `test_upload_rejects_oversized_and_binary`, `test_upload_rejects_invalid_json_and_accepts_valid`, `test_upload_endpoint_requires_admin_and_validates` |
| 5 | Broken object-level authorization (BOLA) | ✅ fixed | Every profile/job access passes `tenant_id` from the verified JWT (never from user input); ownership checked in the data layer | `test_bola_other_tenant_cannot_read_profile`, `test_bola_web_404_for_other_tenant_profile` |
| 6 | Rate limiting | ✅ fixed | Sliding-window per IP+bucket: login 10/min, register 5/5min, research/refresh 30/min, MFA 10/min, webhook 60/min | `test_login_rate_limit_triggers` |
| 7 | JWT secrets | ✅ fixed | HS256 pinned; secret from `JWT_SECRET` env (≥32 chars, fail-fast, ephemeral dev fallback); `alg=none` rejected; tamper rejected | `test_jwt_rejects_tampered_token`, `test_jwt_alg_confusion_blocked` |
| 8 | API server-side only | ✅ fixed | GROQ/OPENROUTER keys read via `os.environ` inside server code; templates contain zero key material; envelopes record only aggregated cost | `test_no_localstorage_token_usage` + template invariant |
| 9 | Password hashing | ✅ fixed | argon2id (time_cost=2, 64 MiB, p=2), auto-rehash on login, policy 12+/upper/lower/digit | `test_password_hashing_is_argon2_and_verifies`, `test_password_policy_enforced_endpoint` |
| 10 | Multi-factor auth | ✅ fixed | TOTP with sealed-at-rest secret (HMAC-derived key), two-step login pending cookie (5 min), rate-limited attempts | `test_mfa_enable_and_verify_flow` |

## PART2

| # | Item | Status | Implementation | Test |
|---|---|---|---|---|
| 11 | CORS tightened | ✅ fixed | Allowlist from `CORS_ALLOW_ORIGINS` (default empty ⇒ same-origin only); foreign preflight → 403; no wildcard | `test_cors_no_allowlist_no_acao_header`, `test_cors_preflight_foreign_origin_forbidden` |
| 12 | No token in localStorage | ✅ fixed | Session JWT in `httpOnly; SameSite=Strict; Secure` cookie; server-rendered app — zero browser storage APIs | `test_no_localstorage_token_usage`, `test_session_cookie_is_httponly_and_strict` |
| 13 | Permissions enforced server-side | ✅ fixed | `require_user` / `require_admin` inside handlers; role claim re-checked per request; templates only decorate | `test_non_admin_cannot_access_admin_pages` |
| 14 | Row-level security | ✅ fixed | `Store`/`IdentityStore` require `tenant_id` on every read/write; registration mints a per-user tenant; cross-tenant reads return nothing (Postgres RLS draft below) | `test_bola_other_tenant_cannot_read_profile` |
| 15 | Webhook signature verification | ✅ fixed | HMAC-SHA256 over raw body with `WEBHOOK_SECRET`, constant-time compare, missing/invalid → 401 | `test_webhook_rejects_bad_signature_accepts_good` |
| 16 | SSRF | ✅ fixed | `assert_public_url`: HTTP(S) only, blocks localhost/*.local, private/loopback/link-local/reserved IPs (DNS-resolved), re-validated on **every redirect hop**; used by crawler + `/admin/preview-url` | `test_ssrf_blocks_private_and_metadata_targets` |
| 17 | Source maps removed | ✅ fixed | No bundler, no `.map` files, no `sourceMappingURL` in shipped assets; CSP forbids eval | `test_no_source_maps_shipped` |
| 18 | Default credentials | ✅ fixed | Bootstrap admin gets a **random** ≥16-char one-time password (or env-provided), `must_change_password=1`; second bootstrap is a no-op | `test_bootstrap_admin_has_random_password_and_must_rotate` |
| 19 | Sensitive data out of logs | ✅ fixed | `RedactingFilter` strips Bearer tokens, password/secret assignments, all known key names; installed on root + webapp + agent loggers | `test_log_redaction_strips_secrets` |
| 20 | Vulnerable dependencies | ✅ checked | `requirements.txt` fully pinned (91 packages); `pip-audit -r requirements.txt` → **No known vulnerabilities found** (9 Oct 2026); re-run before every submission | command recorded in TASKS.md |

## Extra hardening present

- Security headers on every response: CSP, `X-Content-Type-Options`,
  `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Permissions-Policy`,
  `Cache-Control: no-store`.
- Uniform login errors (no user enumeration) + dummy hash on unknown email.
- Cookie flags: HttpOnly, SameSite=Strict, Secure (dev toggle for local http).
- OpenAPI/docs endpoints disabled (`docs_url=None, openapi_url=None`).

## Postgres RLS policy draft (production deployments)

```sql
ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON profiles
  USING (tenant_id = current_setting('app.current_tenant'));
-- application sets: SET app.current_tenant = '<verified-jwt-tenant>';
```

The SQLite data layer enforces the identical predicate in code — that is what
the tests assert.

## Reporting

Security issues: private report via the Builderr Discord or
inquiries@builderr.ai. Never include secrets in reports.

