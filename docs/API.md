# 🔌 **API contracts and authorization**

The [catalogue CRUD guide](CATALOGUE_API.md) specifies all **77 catalogue route forms**, the three-role matrix, every filter/order field, response equivalence, atomic partial/full PUT and confirmed deletion. Standard has no catalogue access; supervisor has individual catalogue access; administrator alone can DELETE all. Every list, including `/test` and `/users`, supports `order_by` and `order_direction` enums with NULLS LAST and ID tie-breaks.

See the running instance's **`/docs`** for the exact OpenAPI schema. The main application and isolated manual QA examples use **http://localhost:6969** and PostgreSQL host port **6669**, internal port **5432**. Use alternate free ports only when the defaults are occupied, without stopping existing services. [QA setup](QA_SETUP.md) explains the explicitly suggested disposable credentials and every UI action.

| Method / path | Authentication / input | Result |
| --- | --- | --- |
| GET `/health` | Public, no body | 200 status ok after real query; 503 unavailable |
| POST `/token` | Public URL-encoded API username/password; password grant, optional space-separated scope | 200 access_token/token_type/expires_in, no-store headers; invalid/inactive credentials 401; unavailable scopes 403 |
| POST `/test` | test:write or current administrator; strict value object or array of such objects | 201 full record for an object; created_count/full items for an atomic array. No per-field text cap; creation request budgets apply |
| GET `/test` | test:read or administrator; optional positive BIGINT id and raw ILIKE value pattern | 200 paginated items ordered by ID; id/value combine with AND |
| POST `/users` | Active administrator; username/password and optional fixed role | 201 public account; omitted role means standard; duplicate 409 |
| GET `/users` | Active administrator; shared pagination | 200 public accounts ordered by ID |
| PUT `/users/{id}/role` | Active administrator; fixed replacement role | 200 public account; absent target 404; last active administrator demotion 409 |
| PUT `/users/me/password` | Any active authenticated API account; strict SecretStr current_password/new_password; no ID/username | 204 without body; wrong confirmation/unchanged password 400; invalid/stale authentication 401; invalid body 422 |
| PUT `/users/{id}/password` | Active administrator; strict SecretStr new_password only; positive BIGINT ID of another user | Empty 204; self-target 400, invalid token 401, standard caller 403, missing target 404, invalid body/path 422 |

**Public account fields:** id, username, role, is_active, created_at. Passwords/hashes are never returned. Invalid JSON, required fields, strict types, unknown fields, invalid roles or query bounds return **422** with safe loc/type/msg, without rejected input or parser context.

## 📚 **Common collection envelope**

```json
{"count":23,"page":2,"page_size":10,"items":[{"id":11,"value":"Example"}]}
```

