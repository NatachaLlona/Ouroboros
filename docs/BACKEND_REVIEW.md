# Backend review fixes

This backend-only change adds migration **011_add_platform_access.sql**. Existing rows, account hashes, credentials, classification positions, private files and infrastructure are preserved. Migrations 001–010 retain their original contents. Frontend and session cookies are outside this task.

## Platform access contract

| Field | Creation and responses | Individual PUT | GET and bulk filters | Ordering | Administrator bulk PUT |
| --- | --- | --- | --- | --- | --- |
| platform_access_types | Array of unique `application`, `website`, `link` values; multiple values supported; omission defaults to `[]` | Omit to preserve; replace whole array; `[]` clears; null and duplicates rejected | One enum value selects records containing that member; AND with other filters | PostgreSQL text-array lexicographic order, preserving submitted element order; ID tie-break | Replace the entire array on every match |
| platform_url | Optional HTTP/HTTPS URL, maximum 2083 characters; omission defaults to null | Omit to preserve; null clears; supplied URL is validated and retained without rewriting | Unmodified case-insensitive ILIKE pattern, including `%`, `_` and existing escape conventions | Text ordering, NULLS LAST in either direction; ID tie-break | Replace URL or clear with null |

Both fields appear in single-object and atomic-array POST results, GET by ID, paginated collection items and PUT results. Full unchanged GET-record PUT remains supported. Unknown historical access types are `[]`; unknown URLs are null. The migration adds CHECK constraints for allowed unique access members and HTTP(S) URL shape; application validation additionally checks URL syntax. It does not fetch URLs or infer data.

GET, bulk PUT, DELETE and their previews share predicates. Bulk preview is nonmutating; actual bulk changes require an active administrator, transaction-time authority checks and `confirm=true`. No filters still selects the complete resource. New fields use the existing atomic business/audit triggers, rollback and bounded capture. Arrays are not automatically sorted or deduplicated. Swagger shows all three allowed access choices. Related identifying reference summaries remain deliberately small and do not expand to full platform records.

## Administrator user collection

`GET /users` remains administrator-only. All supplied criteria combine with AND before count, whitelisted ordering and pagination. Unknown parameters and secret fields are rejected. The public representation remains id, username, role, is_active and created_at.

| Parameter | Meaning |
| --- | --- |
| id | Exact positive BIGINT account ID |
| username | Exact case-sensitive username |
| username_pattern | Unmodified PostgreSQL ILIKE pattern; `%` any sequence, `_` one character, backslash escapes wildcards/backslash; empty matches empty text |
| role | Exact administrator, supervisor or standard |
| is_active | Exact boolean; false is a real filter |
| created_at_date | Entire local calendar day |
| created_at_from / created_at_to | Inclusive lower bound; final calendar date included in full, timestamp upper bound exclusive |
| filter_timezone | IANA zone; omission uses application_timezone; independent of presentation |
| page / page_size | One-based page; 10–50 items per page |
| order_by / order_direction | id, username, role, is_active or created_at; asc/desc; NULLS LAST; ID ascending tie-break |

Calendar filters use shared UTC boundary calculations, including 23/25-hour DST days. Exact day cannot combine with same-field range bounds. Either bound can be omitted; same-day calendar ranges are valid. Timestamps must include offsets. Count and page items use one statement snapshot. Password hashes, scopes, credential versions and other secrets are neither returned nor exposed as filters/order choices. No user bulk mutation is introduced.

## New password policy and login admission

First administrator enrollment, POST /users, own-password changes and administrator resets apply the same **15–1024 Unicode character** bounds to newly set passwords. Spaces, long passphrases and password-manager paste are supported; no uppercase/symbol rules, trimming, normalization or silent truncation is applied. The maximum bounds hashing input while supporting passphrases well over 64 characters. Length is measured in Unicode code points. Current-password confirmation and token login continue accepting existing passwords. No migration rewrites hashes or forces password replacement. Argon2id, current-password self change and transactional credential-version revocation remain in place. Disposable QA credentials must meet the new policy; tracked Postman credential variables stay empty.

`POST /token` admits at most **10 attempts per exact account name** and **50 attempts per direct client address** in **300-second fixed windows**. All admitted attempts count, including successful requests, so concurrent requests cannot bypass the limit. Counters expire automatically; rejected requests do not extend expiry. There is no permanent lockout. The limiter runs before database lookup and Argon2 verification, uses a thread lock, monotonic time and SHA-256 keys, and holds at most **10000 entries** across both dimensions. At capacity, new identities are temporarily rejected until an entry expires; active limits are never evicted to make room. Existing identities can still attempt login subject to their limits when no new entry is needed.

