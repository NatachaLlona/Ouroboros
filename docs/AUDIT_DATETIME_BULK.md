# 🧭 Audit, datetime and bulk API contracts

This phase adds migrations **007** and **008**, eleven collection PUT routes and two read-only audit routes. The catalogue now has 77 routes. Authentication, credential-version revocation, supervisor individual CRUD, restrictive relationships and existing ordering/pagination remain in place. No frontend, email recovery, date table or preferences table is introduced.

## 🕒 Datetimes

Migration 007 adds nullable `created_at TIMESTAMPTZ` and `created_at_timezone TEXT` to **all eleven catalogue tables**. Existing records retain NULL for unknown creation time/context. Defaults and an insert trigger generate both values for new rows; the database rejects changes to either value. Existing `added_at` and `watched_at` retain their meaning and values.

Additional source fields are `watchlist_entries.added_at_timezone TEXT`, `watch_history.watched_at_offset TEXT` and `watch_history.watched_at_timezone TEXT`. Historical unknown context stays NULL. `watched_at_timezone` accepts an explicitly supplied IANA zone only with an explicit watched instant; it must agree with that instant's supplied offset. An offset never implies a geographical zone. Changing watched_at replaces its context; clearing it clears both companions. A full canonical record echo preserves the recorded source offset.

Database sessions and canonical JSON timestamps are UTC (`Z` or `+00:00`). Shared code is in `app/datetimes.py`; Windows uses the declared `tzdata` package. Server clocks and technical log dates are UTC. Configuration fields `application_timezone` and `default_display_timezone` default to `Europe/Lisbon`; neither changes storage timezone.

Catalogue and audit reads accept `display_timezone=<IANA zone>|original`. The default is the configured display zone. Canonical timestamps stay UTC. The separate read-only `presentation` object contains `display_timezone` and `dates`, keyed by timestamp field. Each date has `datetime`, `date`, `time`, `timezone`, `offset`, and `fallback_utc`. NULL dates have NULL presentation. Original display uses the recorded IANA zone or numeric offset; unknown original context explicitly falls back to UTC. Audit clocks are known server UTC. DST conversion uses the event date. Naive dates are rejected; offset-aware inputs disambiguate folds, and inconsistent/nonexistent local zone/offset combinations are rejected.

GET, POST and PUT return the same canonical record schema. Equivalent display selections produce equivalent presentation. A full GET body is valid individual PUT input when its read-only fields are echoed unchanged; presentation is validated against its embedded display selection. To edit mutable values, omit the old presentation. Created fields, source offset and generated identity remain protected. Friendly strings never participate in SQL filtering or ordering.

All eleven collection GET and bulk routes accept `created_at_date` and `created_at_from/to`. Calendar dates use filter_timezone; an upper calendar date includes its entire day. Timestamp lower bounds are inclusive and timestamp upper bounds remain exclusive. Either range bound may be absent; supplied instants require offsets and calculated UTC from must precede to. Bounds combine with every other filter using AND; unknown historical NULL creation dates do not match a bound. Example: `2026-10-01T00:00:00+01:00` through `2026-11-01T00:00:00Z`. Encode plus signs in URLs; editable Postman Params handle encoding once.

## 🧮 Administrator bulk operations

`PUT /<resource>` updates submitted mutable fields on every matching row. Omissions preserve values; null clears nullable fields only. Empty bodies, unknown properties and immutable fields are rejected. Complete resulting-row constraints and restrictive foreign keys apply. `updated_count` counts successfully targeted rows, including unchanged submitted values. `DELETE /<resource>` deletes every matching row; no filters means the whole table. It returns `deleted_count`.

Both return bounded objects containing `matched_count`, `dry_run`, a concise `summary`, and the applicable count for actual execution. `dry_run=true` returns only the preview count and summary, without changing catalogue records. It can create audit evidence and needs no confirmation. Counts may change before execution.

Every actual request requires `confirm=true`, filtered or unfiltered. Missing/false confirmation produces `CONFIRMATION_REQUIRED` (422). Unknown query keys, pagination, ordering and presentation controls are rejected rather than ignored. Bulk predicates match collection GET predicates, including ranges. There is no page limit. SQL locks and changes the selected targets in one transaction; any constraint failure rolls everything back. Administrator authority is rechecked within that transaction under the existing role lock. Supervisors cannot bulk mutate; they retain individual CRUD. There is no bulk API for users, migrations or audits. No TRUNCATE, cascade, sequence reset or ID reuse occurs.

## 🧾 Audit table and read API

Migration 008 adds `api_audit_logs`, separate from the eleven domain tables. Its exact columns are:

