# 📚 **Ouroboros documentation**

| Reader / subject | Guide |
| --- | --- |
| Project overview and quick start | [Project README](../README.md) |
| QA tester, no code knowledge required | [Generated QA test plan](QA_TEST_PLAN.md) |
| Windows setup, Swagger/Postman and report instructions | [QA setup source](QA_SETUP.md) |
| Component responsibilities, data and transactions | [Architecture](ARCHITECTURE.md) |
| Catalogue schema, relationships and pending decisions | [Catalogue model](CATALOGUE.md) |
| Catalogue CRUD, supervisor permissions, filter/order matrix and safe deletion | [Catalogue API](CATALOGUE_API.md) |
| API, authentication, roles and pagination | [API contracts](API.md) |
| Startup/shutdown, logs, troubleshooting and derived projects | [Operations](OPERATIONS.md) |
| Stable scenario catalogue | [qa/scenarios.json](../qa/scenarios.json) |
| Developer conventions and Git workflow | [NEXTGENERATION.md](../NEXTGENERATION.md) |
| Historical Foundation review (not current Ouroboros evidence) | [Final review](FINAL_REVIEW.md) |
| Current next-phase implementation, checks and limitations | [Next-phase review](NEXT_PHASE_REVIEW.md) |
| Classification tiers and complete integer test CRUD | [Tier/test contracts](TIERS_AND_TEST_CRUD.md) |
| Atomic object/array POST, 300-item batches, byte limits and restart | [Batch creation](BATCH_CREATION.md) |
| Current performance/security/architecture review | [Remaining phase review](REMAINING_PHASE_REVIEW.md) |

**Maintenance:** QA case IDs/names/actions live in the catalogue, not a separate handwritten list. QA_TEST_PLAN.md is generated from that catalogue and QA_SETUP.md. Read the plan before testing; do not treat a documented case as executed. The normal installation's private files/data never belong in an evidence package.

## 🧾 Audit, UTC dates and filtered bulk operations

See [the phase contract guide](AUDIT_DATETIME_BULK.md) for migrations 007–008, exact columns, central audit transaction guarantees and outage/crash gaps, versioned error envelopes, UTC/source/display timezone rules, immutable creation dates, and administrator previews/confirmed filtered mutations. The current catalogue has 77 route forms plus two read-only audit routes. Supervisor has individual CRUD and audit reads; standard has neither; administrator alone bulk mutates. Historical creation dates/context stay NULL. No automatic audit retention or durable replay is provided.

For manual QA use owned disposable storage and fresh private accounts. Inspect Swagger controls, complete a GET-to-PUT round trip with original display, preview a filtered change, confirm it explicitly only in disposable storage, and query its X-Interaction-ID in api_audit_logs. Verify standardized codes/header/log/audit correspondence, whole token/password body omissions and restricted audit reads. Record actual UI/Postman JavaScript evidence separately. Never enable destructive examples against normal data.

## 🪜 Classification tiers and complete test CRUD

Migrations009–010 add independent classification tier positions and complete integer-ID test CRUD with shared creation dates, UTC presentation, strict filters and confirmed administrator bulk operations. See [the authoritative contracts](TIERS_AND_TEST_CRUD.md) for the one-time inspected backfill, atomic append/insert/move/delete behavior, bulk tier exception, scope matrix and restart instructions. Never reseed or replace the existing nine normal classifications. Destructive QA remains isolated; review measurements and findings are documented separately.
