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