| Columns | PostgreSQL types / meaning |
| --- | --- |
| `id_api_audit_logs`, `sequence_api_audit_logs`, `prefix_api_audit_logs`, `fantasy_name_api_audit_logs` | TEXT generated ID, BIGINT identity, fixed TEXT `AL`, fixed TEXT `Auditoria de APIs`; minimum seven digits, no truncation |
| `interaction_id` | Unique TEXT; matches HTTP header, error envelope and request file logs |
| `started_at`, `finished_at` | TIMESTAMPTZ; finish nullable while incomplete |
| `duration_ms` | Nullable nonnegative finite NUMERIC |
| `status` | TEXT: in_progress, success, failure |
| `method`, `path`, `matched_route` | TEXT; sanitized path, nullable matched route |
| `http_status`, `response_started` | Nullable INTEGER actual status; BOOLEAN accepted response headers |
| `error_code` | Nullable stable TEXT error code |
| `actor_id`, `actor_username`, `actor_role` | Nullable BIGINT/TEXT/TEXT verified identity snapshots |
| `request_query`, `request_body`, `response_body` | Nullable sanitized, bounded JSONB |
| `resource`, `target_id` | Nullable TEXT; no target for bulk |
| `differences` | Nullable JSONB field-level before/after evidence for individual mutations |
| `operation_summary` | Concise server-owned English TEXT |
| `capture` | JSONB omission/truncation flags and reasons |
| `business_outcome` | TEXT: not_started, committed, rolled_back, read_only, preview |
| `mutation_count`, `mutation_details` | Nonnegative BIGINT; nullable JSONB bounded bulk intent/counts or audit-read counts |

There are no actor/target foreign keys. Evidence survives legitimate user/catalogue deletion. No client can submit facts or mutate audit records through the API. This is application read-only access, **not cryptographic tamper resistance against the database master**.

`GET /api_audit_logs` and `GET /api_audit_logs/{id}` require supervisor or administrator. Standard gets 403; write methods get 405. Collection filters are interaction_id, actor_id, actor_username, started_at_date/from/to, finished_at_date/from/to, filter_timezone (calendar rules below), method, resource, status, http_status, error_code and target_id. Pagination remains page>=1, page_size 10–50. Whitelisted scalar order_by fields and asc/desc are explicit OpenAPI enums; JSON and presentation cannot be sorted. NULLS LAST applies in both directions, with ID ascending tie-break. Shared display_timezone applies.

Audit queries record access, sanitized criteria, matched/returned counts and a concise summary. Their response bodies are omitted to prevent copying audit history recursively.

## 🔒 Lifecycle, integrity and limitations

Central ASGI middleware covers health, token, users/roles/passwords, catalogue, validation/auth failures, unknown routes, unsupported methods, internal failures and cancellation. Deliberate documentation/static exclusions are `/docs`, `/docs/oauth2-redirect`, `/openapi.json`, `/redoc`, `/favicon.ico` (also trailing slash forms).

Entry commits an in_progress row before endpoint execution, without holding a lock over business work. Database row triggers on test, users and all catalogue resources write mutation evidence **inside the same transaction as the change**. Missing/failed mandatory audit rolls back the change. Bulk zero-match and preview summaries are written explicitly in their transactions. Short finalization transactions add transport/body metadata afterward and preserve committed mutation evidence. Rejected or rolled-back attempts are finalized outside the failed transaction. Trusted startup/migration/master connections are outside HTTP audit scope; no API bypass is exposed.

Handled 4xx are audit failure while existing technical `outcome=completed` still means completed transport. Internal/cancelled requests are failure. After headers, audit retains the accepted status and records the internal error separately; it never sends another JSON response. Accepted ASGI output means server send acceptance, not confirmed client receipt. Abrupt process loss or failed finalization can leave in_progress rows, including rows with committed business evidence.

If entry/finalization fails, a sanitized `API audit persistence failed` file event carries the same interaction ID, phase, `AUDIT_UNAVAILABLE` and `audit_persisted=false`. Mutations fail closed when mandatory transactional evidence cannot be saved; health/reads can still diagnose availability. There is **no durable replay queue**: entry outages can create audit gaps; failed finalization may leave incomplete transport metadata. File logging can also fail; retries do not recurse. These limits are explicit, not delivery guarantees.

Capture observes each ASGI stream once, forwards bytes unchanged, and bounds request/response/query/diff payloads. `audit.request_body_max_bytes`, `response_body_max_bytes`, `query_max_bytes`, `mutation_max_bytes` default to 8192 each (256–1048576). Oversized data is omitted with flags, not persisted as a raw preview. Non-JSON, incomplete and invalid bodies have explicit omission reasons. Entire token/password request and response bodies, including errors/malformed inputs, are omitted. Authorization/Cookie headers are never captured. Nested structured/serialized JSON secrets and recognizable token/connection strings are redacted centrally; user diffs project only safe account metadata. No arbitrary-text detector can recognize every hidden secret: never submit secrets as catalogue/free-text values.

Bulk evidence contains bounded filters, intended fields, matched/applied counts and outcome, never an array of every changed/deleted row. Row triggers still update a single audit row per affected row, so large batches cost database work. Storage grows indefinitely; this phase performs no automatic retention/deletion. Future retention, access separation, durable replay and stale in_progress reconciliation need explicit design.

## 🚦 Standard errors

