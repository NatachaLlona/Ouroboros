# 🐍 **Catalogue CRUD API**

Ouroboros implements seven endpoint forms for each of the eleven catalogue resources, including confirmed filtered bulk PUT/DELETE and previews. Audit reads are separate. No frontend, AI or seed data is introduced.

| Route for each `<resource>` | Result |
| --- | --- |
| `POST /<resource>` | 201, complete persisted record for one object; created_count/full items for an atomic array |
| `GET /<resource>` | 200, `{count, page, page_size, items}` |
| `GET /<resource>/{id}` | 200, complete persisted record; missing 404 |
| `PUT /<resource>/{id}` | 200, complete persisted record; missing 404 |
| `DELETE /<resource>/{id}` | 204, empty body; missing 404; dependencies 409 |
| `PUT /<resource>?confirm=true` | Administrator only, filtered bulk update; bounded counts/summary; atomic |
| `DELETE /<resource>?confirm=true` | Administrator only, filtered deletion; bounded counts/summary; dependencies 409 |

## 👤 **Current-role permissions**

| Capability | standard | supervisor | administrator |
| --- | --- | --- | --- |
| Test read/write with current test scopes; own-password change | Yes | Yes | Yes |
| Catalogue GET/POST/PUT/DELETE by ID | No | Yes | Yes |
| Catalogue DELETE all | No | No | Yes |
| User administration and other-user password reset | No | No | Yes |

`GET /health` remains public. User creation defaults to standard; creation/role replacement accepts all three roles. Current database role, active state and credential version are checked on every protected request. Supervisor catalogue permission is derived from current role even for an older test-only token. Promotions/demotions apply without login; password-version revocation still requires reauthentication.

Migration **006_add_supervisor_role.sql** replaces only the api_users role CHECK. It preserves users, hashes, versions, data and migrations 001–005. The last active administrator cannot be demoted to either other role.

## ✏️ **POST, PUT and record round trips**

Single POST/PUT/GET-by-ID and collection items use the identical public record schema, including all generated metadata/defaults/timestamps from PostgreSQL. Array POST wraps those same full records in created_count/items, ordered by request. POST accepts domain fields only, as one object or an atomic array. PUT intentionally supports both partial input and a full copied GET record. Unknown properties and `{}` return 422.

- Omit a field to preserve its locked current value. Explicit null clears only nullable fields.
- Echo ID/sequence/prefix/fantasy name unchanged; attempts to change them return 422. `watchlist_entries.added_at` is server-controlled and may only be echoed unchanged. `watch_history.watched_at` remains editable and timezone-aware; null preserves unknown completion dates.
- The resulting complete record is validated after acquiring its row lock. Switching work_tags requires `{"id_tags": null, "id_tag_relationships": "TR0000001"}`. Both/neither choices or both origins are 422; missing FKs, cross-work provenance and duplicate category pairs are 409.
- Only submitted mutable fields are assigned in SQL. Concurrent unrelated partial updates preserve both changes. A full record explicitly supplies every mutable field, so its supplied values intentionally replace those fields.
- Titles/languages remain supplied Unicode; synopsis content must be English by documented content policy. No SQL or API language detector is claimed. Descriptions/synopses have no arbitrary short text limits. Decimal prices and durations serialize as exact decimal strings and are accepted on round trips.

## 🔎 **Filters and ordering matrix**

All named stored fields below are supported filters and permitted `order_by` choices. Each query field appears in Swagger Parameters with description/examples. Omitted filters are disabled; supplied filters combine with AND before ordering/pagination. Exact filters compare equality. Text patterns use case-insensitive PostgreSQL ILIKE: `%` any sequence, `_` one character, backslash escapes literal wildcard/backslash, no automatic wildcards. Explicit empty text matches empty text. Query values are driver parameters, never SQL interpolation.

