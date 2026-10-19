# 🔬 Remaining changes: implementation, performance, security and architecture

Workspace: `C:\Dev\Ouroboros`, branch `feat/initial-tables`. No commit, push or merge. Earlier working-tree changes are retained. [Detailed tier/test contracts](TIERS_AND_TEST_CRUD.md) specify migrations 009/010 and the complete endpoint/permission matrix.

## 🪜 Preservation and implementation

Migration009 adds only classification tier metadata, backfills once after inspecting existing sequence count/bounds, and creates positive/deferred-unique constraints and a trusted append trigger. Exact1..N sequences retain identical values; gaps use contiguous sequence ranks without resetting identities. The fallback is visible in the safe startup inspection event and persisted column comment. Tests upgrade empty, nine-row and gapped databases, compare all original classification values/IDs, and replay migration checksums. No nine-row limit is hardcoded. Normal records were not replaced, reseeded or modified by this task; their actual current sequence values/backfill result have not been claimed as inspected through private credentials.

The API implements atomic append/insert/move/delete/filtered-delete compaction, defaults to tier ordering and rejects bulk tier bodies with individual-PUT guidance. Membership->actor->list->record locking and deferred uniqueness permit shifts without transient uniqueness failures. Restrictive deletion and failed auditing roll back the entire operation. Internal shifts contribute to the same request's count and bounded reordering evidence; primary individual differences/target remain associated with the moved/deleted record.

Migration010 adds automatic immutable creation context to the integer-ID test table, preserving historical NULLs. All seven test CRUD route forms share full public record schemas, strict filters, UTC display, current scope checks and central audit. Individual operations use test:read/test:write for standard/supervisor; bulk mutations require administrator. Original escaped patterns, unrestricted TEXT and sequence continuity remain.

## ⏱️ Reproducible performance measurements

Command (owned synthetic infrastructure only):

```powershell
.\.venv\Scripts\python.exe scripts/benchmark_api.py --rows 5000 --classifications 100 --requests 40
```

Baseline measurement before the pagination optimization: Windows11 build26300, Python3.15.0, 16 logical host CPUs, PostgreSQL17.11 Docker image, FastAPI0.143.5, Uvicorn0.49.0, Psycopg3.3.6, Pydantic2.14.1, AnyIO4.15.1. One real loopback HTTP worker,40 thread-pool slots,8 short-lived database connection slots with5-second capacity wait, DEBUG file logging. A unique Docker project/volume, ephemeral ports and random credentials were allocated and cleaned up. Normal services/data were never selected. This is a local workstation shared with ordinary background services, not a dedicated performance laboratory.

Synthetic dataset:5,000 works with1,280-byte English synopses,5,000 test rows,100 classifications. Measured requests use new loopback HTTP connections, include JSON response reads, and exclude warm-up calls from workload statistics. Each ordinary workload has40 requests; bulk previews16, contention8, large-text8 and full-table bulk1:433 measured requests overall, zero errors. Large-text bodies contain1,150,000 UTF-8 bytes. Percentiles are interpolated from all outcomes. One bulk sample has no meaningful latency distribution despite identical p50/p95 fields in JSON. Client receive timings can end before final audit logging; the script waits separately before measuring storage/invariants.

| Workload | Concurrency | p50 ms | p95 ms | requests/s | HTTP errors |
| --- | ---: | ---: | ---: | ---: | ---: |
| Works first page | 1 | 143.161 | 192.981 | 6.795 | 0/40 |
| Works first page | 8 | 329.929 | 392.909 | 23.045 | 0/40 |
| Works text filter | 8 | 340.075 | 400.497 | 23.011 | 0/40 |
| Works deep page | 8 | 438.227 | 571.918 | 18.135 | 0/40 |
| Works by ID | 8 | 313.306 | 380.858 | 25.233 | 0/40 |
| Individual test update | 8 | 328.082 | 394.947 | 22.865 | 0/40 |
| Individual work update | 8 | 294.797 | 385.388 | 25.045 | 0/40 |
| Classification move | 8 | 922.783 | 1926.745 | 7.170 | 0/40 |
| Mixed writes | 16 | 1756.070 | 2148.215 | 8.310 | 0/40 |
| Bulk preview all works | 8 | 735.143 | 843.558 | 9.767 | 0/16 |
| Bulk update5,000 works (one sample) | 1 | 16409.206 | 16409.206 | 0.061 | 0/1 |
| Bulk plus individual contention | 8 | 269.522 | 10805.717 | 0.486 | 0/8 |
| Large Unicode test update | 4 | 587.340 | 710.663 | 5.885 | 0/8 |
| Filtered audit read | 8 | 269.249 | 469.925 | 25.440 | 0/40 |

The benchmark ended with 100 distinct contiguous classification tiers 1..100, 437 audit rows, 11,879 recorded row mutations and zero unfinished audit rows. Audit logical row data was 391,924 bytes versus 5,898,240 physical table/index bytes. Physical size includes indexes, free space and update/dead-tuple overhead; this is not a linear growth estimate. Exact large-text UTF-8 bytes, plans, package versions, index inventory and workload/status totals are in ignored `reports/performance.json`.