The supported deployment remains **one Uvicorn worker**. Limits are process-local and reset on restart; they are not a distributed or durable attack-prevention service. Account abuse can temporarily deny login to a legitimate account. Invalid credentials remain generic 401; throttled requests return the standardized **429 LOGIN_THROTTLED** envelope, `Retry-After` in seconds and `Cache-Control: no-store`. Credential/password bodies remain wholly omitted from logs and audit captures. Never log limiter keys, credentials or tokens. No arbitrary forwarding header is trusted: built-in startup explicitly sets `proxy_headers=False`. Custom launches must also disable proxy header processing; a future trusted-proxy deployment requires a separately designed boundary.

Security decisions consulted the official [OWASP ASVS](https://owasp.org/projects/asvs) and Cheat Sheets for [Authentication](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html), [Authorization](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html), [Password Storage](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html), [Logging](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html), [Input Validation](https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html) and [Error Handling](https://cheatsheetseries.owasp.org/cheatsheets/Error_Handling_Cheat_Sheet.html) on 2026-10-25. These controls and passing tests do not establish blanket OWASP compliance.

## Relationship schema and QA traceability

Keep `readOnly` on relationship reference fields and identifying values. Declaring the same annotation on the referenced model causes Pydantic to remove redundant `$ref` sibling annotations. The regression asserts field-level OpenAPI metadata and rejects references in write inputs; it is retained unchanged. Collection-only enrichment, authoritative FK IDs, one-level identifying names, batched queries and repeatable snapshots retain their existing contracts.

The four relationship tests map to existing scenarios **14.2, 14.3, 14.6 and 14.7**. Their manual steps and generated plan use the same IDs, and related Postman collection checks assert summary shape and authoritative IDs. New review regressions use **18.1–18.4**. Canonical Postman includes optional disabled public user filters, an enabled combined-filter example, platform membership/URL filtering, a nonmutating bulk preview and short-password rejection. Run sync_catalogue_postman.py, sync_qa_postman.py, sync_postman_readme.py and generate_qa_docs.py after relevant changes. Preserve private exports/environments.

## Migration, restart and manual checks

Normal migration and live validation remain an interactive owner operation. Identify an occupied listener's executable and launch ownership before stopping it; leave unconfirmed processes alone. Stop only the confirmed Ouroboros terminal with Ctrl+C, then run from C:\Dev\Ouroboros:

```powershell
.\.venv\Scripts\python.exe start.py
```

Use existing interactive master credentials. Startup checks migration checksums and applies 011 transactionally. Do not extract secrets, reseed records, replace the nine normal classifications, recreate infrastructure or change credentials to perform this upgrade. New backend code requires migration011 before serving platform operations.

Manual evidence remains separate: inspect Swagger enum choices/readOnly metadata and password-manager paste, exercise the new Params against disposable QA, import the canonical Postman JSON while retaining private environments, execute its JavaScript checks, and verify 429/Retry-After followed by expiry with a real HTTP client. Automated HTTP/schema tests do not prove Swagger GUI, Postman sandbox or real terminal interaction. Read actual results in the delivery record and sanitized reports; skipped checks never count as passed.

## Observed validation — 2026-10-25

The final `.\.venv\Scripts\python.exe scripts/run_checks.py` run used project dependencies and Docker outside the filesystem sandbox so the existing owned disposable harnesses could access the engine. It completed in 414.982 seconds with exit code 0: **156 tests counted, 155 PASS, 0 FAIL/errors, 1 SKIP**, no blocked tests and no fixture preparation/cleanup failures. The four relationship tests and all eight backend-review tests passed, including actual PostgreSQL migration preservation, platform batch/bulk/audit behavior, user date filtering and preservation of existing short-password authentication until an explicit password change.

Scenario results were 73 PASS, 1 SKIP and 4 MANUAL. The skipped check was `test_accounts_integration.AccountIntegrationTests.test_02_definitive_ports_and_swagger`: host database port 6669 was occupied. Its fixed-port assertion was not validated and is not counted as a success. Required database integrations used temporary ports; the occupied service was left alone. The runner reports mandatory automation passed and QA approval **PENDING_MANUAL_VALIDATION**. See [sanitized summary](../reports/summary.md), [structured results](../reports/results.json) and [JUnit results](../reports/junit.xml).

The QA catalogue/generated-plan check, canonical Postman schema/embedded JSON checks and whitespace diff check also passed. Swagger UI, Postman JavaScript execution, physical terminal/password-manager interaction and normal interactive migration/restart remain pending. No frontend, session-cookie changes, commit, push or merge were performed. Login admission remains process-local, single-worker and reset on restart; it is not distributed protection.