| Resource | Exact filters | ILIKE text filters | Default order_by |
| --- | --- | --- | --- |
| `works` | `id_works`, `sequence_works`, `prefix_works`, `fantasy_name_works` | `title`, `title_language`, `synopsis` | `sequence_works` |
| `platforms` | `id_platforms`, `sequence_platforms`, `prefix_platforms`, `fantasy_name_platforms`, `platform_is_paid`, `platform_is_episodes`, `platform_is_duration_time`, `price_amount` | `platform_name`, `price_currency` | `sequence_platforms` |
| `work_availabilities` | `id_work_availabilities`, `sequence_work_availabilities`, `prefix_work_availabilities`, `fantasy_name_work_availabilities`, `id_works`, `id_platforms`, `duration_minutes`, `episode_quantity` | `publisher_profile`, `url` | `sequence_work_availabilities` |
| `tags` | `id_tags`, `sequence_tags`, `prefix_tags`, `fantasy_name_tags`, `tag_name` | `display_name_tags`, `description_tags` | `sequence_tags` |
| `tag_categories` | `id_tag_categories`, `sequence_tag_categories`, `prefix_tag_categories`, `fantasy_name_tag_categories`, `tag_category_name` | `display_name_tag_categories`, `description_tag_categories` | `sequence_tag_categories` |
| `tag_category_relationships` | `id_tag_category_relationships`, `sequence_tag_category_relationships`, `prefix_tag_category_relationships`, `fantasy_name_tag_category_relationships`, `id_tags`, `id_tag_categories` |  | `sequence_tag_category_relationships` |
| `tag_relationships` | `id_tag_relationships`, `sequence_tag_relationships`, `prefix_tag_relationships`, `fantasy_name_tag_relationships`, `id_tags_source`, `id_tags_target` |  | `sequence_tag_relationships` |
| `work_classifications` | `id_work_classifications`, `sequence_work_classifications`, `prefix_work_classifications`, `fantasy_name_work_classifications`, `work_classification_name` | `display_name_work_classifications`, `description_work_classifications` | `sequence_work_classifications` |
| `watchlist_entries` | `id_watchlist_entries`, `sequence_watchlist_entries`, `prefix_watchlist_entries`, `fantasy_name_watchlist_entries`, `id_works`, `id_work_availabilities`, `id_work_classifications_predicted`, `added_at` | `observations` | `sequence_watchlist_entries` |
| `watch_history` | `id_watch_history`, `sequence_watch_history`, `prefix_watch_history`, `fantasy_name_watch_history`, `id_works`, `id_work_availabilities`, `id_work_classifications`, `watched_at` | `observations` | `sequence_watch_history` |
| `work_tags` | `id_work_tags`, `sequence_work_tags`, `prefix_work_tags`, `fantasy_name_work_tags`, `id_works`, `id_tags`, `id_tag_relationships`, `id_watchlist_entries`, `id_watch_history` |  | `sequence_work_tags` |

Every row in this matrix additionally supports exact `created_at` and `created_at_timezone` filters/order fields. Watchlist also supports `added_at_timezone`; watch history also supports `watched_at_offset` and `watched_at_timezone`. All resources support `created_at_date` and `created_at_from/to`; watchlist added_at and history watched_at support the same calendar/range controls. Calendar upper dates include the whole day; timestamp upper bounds remain exclusive. `filter_timezone` defaults to application_timezone, separately from read-only `display_timezone`; these controls are not order fields. See [UTC and source-context rules](AUDIT_DATETIME_BULK.md).

The exact filters include metadata, foreign IDs and technical snake_case names; platform_name remains human searchable text. Numeric/boolean/timestamp fields use exact values. Exact-instant timestamp filters require an explicit UTC offset and compare instants; calendar inputs use the rules below. Decimal filters must be finite; price is nonnegative and duration positive. Counts/sequences are positive decimal integers.

| Inherited collection | Filters | order_by choices / default |
| --- | --- | --- |
| `/test` | Exact `id`, ILIKE `value` | `id`, `value`; default `id` |
| `/users` | No account filters | `id`, `username`, `role`, `is_active`, `created_at`; default `id` |

`order_direction` is the enum `asc` or `desc`, default asc. All scalar public fields are selectable, but private user fields are never exposed. NULLS LAST applies in both directions. A selected non-ID field uses permanent ID ascending as a deterministic tie-breaker. Catalogue default is sequence ascending. Invalid ordering fields/directions return 422. Identifiers are whitelisted and composed with Psycopg identifiers; direction tokens are fixed trusted SQL.

`page` defaults to 1 (minimum 1); `page_size` defaults to 50 (10–50). Fractional page/count notation is rejected. Filtering, count and ordered items share one statement snapshot. An out-of-range page retains the matching count and has empty items. Separate page requests are not a frozen cross-request snapshot.

## 🗑️ **Deletion and transactional authorization**

Collection DELETE requires `confirm=true` for actual execution, accepts the same scalar/date filters as GET and deletes all matching rows. No filters means the whole table. `dry_run=true` previews matched_count without confirmation. Unknown filters, pagination, ordering and presentation parameters return 422. Actual results include deleted_count, matched_count, dry_run=false and summary; zero matches returns zero counts. A dependency blocks the whole transaction with safe 409. Collection PUT follows the same selection/confirmation rules with a nonempty mutable-field body and updated_count. Neither operation cascades, uses TRUNCATE nor resets/reuses sequences. There are no bulk mutation routes for users, audits or migration infrastructure. See [full contracts](AUDIT_DATETIME_BULK.md).

Catalogue writes share membership advisory lock **719230818** with user administration. Lock order is advisory lock, current actor row/version, then catalogue rows. Roles and token version are rechecked inside the write transaction. This favors simple consistent authorization over concurrent catalogue write throughput in this local phase. User creation/role replacement also rechecks the actor version. Last-administrator protection remains serialized. Self-password changes lock their own account row without acquiring the advisory lock.