After the fix, a second fresh owned dataset compared both formulations with warmed EXPLAIN ANALYZE, using the same parameters and two executions per variant (the second recorded). This isolated SQL comparison ran after the regression suite finished, without simultaneous QA Docker workloads:

| Query | MATERIALIZED ms / temp blocks written | NOT MATERIALIZED ms / temp blocks written |
| --- | ---: | ---: |
| First page | 8.113 / 840 | 3.309 / 0 |
| Selective text filter | 1.972 / 0 | 3.445 / 0 |
| Deep page | 22.766 / 2532 | 9.153 / 1692 |

The first/deep-page spool cost decreased; a selective filter did more scan work (shared hits doubled from 1,000 to 2,000) and became slower in this small sample. This is an explicit tradeoff, not a claim that every query became faster. Deep sorting still spills. These are executor timings, not updated HTTP percentile measurements or statistically stable production estimates. Reproduce with `scripts/benchmark_api.py --plans-only --rows 5000 --classifications 100 --requests 8 --output reports/pagination-plans.json`. The [PostgreSQL CTE rules](https://www.postgresql.org/docs/17/queries-with.html) describe the folding/materialization tradeoff; [deferred constraints](https://www.postgresql.org/docs/17/sql-set-constraints.html) support temporary tier overlaps within a transaction.

### Findings and disposition

| Severity / area | Evidence | Disposition / practical limit |
| --- | --- | --- |
| Medium performance: global write serialization | Shared membership lock719230818 serializes catalogue and test writes across resources; moves additionally lock the classification list. Mixed16-way p95≈2.15s; a bulk operation affected competing requests. | Retained to preserve role/password races and established lock order. Narrowing it requires a coordinated authorization-lock redesign, not a local throughput tweak. |
| Medium performance: per-row transactional audit overhead |5,000-row bulk took16.4s; each row updates the same request audit row. Storage shows physical amplification. | Retained mandatory atomic evidence. Bulk returns counts, not copied rows, but still costs O(affected rows) audit work. The30-second statement timeout and connection/lock waits can reject larger workloads; no maximum safe batch size or production capacity is inferred. |
| Low performance: avoidable full-row materialization | Baseline EXPLAIN: first-page20.766ms/840 temporary blocks written; deep-page31.463ms/2532 blocks. | Fixed shared pagination CTE to NOT MATERIALIZED. Count and page remain one statement/snapshot, with unchanged driver parameters. PostgreSQL may plan separate filtered scans without storing every wide row. Follow-up plan comparison is recorded separately; baseline HTTP numbers above are not post-fix claims. |
| Low performance: repeated connections/count costs | Ordinary protected requests use entry/auth/business/finalization connections sequentially. Provider caps simultaneous connections at8; current account cannot be cached safely without revocation design. Counts scan all matches; deep OFFSET discards preceding records. | No row-level Python N+1 query loop for pages. Keep current semantics; a bounded reusable pool, keyset paging or optional counts would need explicit later contracts. SQL templates are also read repeatedly; disk access is a small unmeasured component. |
| Low index coverage/growth | Tier's unique index supports tier order; common metadata sequence ordering and arbitrary ILIKE/substrings have no universal supporting index. Existing PK/unique/FK-leading indexes and audit lookup indexes were inventoried. | No blindly duplicated indexes were added. Counts, selectivity and arbitrary public sort choices make one index per field inappropriate. Consider measured sequence/audit-order or trigram indexes for a larger representative dataset, with write/storage costs assessed first. |

## 🛡️ Security review and tools actually run

Official [OWASP ASVS 5.0.0](https://owasp.org/projects/asvs) and Cheat Sheets for [Authentication](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html), [Authorization](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html), [Password Storage](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html), [Logging](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html), [Input Validation](https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html) and [Error Handling](https://cheatsheetseries.owasp.org/cheatsheets/Error_Handling_Cheat_Sheet.html) were consulted. Review checks cover current roles/scopes/version, transaction authority, strict confirmation/known filters, whitelisted identifiers/parameterized values, immutable echoes, tier locking, Argon2id and token revocation, nested redaction, complete password/token body omissions, safe headers/errors, audit atomicity, stream failures/cancellation, aware timezone validation and exact infrastructure cleanup. Passing checks is not blanket ASVS compliance or proof of no vulnerabilities.

| Tool / scope | Observed result / disposition |
| --- | --- |
| Bandit1.9.4, app and start.py |7 LOW,0 MEDIUM,0 HIGH; no scanner errors. Four medium SQL-composition heuristics in static compaction code were eliminated by using literal SQL rather than concatenated fixed fragments. |
| B105 | Literal `bearer` is a public protocol label, not a password; retained without blanket suppression. |
| B110 | Last-resort audit fallback deliberately does not recurse if the file sink also fails. Required limitation; no fabricated persistence. |
| B404/B603 and Windows B607 | Reviewed bounded subprocess argument lists/shell=False and trusted local Docker/ACL tools. Windows ACL utility still relies on the operator's trusted executable PATH; no HTTP input selects shell commands. |
| Ruff0.17.1, F correctness rules, app/start.py |No remaining findings. Seven unused-import/variable issues were removed; not a claim of all-rule style compliance. |
| pip-audit2.10.1, requirements.txt and requirements-dev.txt |No known vulnerabilities reported for resolved declared dependency sets at the time of the run. Tool dependencies are optional/pinned separately in requirements-review.txt; vulnerability databases can change. |
| pip check / compileall |No broken requirements; source compilation passed. |
| SonarLint/SonarQube for IDE |Did not run. Standard VS Code extension inventory returned no Sonar extension; CLI inventory also emitted a local log-directory permission warning. Bandit/Ruff are the actual static tools used. |

Additional residual findings: **Medium availability**—unrestricted authenticated TEXT inputs and responses still consume business/parser memory and SQL work even though audit/log capture is bounded. The measured large payloads succeeded; this does not bound arbitrary client memory use. Deployment request/concurrency budgets need a separately agreed policy. **Medium audit operations**—no durable replay or retention/reconciliation is introduced; outages/crashes can leave gaps or in_progress transport metadata. Mandatory mutation evidence remains fail-closed and committed evidence survives failed finalization. **Low local trust**—database masters can bypass/tamper with application invariants; application read-only audit APIs are not cryptographic tamper resistance.

## 🏗️ Architecture assessment

Routers declare permission/HTTP contracts; schemas publish fixed resource fields and strict query controls; repositories own transactions; ClassificationOrdering owns ordered-list mechanics; SQL templates compose trusted identifiers and parameters; central audit and datetime helpers remain shared. Integer test CRUD reuses paging/predicates/templates and audit/UTC contracts without pretending test IDs are catalogue IDs. Generated resource endpoints remain based on a fixed descriptor, not client-selected tables or columns.

Transaction ownership is clear: membership/actor/list/record locks are acquired in one order, intermediate uniqueness is deferred, business/audit evidence commit together, and transport finalization uses a later short transaction. Code review found no application row-by-row page fetch N+1 pattern. Tier shift samples are bounded; SQL still processes each affected row, an intentional cost rather than constant-time reordering.

Maintainability limitations: CatalogueError is reused by TestRepository despite its catalogue-specific name, and repositories retain some parallel transaction/policy structure because test scopes differ from catalogue roles. Moving errors or lock helpers into a shared module is a future extraction when further resources justify it, not a reason for an unrelated rewrite now. Public query/order enums, canonical Postman and single QA catalogue are synchronized; actual browser/Postman JavaScript execution is separate evidence.

## 🧪 Verification and normal runtime

The full `scripts/run_checks.py` completed with exit0: **128 tests PASS,0 FAIL,1 optional SKIP**; **63 scenarios PASS,0 FAIL,1 optional SKIP,4 MANUAL**. The fixed-port case was skipped because normal database port6669 is occupied; mandatory integration used temporary ports. Stable scenarios16.1–16.6 map new isolated tests and matching manual actions. Actual Swagger UI/Postman JavaScript, physical terminal and hosted-workflow checks remain manual; overall approval stays PENDING_MANUAL_VALIDATION. Synthetic9-row preservation evidence is not a claim of a read-only fingerprint of normal records. Compilation, generated-plan traceability, dependency consistency and whitespace checks also passed.

No normal migration or record mutation was performed. Interactive credentials are required for normal startup, so current normal sequences and the actual normal backfill strategy remain pending that authorized startup. No secret files or private Postman YAML/metadata were read. Listener inspection is read-only and never stops a process; unrecognized arguments are omitted to avoid revealing secrets. The latest listener/container state belongs in the completion note.

Final read-only snapshot: `ouroboros-postgres-1` healthy on127.0.0.1:6669; `foundation-postgres-1` stopped; no TCP listener on6969. All owned test/benchmark containers were removed. Earlier listener11724 used the system Python executable and was not confirmed as this workspace's launch, so it was never stopped/restarted; it was absent at the final check. Existing normal runtime changes outside these read-only observations were not attributed to this task.

Final focused rerun: all six remaining-phase tests passed, including explicit last-position insertion, clearing a populated unreferenced classification list with sequence continuity, and real API reorder evidence at the256-byte audit limit. Three QA traceability checks and generated-plan consistency also passed after documentation/client updates. Tool versions, findings and sanitized results are included in the public review bundle; no production-readiness or full manual-approval claim is made.

After identifying and stopping only a confirmed Ouroboros terminal with Ctrl+C:

```powershell
Set-Location -LiteralPath C:\Dev\Ouroboros
.\.venv\Scripts\python.exe start.py
```

Keep existing database/master choices and answer masked credential prompts. Read `Classification tier backfill inspected`: sequence1..9 stays1..9, otherwise the explicit rank fallback is reported. Do not recreate/reseed the nine rows. Swagger: **http://localhost:6969/docs**.