`page` defaults to **1**, integer >=1. `page_size` defaults to **50**, integer **10–50**. Count reflects all matching rows before LIMIT/OFFSET; an out-of-range page preserves count with empty items, while no matches has count 0. **GET /test changed from a bare array to this envelope.** `/health` is a single object and exempt. See [pattern examples](../README.md#search-patterns) for `%`, `_`, backslash escapes and URL encoding; Params values use raw `%`, encoded once as `%25` on the wire.

## 🛡️ **Roles and token lifetime**

Standard users retain only allowed test scopes and cannot administer users. Active administrators authorize all shared protected endpoints, including future scopes, without a static all-scopes list as their authority. Every request reloads current role/state. A standard token immediately gains administrator behavior after explicit promotion; a previously issued administrator token loses it after demotion. Missing/invalid/expired/inactive tokens return **401**; authenticated denial is **403**. Administrative writes recheck authorization inside the membership transaction.

JWTs use HS256, immutable numeric-string sub, version 2, selected-database binding, issuer/audience and expiration validation. Passwords use Argon2id. `/token` accepts optional grant_type=password (omitted/empty defaults), empty unused client_id/client_secret and allowed space-separated scopes. **Swagger Authorize** sets global authentication; POST /token Try it out alone does not. Logout before switching users. Old-token behavior is verified with separate Postman variables, never by silently reauthenticating.

The [catalogue-generated QA plan](QA_TEST_PLAN.md) owns executable case IDs and approval criteria. HTTP/OpenAPI automation, browser interaction and Postman JavaScript execution are separate evidence types.

## 🔎 **Swagger query controls**

Authorize once with **Authorize → credentials/scopes → Authorize → Close**. Subsequent permitted requests reuse that authorization until logout, expiration or revocation. POST `/token` alone does not authorize the interface. After changing/resetting credentials, log out and authorize with the new password.

GET `/test` explicitly exposes optional `id`, `value`, `page` and `page_size`; GET `/users` exposes only optional `page` and `page_size`. **No users filters are implemented or documented.** Pagination defaults, bounds, examples and pattern escaping appear in each query control. Filters precede counting and pagination; both endpoints use ascending ID ordering. Raw `%Ouroboros%` in Swagger means contains; `literal\%\_\\` matches literal percent/underscore/backslash. Empty value matches empty text; omission disables it.

## 🛡️ **Reset another user's password**

PUT `/users/{id}/password` accepts only `{"new_password":"<private new password>"}`, with the same strict nonempty string policy as enrollment and self-service. No target current password is required. Self-targeting returns **400**: use `/users/me/password` and confirm the current password. This preserves a coherent self-service confirmation flow.

The shared administrator advisory lock serializes reset/role changes. Actor row locking rechecks current active administrator role and token credential version; a demoted actor is **403**, a stale actor version **401**. The target row lock serializes self-service and reset. Hash/version commit together; only target old tokens become invalid. Inactive targets stay inactive; unrelated accounts and the signing key are unchanged. Requests authorized before commit may finish; this does not cancel in-flight work. No new migration is needed beyond migration 004.

Success emits exactly **API password reset**, INFO, with `administrator_id`, `user_id`, `outcome=completed` and automatic request interaction ID. Transactional expected rejections emit **API password reset rejected**, WARNING, with the same IDs, outcome=rejected and safe status. Authentication/validation failures occur before the endpoint and use generic safe HTTP rejection/final events without a verified actor audit. Unexpected errors use safe generic diagnostics and final outcome=failed. The **entire reset body** is omitted at INFO/DEBUG, including malformed JSON and extra fields. Passwords, hashes and tokens never belong in evidence. See QA **9.1–9.2**, Postman **62–76**.

## 🔑 **Change your own password**

Migration **004_add_credential_version.sql** adds a per-account BIGINT version, initially 1, preserving existing IDs/hashes/profiles/data. Every new JWT includes **credential_version**, checked against the current database value on every protected request. Obtain a fresh token after upgrading; tokens without this required claim are rejected.

PUT `/users/me/password` requires the caller's current password and a different nonempty new password, both represented by SecretStr. The token identifies the target; extra identity fields are 422. A row lock rechecks active state/version and verifies Argon2id before replacing the hash and incrementing the version in the same transaction. Competing changes using one version yield exactly one success, with the other stale token rejected. No master credential, administrator override or global signing-key rotation is involved.

After commit all earlier tokens of **that account** are invalid, including the changing token; old-password login is 401, new-password login succeeds, and other accounts' tokens remain valid. Logout/re-authorize in Swagger using the new password. The **entire endpoint body is omitted** from DEBUG logs, including malformed JSON and rejected requests. Success records the exact **API password changed** INFO event with user_id and request context. The [QA cases 8.1–8.5](QA_TEST_PLAN.md) and Postman folder 40–60 verify both profiles, negative cases, revocation and concurrency.

## 🧾 Audit, UTC dates and filtered bulk operations

See [the phase contract guide](AUDIT_DATETIME_BULK.md) for migrations 007–008, exact columns, central audit transaction guarantees and outage/crash gaps, versioned error envelopes, UTC/source/display timezone rules, immutable creation dates, and administrator previews/confirmed filtered mutations. The current catalogue has 77 route forms plus two read-only audit routes. Supervisor has individual CRUD and audit reads; standard has neither; administrator alone bulk mutates. Historical creation dates/context stay NULL. No automatic audit retention or durable replay is provided.

For manual QA use owned disposable storage and fresh private accounts. Inspect Swagger controls, complete a GET-to-PUT round trip with original display, preview a filtered change, confirm it explicitly only in disposable storage, and query its X-Interaction-ID in api_audit_logs. Verify standardized codes/header/log/audit correspondence, whole token/password body omissions and restricted audit reads. Record actual UI/Postman JavaScript evidence separately. Never enable destructive examples against normal data.

## 🪜 Classification tiers and complete test CRUD

Migrations009–010 add independent classification tier positions and complete integer-ID test CRUD with shared creation dates, UTC presentation, strict filters and confirmed administrator bulk operations. See [the authoritative contracts](TIERS_AND_TEST_CRUD.md) for the one-time inspected backfill, atomic append/insert/move/delete behavior, bulk tier exception, scope matrix and restart instructions. Never reseed or replace the existing nine normal classifications. Destructive QA remains isolated; review measurements and findings are documented separately.

## Object and array creation

POST /test and the eleven catalogue POST creation endpoints accept one object or a nonempty atomic array. Single-object 201 responses remain full records; array 201 responses contain created_count and full items in request order, without GET pagination. Each item uses the existing create schema and creation permissions. See [the batch creation contract](BATCH_CREATION.md) for zero-based item errors, transaction/audit guarantees, classification tiers, configurable api.max_batch_size (default 300) and api.max_creation_body_bytes (default 4 MiB), client examples and restart instructions. Capture/inspection budgets are independent and remain bounded. No migration, reset or seed is required; preserve existing normal records and leave unconfirmed listeners alone.