`app/error_codes.json` version 1 is validated at startup for exact structure, duplicate keys/codes, supported codes, statuses and safe messages. Invalid content fails with a safe diagnostic. Errors use `{"error":{"code":"VALIDATION_ERROR","message":"...","interaction_id":"..."}}`, with bounded sanitized `details` for validation. No rejected input, raw SQL, stack or credential context is returned. Correct HTTP status and required WWW-Authenticate/Allow headers are preserved. Logs and audit use the same code/interaction ID; failures after accepted headers cannot replace the response.

The 16 codes are RESOURCE_NOT_FOUND, METHOD_NOT_ALLOWED, RELATIONSHIP_CONFLICT, USER_CONFLICT, PASSWORD_CHANGE_REJECTED, VALIDATION_ERROR, AUTHENTICATION_REQUIRED, INVALID_TOKEN, INVALID_CREDENTIALS, INSUFFICIENT_PERMISSIONS, CONFIRMATION_REQUIRED, DATABASE_UNAVAILABLE, AUDIT_UNAVAILABLE, INTERNAL_ERROR, REQUEST_CANCELLED and TRANSPORT_FAILURE. See the JSON catalogue for authoritative messages/statuses.

## 🛡️ OWASP conventions and verification

Security decisions use official [OWASP ASVS 5.0.0](https://owasp.org/projects/asvs) and the [Authentication](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html), [Authorization](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html), [Password Storage](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html), [Logging](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html), [Input Validation](https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html) and [Error Handling](https://cheatsheetseries.owasp.org/cheatsheets/Error_Handling_Cheat_Sheet.html) Cheat Sheets (consulted 2026-10-19).

Concrete checks: deny by default and verify current account state on every request; recheck mutation authority in its transaction; parameterize values and whitelist identifiers; keep Argon2id hashes; verify current password for self changes; revoke old tokens via credential version on reset/change; omit authentication/password bodies; bound and sanitize audit/log/error data; restrict audit reads; preserve transactional rollback; return safe centralized errors. No GET password endpoint exists: passwords cannot be recovered from hashes. Future email recovery must reset passwords, never email existing passwords; email is outside scope. Passing checks or scans is not a claim of blanket OWASP compliance.

Use the single [QA plan](QA_TEST_PLAN.md) and canonical Postman collection. Preview requests are safe catalogue reads; actual bulk examples ship confirm=false and require private local `catalogue_destructive_opt_in=isolated`, and are skipped in ordinary runs. Credentials/tokens remain empty in tracked JSON. Optional filter Params start disabled. Capture/reuse interaction IDs to query audit history. Schema/HTTP automation does not prove actual Swagger UI or Postman JavaScript execution.

## 🪜 Classification tiers and complete test CRUD

Migrations009–010 add independent classification tier positions and complete integer-ID test CRUD with shared creation dates, UTC presentation, strict filters and confirmed administrator bulk operations. See [the authoritative contracts](TIERS_AND_TEST_CRUD.md) for the one-time inspected backfill, atomic append/insert/move/delete behavior, bulk tier exception, scope matrix and restart instructions. Never reseed or replace the existing nine normal classifications. Destructive QA remains isolated; review measurements and findings are documented separately.

## Calendar-day filters

All publicly filterable timestamp fields support `<field>_date`, `<field>_from` and `<field>_to`: created_at on test and all catalogue resources, added_at on watchlist_entries, watched_at on watch_history, and started_at/finished_at on api_audit_logs. Existing exact-instant filters remain available where previously exposed.

`created_at_date=2026-10-25` matches the entire calendar day. `created_at_from=2026-10-01&created_at_to=2026-10-25` includes both calendar dates. Either bound may be omitted. The date-only upper bound becomes the beginning of the following local day, exclusively. A same-day date range is valid. Historical NULL dates never match supplied date filters.

`filter_timezone=Europe/Lisbon` selects a validated IANA zone; omission uses configured application_timezone. It is independent of display_timezone and recorded source zones. Local midnights are converted separately to UTC, so DST days can span 23 or 25 hours. SQL compares stored timestamps directly against parameterized UTC boundaries, without row casts or formatting.

From/to still accept timezone-aware ISO 8601 timestamps: the lower instant is inclusive and the upper instant is exclusive. For example, `created_at_to=2026-10-25T00:00:00Z` excludes that instant and everything after it; `created_at_to=2026-10-25` includes that entire local calendar day. Mixed date/timestamp bounds follow these same rules. Naive datetimes, invalid dates/zones, nonincreasing calculated boundaries, and exact-day plus same-field range combinations return 422. An upper calendar date that cannot advance to the following day is rejected.

Collection GET, administrator bulk PUT/DELETE and previews share predicates. Compare GET count with preview matched_count using identical criteria; separate requests can observe intervening writes. Swagger lists date/date-time alternatives and examples. Postman calendar controls are editable and unchecked by default. Enable either exact-day or range controls for a field, not both. Actual bulk requests retain confirmation and disposable-data opt-in requirements.

## Atomic array creation

POST on the eleven catalogue resources and /test accepts one object or an ordered atomic array (default maximum 300). Single responses retain their full record shape; arrays return created_count/items with full final records, independently of GET pagination and administrator bulk PUT/DELETE. See [request, validation, configuration, audit and restart contracts](BATCH_CREATION.md).