After a successful deletion commit, INFO `Catalogue records deleted` records actor_id, resource, target_id (null for all), actual deleted_count and outcome=committed with automatic interaction ID. Expected repository rejections emit WARNING `Catalogue deletion rejected` with outcome=rejected/status, no committed count. Authentication/body/query failures before repository execution use shared safe rejection events. No SQL, rejected database values, credentials, hashes or tokens enter HTTP errors.

Statuses: **401** authentication; **403** role; **404** absent record; **409** referential/unique conflict; **422** invalid fields/query/confirmation/resulting constraints; inherited **503** backend unavailability. Safe parser errors expose locations/categories without input values. Generated IDs and all existing restrictive constraints remain in [CATALOGUE.md](CATALOGUE.md).

## 🧭 **Swagger, Postman and isolated QA**

Start in an interactive PowerShell terminal: `Set-Location C:\Dev\Ouroboros`, then `.\.venv\Scripts\python.exe start.py`. Enter credentials only through masked prompts. Swagger is **http://localhost:6969/docs**. Use **Authorize** once, reuse it across requests, and **Logout / re-authorize** to switch users. Calling POST /token alone does not configure global Swagger authorization. Dropdowns are standard OpenAPI enums; optional filters stay visible, without custom JavaScript.

Import only `postman/Ouroboros.postman_collection.json`. Keep all credentials, tokens and captured IDs in private local variables. New catalogue folders run in dependency order. Every GET collection shows all filters (unused fields unchecked), page/page_size and ordering controls. Enter raw `%` patterns in Params to avoid double encoding. Use fresh isolated supervisor/standard/admin accounts for the role folder. Full-record PUT uses a locally captured response, not versioned personal values.

**Destructive Postman requests are opt-in and skipped by default.** Both delete examples check `catalogue_destructive_opt_in=isolated` in a prerequest script. DELETE all also ships with `confirm=false`; explicitly select that request on disposable data and change it to true. Never enable a normal collection runner against real data. Delete leaves before parents. Recreate scripts with `python scripts/sync_catalogue_postman.py`, then `sync_qa_postman.py` and `sync_postman_readme.py`.

Run `.\.venv\Scripts\python.exe scripts/run_checks.py` for owned disposable Docker tests and sanitized reports. Scenarios **14.1–14.7** link the manual steps and HTTP automation. A fresh database per CRUD test stays inside a UUID-owned cluster; no normal records or Foundation resources are seeded, stopped or deleted. Swagger visual interaction, Postman sandbox/import, physical terminal and hosted CI remain separate manual evidence. If startup ports are occupied, choose free ports; do not stop another application.

Troubleshooting: **422 PUT** — omit unchanged metadata or echo it exactly, check nullability and send both fields when switching XOR choices; **409 DELETE** — remove only explicitly intended dependents first in disposable QA, never cascade; **403 supervisor** — confirm current database role and selected database; **401 after password change** — reauthenticate; **422 order** — choose the resource-specific Swagger enum.

## 🧾 Audit, UTC dates and filtered bulk operations

See [the phase contract guide](AUDIT_DATETIME_BULK.md) for migrations 007–008, exact columns, central audit transaction guarantees and outage/crash gaps, versioned error envelopes, UTC/source/display timezone rules, immutable creation dates, and administrator previews/confirmed filtered mutations. The current catalogue has 77 route forms plus two read-only audit routes. Supervisor has individual CRUD and audit reads; standard has neither; administrator alone bulk mutates. Historical creation dates/context stay NULL. No automatic audit retention or durable replay is provided.

For manual QA use owned disposable storage and fresh private accounts. Inspect Swagger controls, complete a GET-to-PUT round trip with original display, preview a filtered change, confirm it explicitly only in disposable storage, and query its X-Interaction-ID in api_audit_logs. Verify standardized codes/header/log/audit correspondence, whole token/password body omissions and restricted audit reads. Record actual UI/Postman JavaScript evidence separately. Never enable destructive examples against normal data.

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

## Platform access information

Migration011 adds platform_access_types (unique application/website/link array, default []) and optional HTTP/HTTPS platform_url (maximum 2083 characters). Both support creation, single/batch results, reads, partial/full-record PUT, ordering and confirmed administrator bulk replacement. Access-type filtering tests membership in one allowed value; URL filtering uses ILIKE. Historical unknowns stay []/null. See [the full field operation matrix](BACKEND_REVIEW.md).
## Description input length policy

`description_tags`, `description_tag_categories` and `description_work_classifications` accept up to the configured **4000 Unicode 16 extended grapheme clusters**, not UTF-16 units or code points. Fields remain optional/nullable, and omitted PUT values are preserved. Supplied overflow on POST/object/array, individual PUT or administrator bulk PUT returns the standard **422 VALIDATION_ERROR**, without truncation or partial batch writes. Generated input schemas publish `x-max-graphemes`/`x-unicode-version` and explanatory descriptions. Output schemas intentionally allow preserved historical oversized text. PostgreSQL TEXT, observations, synopsis and all other text contracts are unchanged. See [configuration, counting and historical inspection](DESCRIPTION_AND_TIERS.md).
