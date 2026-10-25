## 🧭 **Read this first**

For catalogue CRUD scenarios **14.1–14.7**, use the [resource/filter/permission matrix](CATALOGUE_API.md) and new canonical Postman folders. Administrator creates supervisor explicitly; standard still has no catalogue access. All collection GETs now show ordering enums. DELETE examples are skipped by default: only in disposable data, explicitly select the request, set the private local catalogue_destructive_opt_in=isolated, and for DELETE all change confirm=false to true. Never run that flow against normal records. POST/PUT/GET expose the same complete record; copy a GET body to PUT with unchanged metadata and server-controlled added_at. Troubleshooting and exact status expectations are in the CRUD guide.

This guide is for a Windows tester with no prior Ouroboros, Python, Docker, OAuth2 or Git experience. **Use a separate QA folder and database. Never test against the owner's normal installation.** A green automated report verifies code/HTTP checks, not the appearance or behavior of a desktop interface. Record manual evidence separately. Expected **400, 401, 403, 409 and 422 are PASS** when the case asks for them.

### 🧰 **Programs and terms**

| Program | Official download / purpose |
| --- | --- |
| Python 3.10 or newer (3.12 recommended for matching CI) | [Python for Windows](https://www.python.org/downloads/windows/): runs the application and checks; enable the installer option to add Python to PATH |
| Docker Desktop | [Docker Desktop for Windows](https://docs.docker.com/desktop/setup/install/windows-install/): runs an isolated PostgreSQL server; follow its Windows/WSL2 requirements and restart Windows if requested |
| Postman Desktop | [Postman downloads](https://www.postman.com/downloads/): sends API requests and executes collection assertions |
| Git (only when receiving a repository URL) | [Git for Windows](https://git-scm.com/downloads/win): downloads source history; a sanitized source package is also acceptable |
| VS Code (optional) | [VS Code](https://code.visualstudio.com/download): editor with a terminal; ordinary Windows PowerShell also works |

An **API** accepts requests at URLs. **Swagger** is the interactive web page at `/docs`. A **Bearer token** is the temporary credential returned after API login. The PostgreSQL **master user** prepares the database and is separate from API accounts. A **container** runs the database; its **volume** stores data after it stops. A Python **virtual environment** is a project-only dependency folder, `.venv`.

### 📦 **Receive clean source and create a QA installation**

1. Ask the developer for the exact revision/source package being tested. Record that public revision with your evidence. Obtain access to the private repository if cloning it. Do not download another developer's configuration, secrets or database volume.
2. Open PowerShell. A terminal is a window where you enter the commands shown below. Open Docker Desktop and wait until its Engine is running in **Linux containers** mode.
3. Put the supplied source in a **new** folder, such as `C:\Dev\Ouroboros-QA`. If using Git, replace `REPOSITORY_URL` with the URL supplied by the developer: `git clone REPOSITORY_URL C:\Dev\Ouroboros-QA`. Do not type that placeholder literally. Do not copy `.app.config`, `.secrets`, logs, reports, `.venv`, private Postman environments or Docker volumes.
4. Enter these commands from the new folder. Stop and ask for help if any command shows an error; a missing program is **BLOCKED preparation**, not a successful test.

```powershell
cd C:\Dev\Ouroboros-QA
python --version
docker version
docker compose version
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
if (Test-Path -LiteralPath .app.config) { throw 'Use a fresh QA folder; existing configuration must not be overwritten' }
Copy-Item -LiteralPath .app.config.example -Destination .app.config -ErrorAction Stop
notepad .app.config
```

**Only copy the example when `.app.config` does not exist.** If the folder already contains one, do not overwrite it; use a new QA folder. In Notepad, retain all other JSON fields and change only these choices. Commas, quotes and braces must remain valid JSON. No password goes into this file.

If installing PyYAML on the local Python 3.15 reports a missing C++ compiler, its optional native extension is not needed for these checks. Use the supported pure-Python build (or use Python 3.12 as CI does):

```powershell
$env:PYYAML_FORCE_LIBYAML = '0'
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
Remove-Item Env:PYYAML_FORCE_LIBYAML
```

This build choice is supported by [PyYAML's distribution setup](https://github.com/yaml/pyyaml/blob/6.0.3/setup.py); it does not disable YAML validation.

| Field | QA example | Meaning |
| --- | --- | --- |
| `host` / `port` | `localhost` / `6969` | QA API / Swagger port |
| `infrastructure.project_name` | `ouroboros-qa-manual-yourinitials` | Replace the suffix with your own unique lowercase name |
| `infrastructure.workspace` | empty string | Bound to this new directory on first startup |
| `database.name` / `database.user` | `ouroboros_qa` / `ouroboros_qa` | QA database / its new master role |
| `database.port` | `6669` | QA PostgreSQL port on Windows; container still uses 5432 |
| `api_users.last_api_username` | empty string | Convenience only; not an account |
| `logging.level` | `DEBUG` | Includes sanitized body diagnostics; later compare INFO |

Use the standard ports in the main QA path. If either is occupied, follow the alternative-port troubleshooting below; never stop that service. Run `Get-NetTCPConnection -State Listen -LocalPort 6969,6669 -ErrorAction SilentlyContinue`; any returned row means a chosen port is occupied. **Do not stop the other service.** Choose new ports and update Postman's base URL. The normal defaults remain API 6969 / database 6669.

### ▶️ **Start and answer the prompts**

```powershell
.\.venv\Scripts\python.exe start.py
```

Keep this terminal open while testing. **Do not paste passwords into commands, reports or screenshots.** Maintain your test credentials privately (for example in your approved password manager), never in a shared export.

| Prompt | Exact action in this fresh QA installation |
| --- | --- |
| Keep configured database? | Press Enter to keep `ouroboros_qa`; choosing another name is independent of the master user |
| Keep configured master user? | Press Enter to keep `ouroboros_qa` |
| Master database password | Suggested for disposable QA only: `OuroborosQA-Database-2026!`; enter it manually, with asterisks expected. Reuse it on every restart of this volume |
| New API administrator username | Suggested API name: `admin`; enter it manually; this is not the master user |
| API administrator password | Suggested for disposable QA only: `AdminPassword-2026!`; enter/store it locally |

If instead you see **promote/create**, this database already contains API users but no active administrator. Confirm it is your QA database; choose `promote` and an explicitly known active API username, or `create` and a new unique username. Never guess a first ID. Once an active administrator exists, later startups ask only for the master password and skip API enrollment. Save the original administrator ID returned by **GET /users**; do not assume it is 1.

### 🌐 **Swagger login and switching accounts**

1. Open a browser at **http://localhost:6969/docs** (substitute your API port). Open **GET /health → Try it out → Execute**; no login is required. Read the response status/body in the **Responses** area.
2. Click **Authorize**, fill the **API** username/password, choose `test:read` and `test:write`; an administrator may also select `users:manage`. Leave client fields empty. Click **Authorize**, then **Close**.
3. For any case below, expand its method/path, click **Try it out**, fill the query/path fields or JSON body, and click **Execute**. The token is sent automatically. Save **X-Interaction-ID** from response headers as non-secret evidence.
4. **To switch users:** click **Authorize → Logout → Close**, reopen **Authorize**, enter the next API account, select only that account's allowed scopes, authorize and close. Do not rely on changing a username in `/token` to switch global authorization. Standard users must not select `users:manage`; requesting it produces expected 403.
5. **Try it out on POST /token** accepts form fields: username/password required, grant_type=`password`, scope omitted or space-separated allowed names, client_id/client_secret empty. Optional **Send empty value** can be unchecked or checked; empty grant_type uses password. This returns a token but does not establish global authorization. Never screenshot the returned token.
6. Old-token promotion/demotion cases use **Postman**, because its separate saved variables prevent Swagger's Authorize dialog from silently obtaining a new token.

### 📮 **Import Postman once and configure local values**

1. Postman Desktop → **Import → Files** → select **postman/Ouroboros.postman_collection.json** from this QA folder. This is the sole canonical **Collection v2.1**. Do not import the YAML directory; three historical List all entries YAML copies contain old assertions. Do not delete personal YAML/customizations.
2. To update an older import, retain your private environment/custom requests first, then choose replacement if offered. Otherwise archive/remove only the identified old imported collection and import this JSON once. Avoid two same-named active imports.
3. Create a **private local environment**, select it, and set `base_url=http://localhost:6969`. Set credentials only locally and mark passwords sensitive. A placeholder such as `{{admin_username}}` must resolve before sending. Do not share/sync/export secrets.
4. Basic requests 01–08 use `api_username`/`api_password`, captured `access_token` and `test_id`. Run 02 then 03 before filters. Request 04 has **Params** `id` and `value` unchecked: neither = unfiltered page, one = that filter, both = AND. Keep `%Ouroboros%` raw in Params; the transmitted URL must have `%25Ouroboros%25`, not `%2525`.
5. Administrative requests 09–20 use `admin_username`/`admin_password` for your existing administrator, new unique `standard_username`/`standard_password`, and new unique `additional_admin_username`/`additional_admin_password`. They create persistent accounts; use new names on reruns. Request 09 captures `admin_token`; 10 captures `standard_user_id`; 12 captures `standard_token`.
6. The **QA role lifecycle** folder continues with promotion/reuse/demotion. Run 09, 10 (role is **omitted**), 12 and then the lifecycle folder in order. It captures `old_standard_token`, `promoted_token` and `admin_user_id` without assuming IDs. Run 09–20 separately if checking all earlier scenarios; repeat creation needs fresh usernames.
7. Keep captured tokens/IDs in **collection scope**, without empty environment variables shadowing them. Do not edit Authorization manually except for the explicit invalid/missing-token cases. Open each request's **Tests / Test Results** to see assertions prefixed with catalogue IDs. Status 401/403/409/422 can mean PASS for negative cases.
8. Record only status, public metadata, interaction ID and assertion results. Redact Authorization, token responses, password fields and environments before evidence capture. Clear all captured credentials/tokens/IDs before exporting; prefer the unchanged versioned JSON.

### 🔐 **Pagination and administrator reset requests 61–76**

Request **61 - Pagination example (page 2, size 10)** requires the basic `access_token` from request 02. Open **Params**: edit page/page_size, toggle the unchecked id/value filters, and retain raw patterns for single URL encoding. `count` is all matching records; page 2 can legitimately have empty items. The canonical JSON contains one List all entries request; do not import historical local YAML copies alongside it.

Run **62–76** as a separate ordered reset sequence in a disposable QA database. Set `admin_username` and **reset_admin_password** to a current administrator's credentials (after earlier self-password cases, use its latest password). Set a fresh **reset_target_username**, private **reset_old_password** and a distinct **reset_new_password**. Supply an existing unrelated **standard** account via **reset_peer_username/reset_peer_password**, using its latest credentials. Do not shadow automatically captured reset tokens/IDs with empty environment variables. Request 63 persists a new target, so reruns need a fresh username. Requests capture the real target ID and each token automatically.

Expected negatives are 403 for standard callers, 401 without authentication or after revocation, 404 for a missing target and 422 for empty input. Success is empty 204; old target password fails, new password succeeds, and peer/admin tokens remain valid. For self-target rejection, obtain the acting administrator's actual ID through GET `/users`, call PUT `/users/{that_id}/password`, expect 400, then use `/users/me/password` with current-password verification. Record only sanitized status, interaction ID and assertions. Never export captured reset variables. HTTP replay tests do not execute Postman's JavaScript sandbox or verify checkbox rendering.

### ⏹️ **Stop, restart, inspect logs and controlled QA-only database changes**

Press **Ctrl+C** in the application terminal to stop the API; PostgreSQL remains running. Restart using the same command and QA master password. To stop/start **only this QA database**, open a second PowerShell terminal in your QA folder:

```powershell
$qaConfig = Get-Content -Raw -Encoding UTF8 .app.config | ConvertFrom-Json
$qaProject = $qaConfig.infrastructure.project_name
$env:OUROBOROS_DB_NAME = $qaConfig.database.name
$env:OUROBOROS_DB_USER = $qaConfig.database.user
$env:OUROBOROS_DB_PORT = [string]$qaConfig.database.port
$env:OUROBOROS_DB_SECRET_FILE = (Resolve-Path .secrets/postgres_password).Path
docker compose -p $qaProject stop postgres
docker compose -p $qaProject start --wait postgres
```

Never add `--volumes`, delete `.secrets`, change the normal installation or paste master passwords in commands. Initialization secrets are protected plaintext files, not encrypted storage. Each POST persists a record; role/user cases also persist changes. Keep the QA volume if you need to repeat persistence checks.

For the **inactive-user** case only, change the captured QA user's state using these commands, with the QA container running. Paste the actual numeric `standard_user_id`; do not use a guessed ID. Run only in your isolated QA directory, after checking `$qaProject` has your QA identity. This uses the container's local master connection and does not add an API for activation.

```powershell
$qaStandardId = [long](Read-Host 'Paste the captured standard_user_id')
if ($qaStandardId -le 0) { throw 'Expected a positive captured ID' }
docker compose -p $qaProject exec -T postgres psql -U $qaConfig.database.user -d $qaConfig.database.name -c "UPDATE public.api_users SET is_active=false WHERE id=$qaStandardId"
# Restore the same QA account after the negative checks:
docker compose -p $qaProject exec -T postgres psql -U $qaConfig.database.user -d $qaConfig.database.name -c "UPDATE public.api_users SET is_active=true WHERE id=$qaStandardId"
```

Find the current `logs/application_*.log`, open it in VS Code/Notepad, and search the response's exact **X-Interaction-ID**. Its final `HTTP request finished` event has `outcome`: **completed** for normal processing (including expected 4xx/5xx), **failed** for unexpected processing/send failure, or **cancelled**. `status` is the status actually handed to the server, or `null` with `response_started: false` if no status was sent. A failed streamed response can retain status 200; outcome must still be failed. There is no public fault-injection endpoint: use the mapped automated middleware test for this condition.

For JSON files/PowerShell examples with Unicode, use `Get-Content -Raw -Encoding UTF8`; send `[System.Text.Encoding]::UTF8.GetBytes($json)` with Content-Type `application/json; charset=utf-8`. Save PowerShell 5.1 scripts containing emoji as UTF-8 **with BOM**. In Postman, choose Body → raw → JSON and keep literal Unicode.

### 🏃 **One-command automated checks and evidence**

```powershell
.\.venv\Scripts\python.exe scripts/run_checks.py
```

This command checks Python/dependencies/Docker, provisions **randomly named disposable databases/volumes with random credentials and available ports**, runs mapped unit/integration tests, and cleans only resources created by those tests. It never asks for normal credentials or reads normal secrets/configuration. It may take several minutes and download the pinned PostgreSQL image. Do not interrupt Docker during the run. Reports are **reports/summary.md**, **reports/results.json** and **reports/junit.xml**, ignored by Git. Test exception text/output is excluded to prevent secret exposure; reproduce a failed mapped selector only in isolation. Scenario totals differ from test totals because a scenario can require several checks and checks can support several scenarios.

| Result | Meaning |
| --- | --- |
| PASS | All mapped automated tests passed; manual evidence still separate for both-type scenarios |
| FAIL | A required verification failed |
| BLOCKED | Required tool, fixture, earlier lifecycle phase or scenario dependency failed |
| SKIP | A check was intentionally omitted/unavailable; optional default-port checks may skip occupied ports |
| MANUAL | Human/interface evidence is required; no automated PASS is claimed |

The command returns nonzero if mandatory automation fails, is blocked or skips. `--unit-only` is an intentionally **partial** diagnostic run and returns nonzero; `--preflight-only` checks tools only and is never QA approval. A successful automated run is **not full QA sign-off** while manual evidence is missing. Fixed-port checks are optional and reported separately; occupied services are never stopped. On interruption or external machine failure, inspect ownership before cleanup; never delete resources by a broad Ouroboros name prefix.

### ☁️ **Run and read GitHub Actions**

After a maintainer publishes the workflow to the repository's default branch, open the repository → **Actions → Ouroboros QA checks → Run workflow**, select the intended branch/revision, and run. You need permission to run repository workflows. Open that run: preparation, scenarios and reports are separate visible steps. On the run's **Summary**, review the same scenario IDs and totals. Under **Artifacts**, download **ouroboros-qa-reports**, unzip it and open summary.md/results.json/junit.xml. Attach only sanitized evidence to your QA record. See [GitHub's manual-run guide](https://docs.github.com/en/actions/managing-workflow-runs/manually-running-a-workflow) and [artifact guide](https://docs.github.com/en/actions/tutorials/store-and-share-data).

**A local workflow file is not evidence of a GitHub execution.** Record the actual run URL/revision/result before signing off pipeline behavior. Artifacts are attempted even after failure; a failed dependency/tool installation can prevent report creation, which must be recorded as blocked preparation.

### 🛠️ **Preparation troubleshooting**

| Symptom | Action / result |
| --- | --- |
| `python` not recognized | Install Python, enable PATH, reopen PowerShell; preparation remains BLOCKED |
| Package installation fails | Confirm internet access and correct virtual-environment path; do not substitute a global Python installation |
| Docker/Engine unavailable | Start Docker Desktop, wait for Linux Engine; follow its Windows/WSL2 instructions |
| JSON configuration error / identity blank | Reopen only QA `.app.config`, repair JSON / choose unique project identity |
| Foreign workspace/volume ownership error | Stop; choose fresh QA configuration/secrets/identity. Never adopt or delete the other volume |
| API port occupied | Choose another free API port; update Postman base_url |
| Database authentication error | Reuse the master password originally chosen for this QA volume; initialization variables do not reset an existing role |
| Browser/Postman connection refused | Keep start.py running; verify host/port and startup log |
| 401 | Check which API account/token is being used, expiry and local variable shadowing |
| 403 | Check current role/scopes; expected for standard administrative requests |
| 409 / 422 | Compare with the negative case's expected result before treating as failure |

Do not infer PASS from a written instruction. If a case cannot be performed safely or a dependency failed, record **BLOCKED**, its non-secret reason and the revision. The following cases are generated from the single versioned catalogue; do not edit their IDs/names independently.

### 🔐 **Concrete disposable QA credentials and own-password changes**

These are **public suggestions for a disposable local QA installation only**, never production defaults, automatic account creation or existing private credentials. Enter them yourself in terminal/UI prompts. The database/master are both suggested as **ouroboros_qa**; API users are separate accounts even though they use this same isolated database.

| Account / purpose | Suggested username | Suggested password (enter locally) |
| --- | --- | --- |
| PostgreSQL QA database / master | ouroboros_qa | OuroborosQA-Database-2026! |
| First API administrator | admin | AdminPassword-2026! |
| New API standard account (omit role when creating) | default | DefaultPassword-2026! |
| Administrator after own-password change | admin | AdminPassword-Updated-2026! |
| Standard after own-password change | default | DefaultPassword-Updated-2026! |

The main URLs are **http://localhost:6969/docs**, API port **6969**, PostgreSQL host **6669**, internal **5432**. Automated tests still choose random credentials and free ports. Never insert these examples into .app.config, source defaults, the initialization code or the versioned Postman JSON. These explicitly requested public examples are an exception to documentation's usual credential placeholders; real credentials remain prohibited everywhere versioned.

After all role cases, use the **Own password changes** folder (40–60). Put admin_username/admin_password and standard_username/standard_password in your private environment using the examples above. Set admin_new_password and standard_new_password there too. Keep all captured password_*_token variables in collection scope, never shadowed by empty environment values. Run 40–57 in order; 42 deliberately uses the different administrator password as incorrect confirmation for default. If you chose different local passwords, ensure that incorrect confirmation is actually different.

**PUT /users/me/password** uses the authenticated account, with **no id/username** in its JSON. For default's example enter current_password=DefaultPassword-2026! and new_password=DefaultPassword-Updated-2026! locally. For admin use AdminPassword-2026! and AdminPassword-Updated-2026!. Both profiles return **204 with no body**; incorrect current or unchanged new password gives **400**, invalid/stale authentication **401**, invalid JSON/types/extra identity fields **422**. The whole body is omitted from DEBUG logs, not merely redacted. Find the exact **API password changed** INFO event after a successful commit, with user_id and the request's interaction ID.

After success every earlier token of that account is invalid, including the changing token. The old password no longer logs in. Other users' tokens continue working and the global signing key stays unchanged. **Swagger: Authorize → Logout → Close → Authorize** with the new API password before continuing. A response's X-Interaction-ID changes for each request and is distinct from a public user/record ID.

For the optional manual race set standard_next_password_a=DefaultPassword-RaceA-2026! and standard_next_password_b=DefaultPassword-RaceB-2026! locally. Clear both password_race_*_status captures, send 58/59 concurrently with the SAME pre-race token/current password, then run 60. Exactly one status must be 204 and the other 401; login with the winning candidate afterward. Sequential clicks verify stale-token rejection but do not prove concurrency. The automated mapped case sends real simultaneous HTTP requests. None of these values are filled in the versioned collection.

### 🔀 **Alternative ports only when the defaults are occupied**

If 6969 or 6669 is occupied, do **not** stop that service. In your fresh QA configuration choose free alternatives, e.g. API **6971** and database host **6671**, retain container **5432**, and set Postman base_url=http://localhost:6971. Open http://localhost:6971/docs instead. Keep the unique QA project/volume/workspace identity. This is a troubleshooting alternative, not the main path and not a reason to modify the normal installation. Automated checks always use available ports; the optional standard-port case is separately SKIP when occupied.

## 🧾 Audit, UTC dates and filtered bulk operations

See [the phase contract guide](AUDIT_DATETIME_BULK.md) for migrations 007–008, exact columns, central audit transaction guarantees and outage/crash gaps, versioned error envelopes, UTC/source/display timezone rules, immutable creation dates, and administrator previews/confirmed filtered mutations. The current catalogue has 77 route forms plus two read-only audit routes. Supervisor has individual CRUD and audit reads; standard has neither; administrator alone bulk mutates. Historical creation dates/context stay NULL. No automatic audit retention or durable replay is provided.

For manual QA use owned disposable storage and fresh private accounts. Inspect Swagger controls, complete a GET-to-PUT round trip with original display, preview a filtered change, confirm it explicitly only in disposable storage, and query its X-Interaction-ID in api_audit_logs. Verify standardized codes/header/log/audit correspondence, whole token/password body omissions and restricted audit reads. Record actual UI/Postman JavaScript evidence separately. Never enable destructive examples against normal data.

## 🪜 Classification tiers and complete test CRUD

Migrations009–010 add independent classification tier positions and complete integer-ID test CRUD with shared creation dates, UTC presentation, strict filters and confirmed administrator bulk operations. See [the authoritative contracts](TIERS_AND_TEST_CRUD.md) for the one-time inspected backfill, atomic append/insert/move/delete behavior, bulk tier exception, scope matrix and restart instructions. Never reseed or replace the existing nine normal classifications. Destructive QA remains isolated; review measurements and findings are documented separately.

## Atomic array creation

POST on the eleven catalogue resources and /test accepts one object or an ordered atomic array (default maximum 300). Single responses retain their full record shape; arrays return created_count/items with full final records, independently of GET pagination and administrator bulk PUT/DELETE. See [request, validation, configuration, audit and restart contracts](BATCH_CREATION.md).
