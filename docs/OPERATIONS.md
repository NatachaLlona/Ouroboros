# ⚙️ **Installation, operation and troubleshooting**

Use the [project README](../README.md#setup-and-run) for a quick developer start and [QA setup](QA_SETUP.md) for fully guided Windows installation, independent master prompts, Swagger, Postman and isolated evidence. Install `requirements-dev.txt` when running QA checks; `requirements.txt` is sufficient for the application. The canonical conventions remain [NEXTGENERATION.md](../NEXTGENERATION.md).

## ▶️ **Lifecycle and data safety**

Catalogue CRUD is described in [CATALOGUE_API.md](CATALOGUE_API.md). Migration 006 extends roles; 007 adds creation/source timezone context and 008 adds central audit storage. Use disposable databases for destructive QA; administrator bulk PUT/DELETE require confirm=true, accept strict filters, support dry_run previews, roll back on constraints and never reset sequences. Normal startup remains interactive and creates no catalogue seed data.

Start with the explicit virtual-environment interpreter: `.\.venv\Scripts\python.exe start.py`. Paths resolve from the source root, including absolute-path invocation. Startup requires Docker Engine, explicit project identity, independent database/master choices and correct master password. It migrates the selected database and explicitly recovers the first administrator if needed. It does not automatically promote an existing ID. With an active administrator, further creation/role changes belong to APIs.

Ctrl+C stops the API and releases in-memory provider/signing-key references; PostgreSQL keeps running. Follow [safe stop/start commands](../README.md#stop-and-restart-without-deleting-data), using the **configured identity**, never another project's name. Retain the original volume and protected initialization file. POSTGRES_DB/POSTGRES_USER cannot change existing initialized roles/databases. Do not use volume-removal flags on normal shutdown. Applied migrations are immutable and checked on startup; add new numbered files for future changes.

## 🧱 **Create a derived project**

1. Copy only source/templates into a new folder/repository. Do not copy `.app.config`, `.secrets`, logs, reports, virtual environments, private Postman settings or data volumes.
2. Create a fresh virtual environment, install requirements and copy the example only if no local config exists.
3. Choose a **unique lowercase infrastructure.project_name**, blank initial workspace, available distinct API/database host ports, and independent database/master names. Keep required timeouts/logging/auth settings. The [AcmeService example in the README](../README.md) is instructional, not an implemented application.
4. Run start.py in that folder, choose its own master password and first API administrator. It gets fresh protected secrets and `<project_name>_postgres_data`.
5. Use its own Postman base URL. Never adopt a foreign container or orphan volume. A mismatched workspace/config/ownership receipt is a stop condition, not permission to delete the older installation.

## 🪵 **Investigate by request ID**

Copy **X-Interaction-ID** from a response, then search that exact 24-digit string in the current execution's UTF-8 `logs/application_*.log`. The field order remains LEVEL | INTERACTION_ID | DATETIME | CATEGORY | METHOD PATH | COMPONENT | CLASS | SOURCE:LINE | MESSAGE | CONTEXT. Widths are minimums, never truncation. Application events have a blank ID. Console color affects only the level on compatible interactive terminals; NO_COLOR/redirection disables it, and files never contain ANSI.

```text
INFO     | 202610181133110482759163 | 2026-10-18T11:33:11.048+01:00 | request     | GET /test | ouroboros | - | app/main.py:145 | HTTP request finished | {"status": 200, "response_started": true, "outcome": "failed", "duration_ms": 12.4}
```

This **illustrative failed streaming response** retains HTTP 200 because headers had already been sent. `outcome` describes execution: **completed** means normal handling including expected 4xx/5xx; **failed** means unexpected processing/send failure; **cancelled** means cancellation. If the ASGI send callback never accepted a status, it is **null**, with response_started false. The server can only report callback acceptance, not prove that a remote client received bytes. No second response is attempted after a send failure or accepted headers. The original safe category/frames are recorded once; the propagated server exception has a fixed safe message and suppressed private context.

DEBUG includes a recursively sanitized body object, or bounded truncated preview with truncated=true. `/token`, Authorization, passwords, hashes and tokens stay excluded. Control characters are escaped; one event remains one line. INFO suppresses DEBUG details. Never put secrets under arbitrary free-text fields; key-based redaction cannot detect every hidden secret.

## 🏃 **Checks, reports and troubleshooting**

Run **`.\.venv\Scripts\python.exe scripts/run_checks.py`**. [QA setup](QA_SETUP.md) explains prerequisites and result categories; the [generated plan](QA_TEST_PLAN.md) supplies every stable case identity and mapped test. Reports in ignored `reports/` are sanitized Markdown, JSON and JUnit, with distinct scenario/test totals. Missing mandatory tools/preparation/skipped required automation returns nonzero. Manual/UI/pipeline approval is never inferred from these checks.

| Problem | Investigation |
| --- | --- |
| Startup error | Safe stage/error_type/source frames; never print raw config or private exception text |
| Connection refused | API terminal running, correct host/port, Docker Engine and startup status |
| Health 503 | Database stopped/unavailable, wrong QA port or connection capacity |
| Authentication 401 | Correct API account, current active state, valid unexpired token and selected database |
| Authorization 403 | Current role, issued/current test permissions and local variable shadowing |
| Conflict 409 | Duplicate username or last active administrator rule; can be expected PASS in negative cases |
| Validation 422 | Exact field/type, fixed role set, page>=1/page_size 10–50, positive BIGINT id |
| BLOCKED preparation | Install declared dependencies/start Docker; do not mark subsequent scenarios FAIL just because preparation failed |
| Python 3.15 cannot compile PyYAML | Prefer Python 3.12 for CI parity, or use its supported pure-Python build as documented in QA setup |

No GitHub execution, visual Swagger clicks, physical terminal appearance or Postman sandbox run is established merely by creating files or passing equivalent HTTP tests. Follow the manual evidence cases before declaring Ouroboros fully validated.

## 🧾 Audit, UTC dates and filtered bulk operations

See [the phase contract guide](AUDIT_DATETIME_BULK.md) for migrations 007–008, exact columns, central audit transaction guarantees and outage/crash gaps, versioned error envelopes, UTC/source/display timezone rules, immutable creation dates, and administrator previews/confirmed filtered mutations. The current catalogue has 77 route forms plus two read-only audit routes. Supervisor has individual CRUD and audit reads; standard has neither; administrator alone bulk mutates. Historical creation dates/context stay NULL. No automatic audit retention or durable replay is provided.

For manual QA use owned disposable storage and fresh private accounts. Inspect Swagger controls, complete a GET-to-PUT round trip with original display, preview a filtered change, confirm it explicitly only in disposable storage, and query its X-Interaction-ID in api_audit_logs. Verify standardized codes/header/log/audit correspondence, whole token/password body omissions and restricted audit reads. Record actual UI/Postman JavaScript evidence separately. Never enable destructive examples against normal data.

## 🪜 Classification tiers and complete test CRUD

Migrations009–010 add independent classification tier positions and complete integer-ID test CRUD with shared creation dates, UTC presentation, strict filters and confirmed administrator bulk operations. See [the authoritative contracts](TIERS_AND_TEST_CRUD.md) for the one-time inspected backfill, atomic append/insert/move/delete behavior, bulk tier exception, scope matrix and restart instructions. Never reseed or replace the existing nine normal classifications. Destructive QA remains isolated; review measurements and findings are documented separately.

## Object and array creation

POST /test and the eleven catalogue POST creation endpoints accept one object or a nonempty atomic array. Single-object 201 responses remain full records; array 201 responses contain created_count and full items in request order, without GET pagination. Each item uses the existing create schema and creation permissions. See [the batch creation contract](BATCH_CREATION.md) for zero-based item errors, transaction/audit guarantees, classification tiers, configurable api.max_batch_size (default 300) and api.max_creation_body_bytes (default 4 MiB), client examples and restart instructions. Capture/inspection budgets are independent and remain bounded. No migration, reset or seed is required; preserve existing normal records and leave unconfirmed listeners alone.

## Migration011 and authentication limits

Apply platform migration011 through start.py using existing interactive master credentials before serving updated platform routes. Stop only a confirmed workspace-owned API terminal; do not restart unconfirmed listeners or recreate infrastructure. The single-worker process has fixed 300-second login admission windows (10/account, 50/direct client, 10000 hashed entries maximum). Restart resets these process-local counters. Built-in Uvicorn startup disables proxy headers. New passwords use 15?1024 Unicode characters; no existing hashes are rewritten. See [migration/restart and field contracts](BACKEND_REVIEW.md).

## Frontend startup and browser configuration

Build Angular once before Python startup: from frontend/, run npm ci, npm run build and npm test with compatible Node 24.15.0. No separate frontend server or new migration is required. Do not rebuild on every normal start. See [exact Windows commands and asset deployment](ANGULAR.md). Keep migrations through 011 for the platform fields. Before normal startup, explicitly configure browser.origin=http://localhost:6969 and browser.allow_loopback_http=true for local development; never overwrite existing private settings. Missing browser settings default to HTTPS and HTTP disabled. The loopback-only development cookie omits Secure; HTTPS uses a Secure __Host- cookie. Sessions use auth.token_ttl_seconds, are bounded to 10000, survive reload and clear on process restart. Existing one-worker/proxy-header rules remain. Use .\.venv\Scripts\python.exe start.py and open http://localhost:6969/. Identify launch ownership before any restart; leave unknown listeners alone. [Exact configuration and walkthrough](FRONTEND.md).

## Operator-selected refinement QA ports

The main application remains 6969, normal PostgreSQL host 6669 and container PostgreSQL 5432. The owner selected 2469 for Angular preview/HTTP QA and 2424 for disposable PostgreSQL. Set OUROBOROS_QA_DB_PORT=2424 and OUROBOROS_QA_API_PORT=2469 before scripts/run_checks.py. Checks and preview must run sequentially; occupied ports fail without selecting another. The workflow_dispatch inputs require the operator to choose both distinct QA ports. No normal configuration, secrets or catalogue records are used by disposable tests. See [ANGULAR.md](ANGULAR.md) for exact Windows build/test/start commands and current UI walkthrough.

The owner additionally selected **4242** for the second disposable PostgreSQL cluster used concurrently by the derived-project isolation test. Set **OUROBOROS_QA_DERIVED_DB_PORT=4242**. This is QA-only; never substitute it for normal 6669 or HTTP/Angular 2469. The hosted workflow requires all three QA port inputs from its operator.
