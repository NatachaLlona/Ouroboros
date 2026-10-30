# 🧭 Classification positions and complete test CRUD

This phase adds migrations **009** and **010**. Existing normal classifications are never seeded, replaced or re-entered. Both migrations are non-destructive; apply them through interactive startup with the existing master credentials. QA and performance runs use only owned disposable databases.

## 🪜 One-time backfill and ongoing ordering

`work_classifications.tier` is a required positive BIGINT with a deferrable unique constraint. It is independent of the immutable classification ID and identity sequence. Migration 009 inspects existing count/min/max and the unique sequence ordering first. A list with sequences exactly 1 through N retains those same positions (including the user's nine rows when their sequences are 1–9). Empty lists work. Gaps or other valid unexpected sequence values produce contiguous ranks starting at 1 in sequence/ID order. No row or relationship is deleted, no sequence is reset and names/descriptions/creation fields remain unchanged.

Startup emits `Classification tier backfill inspected` with safe numeric counts, sequence bounds and `preserved_sequence` or `contiguous_sequence_rank`. The migration also records the strategy/count/bounds in the tier column comment. This is a one-time backfill only. Later tiers never derive from sequence; migration replay preserves changes and existing checksums. If normal startup has not run, do not claim the actual normal backfill strategy or values were verified.

| Operation | Behavior |
| --- | --- |
| POST `/work_classifications`, tier omitted | Append at N+1 |
| POST, explicit tier | Insert at 1..N+1 and shift later positions down |
| Individual PUT, tier omitted | Preserve the current position while updating other fields |
| Individual PUT, explicit tier | Move to 1..N and shift intervening rows |
| Individual DELETE | Close the removed position's gap |
| Filtered collection DELETE | Compact survivors preserving their relative order |
| DELETE all | Leave an empty list; identity sequence continues |
| Collection PUT containing tier | 422 VALIDATION_ERROR with individual-PUT guidance; no mutation |

Tier rejects null, booleans, fractions, nonpositive and out-of-range positions. POST/GET/PUT share the full public representation. Full unchanged GET records remain valid individual PUT input. Immutable identity and creation metadata cannot change. Exact tier filtering and tier/order-direction dropdowns are exposed; default classification collection ordering is **tier ASC**, with ID ascending tie-break. Other explicit scalar orderings remain available. Bulk ordinary-field updates remain supported.

API lock order is membership lock 719230818, actor row/version revalidation, classification list lock 719230819, then affected records. A deferred unique constraint permits temporary overlaps during set-based shifts; uniqueness is validated at commit. Insert/move/delete/compaction and audit evidence share the transaction. Restrictive foreign-key failures roll back shifts as well as the primary change. Direct database masters remain trusted and must preserve ordering invariants when editing tiers themselves.

Automatically shifted rows contribute to the same request's mutation_count. `mutation_details.reordering` records action, moved classification ID/old/new tier, affected/shifted count and up to twenty shifted IDs with old/new positions. Capture limits can omit the sample explicitly; core moved/count facts take priority. Internal shifts do not invent API requests. Individual insert/move/delete retains the primary record's target/differences; bulk deletion uses aggregate evidence.

## 🧪 Complete integer-ID test resource

Migration 010 adds nullable `test.created_at TIMESTAMPTZ` and `created_at_timezone TEXT`. Historical dates/context remain NULL. New inserts receive automatic values even for an explicit SQL NULL; updates cannot change them. Integer automatic IDs and unrestricted Unicode TEXT values retain their existing format and behavior. There are no prefixed test IDs or artificial text-length limits.

| Route | Standard / supervisor | Administrator | Result |
| --- | --- | --- | --- |
| POST `/test` | test:write | Yes | 201 full record for an object; created_count/full items for an atomic array |
| GET `/test` | test:read | Yes | Filtered paginated full records |
| GET `/test/{id}` | test:read | Yes | 200 full record / 404 |
| PUT `/test/{id}` | test:write | Yes | 200 full record / 404 |
| DELETE `/test/{id}` | test:write | Yes | Empty 204 / 404 |
| PUT `/test` | No | Yes | Bulk preview or confirmed filtered update |
| DELETE `/test` | No | Yes | Bulk preview or confirmed filtered deletion |

The existing test:write scope now means create/update/delete individual entries. Token checks still reload current account state/role/version and intersect current scopes. Mutation authority is rechecked under membership/actor locks inside its transaction; administrator promotions/demotions affect already-issued tokens, and credential changes revoke earlier tokens.

Individual PUT preserves omitted fields, accepts an unchanged ID/creation/presentation echo, rejects `{}`, unknown properties, changed immutable values and null value. Empty text remains valid. Single POST/GET-by-ID/PUT, array POST items and page items use the same record schema: id, value, created_at, created_at_timezone and read-only presentation. Canonical timestamps are UTC. The shared `display_timezone` IANA/original conversion and unknown-source UTC fallback apply.

GET and bulk predicates are identical AND combinations: exact id/created_at/created_at_timezone, original unmodified ILIKE value pattern, created_at_date for a whole calendar day, and created_at_from/to date or timestamp bounds. Calendar upper dates include the whole day; timestamp upper instants are exclusive and require offsets. Bounds must form a valid increasing UTC interval; historical NULL dates do not match bounds. GET supports page>=1, page_size10–50, whitelisted id/value/created_at/created_at_timezone ordering, asc/desc, NULLS LAST and ID tie-break. Unknown filters are rejected.

Bulk PUT/DELETE are administrator-only, have no page limit, and require confirm=true for actual execution. dry_run=true returns matched_count without changing test rows and needs no confirmation. Unknown/misspelled filters, page/order/display controls, immutable bulk fields and empty bulk update are rejected. Actual results include matched_count, updated_count or deleted_count, dry_run=false and a concise summary. updated_count includes unchanged targeted values. Preview counts may change. No TRUNCATE, sequence reset or ID reuse is performed. Central bounded audit capture, error envelopes and transactional rollback apply to every route.

## 🔬 Verification and runtime

Run full checks with `.\.venv\Scripts\python.exe scripts/run_checks.py`. New stable scenarios **16.1–16.6** cover migration preservation, ordered CRUD, compaction/rollback, concurrency/audit bounds, complete test CRUD and bulk/scope behavior. The single catalogue generates the manual plan. Canonical Postman exposes fields and all Params; unused filters are unchecked. Reorders, deletions and actual bulk examples require explicit local `catalogue_destructive_opt_in=isolated`; bulk confirm defaults to false. Actual GUI/JavaScript execution requires separate evidence.

For a focused owned harness:

```powershell
$env:FOUNDATION_RUN_INTEGRATION='1'
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_remaining_phase.py -v
```

Performance/security/architecture measurements and tool findings are recorded in [the phase review](REMAINING_PHASE_REVIEW.md). Existing [audit/privacy/outage limitations](AUDIT_DATETIME_BULK.md) remain applicable: no durable replay, automatic retention or master-resistant tamper-proof storage.

Before restarting an occupied listener, verify its executable/launch command belongs to this workspace. Stop only the confirmed Ouroboros terminal with Ctrl+C, then run:

```powershell
Set-Location -LiteralPath C:\Dev\Ouroboros
.\.venv\Scripts\python.exe start.py
```

Answer existing masked credential prompts; do not extract secret files or bypass authentication. Read the startup backfill strategy and preserve the nine normal records. Swagger: **http://localhost:6969/docs**. If credentials are interactive, normal migration/validation remains pending until this startup; do not substitute destructive QA.

## Calendar-day filters

All publicly filterable timestamp fields support `<field>_date`, `<field>_from` and `<field>_to`: created_at on test and all catalogue resources, added_at on watchlist_entries, watched_at on watch_history, and started_at/finished_at on api_audit_logs. Existing exact-instant filters remain available where previously exposed.

`created_at_date=2026-10-25` matches the entire calendar day. `created_at_from=2026-10-01&created_at_to=2026-10-25` includes both calendar dates. Either bound may be omitted. The date-only upper bound becomes the beginning of the following local day, exclusively. A same-day date range is valid. Historical NULL dates never match supplied date filters.

`filter_timezone=Europe/Lisbon` selects a validated IANA zone; omission uses configured application_timezone. It is independent of display_timezone and recorded source zones. Local midnights are converted separately to UTC, so DST days can span 23 or 25 hours. SQL compares stored timestamps directly against parameterized UTC boundaries, without row casts or formatting.

From/to still accept timezone-aware ISO 8601 timestamps: the lower instant is inclusive and the upper instant is exclusive. For example, `created_at_to=2026-10-25T00:00:00Z` excludes that instant and everything after it; `created_at_to=2026-10-25` includes that entire local calendar day. Mixed date/timestamp bounds follow these same rules. Naive datetimes, invalid dates/zones, nonincreasing calculated boundaries, and exact-day plus same-field range combinations return 422. An upper calendar date that cannot advance to the following day is rejected.

Collection GET, administrator bulk PUT/DELETE and previews share predicates. Compare GET count with preview matched_count using identical criteria; separate requests can observe intervening writes. Swagger lists date/date-time alternatives and examples. Postman calendar controls are editable and unchecked by default. Enable either exact-day or range controls for a field, not both. Actual bulk requests retain confirmation and disposable-data opt-in requirements.

## Atomic array creation

POST on the eleven catalogue resources and /test accepts one object or an ordered atomic array (default maximum 300). Single responses retain their full record shape; arrays return created_count/items with full final records, independently of GET pagination and administrator bulk PUT/DELETE. See [request, validation, configuration, audit and restart contracts](BATCH_CREATION.md).
