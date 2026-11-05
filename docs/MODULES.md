# Four-module container runtime

This guide supersedes the former host-venv application startup instructions. Business contracts, account permissions, migrations and existing data are unchanged.

## Layout and configuration

| Module | Runtime | Private/local configuration | Versioned example |
| --- | --- | --- | --- |
| Database | Existing `postgres` service, PostgreSQL 17.11 | `database/config.json` | `database/config.example.json` |
| Base/API | `api/`, Python 3.12, FastAPI | `api/config.json` | `api/config.example.json` |
| Frontend | Existing `frontend/`, `frontend/` Nginx image | `frontend/config.json` | `frontend/config.example.json` |
| Assistance | `assistance/`, Python 3.12, faster-whisper and existing GPT-5.4 provider | `assistance/config.json` | `assistance/config.example.json` |

`start.py` delegates to the standard-library-only `orchestration.py`. `config.json` holds the Compose project, existing public address/port, startup deadline, configurable internal API/assistance/database addresses ; `config.example.json` documents its shape. The approved defaults remain HTTP 6969 and loopback PostgreSQL 6669. No assistance or separate API port is published in the four-service mode.

There are exactly five deployment configuration sources: root `config.json`, plus one `config.json` in each module. Each has a sanitized `config.example.json`. Startup initializes only missing canonical files from their corresponding examples; it never reads retired dot-config files or the removed modules/ package. Existing canonical files are never overwritten by initialization.

Root configuration owns Compose identity/workspace, public HTTP binding, startup deadlines and existing internal service addresses. `database/config.json` is the single source for selected PostgreSQL database/master, original published port and database startup timeout. API receives those needed database settings separately; `api/config.json` owns connection/query budgets, authentication, browser origin, logging, timezones and business/API limits. Interactive changes to database/master selection persist only in the database file. The container substitutes the internal connection address (`postgres:5432`); host ports are not used between containers. Changing preferences never rotates roles/passwords in an existing volume.

Assistance configuration owns transcription model/device/compute type, languages, native-window size, audio/text budgets, recording duration, concurrency and timeouts. The `form_assistant` block owns the existing provider processing budgets; its model must remain exactly `gpt-5.4`. Defaults preserve the previous prompts, model and inference parameters. The existing host cache location is owned only by `assistance/config.json` under transcription.cache_directory; relative paths resolve from the identified repository root. Its physical files were preserved, and the assistance process still sees the bind mount as `/models`.

The public frontend JSON controls both names, greetings, image paths and independent color groups. Angular loads `/frontend/runtime-config.json` before bootstrap. The frontend entrypoint validates this JSON and generates external `/frontend/assistant-theme.css`, preserving strict CSP. Edit `frontend/config.json`, then restart the frontend through `python start.py`; no Angular rebuild is needed for those presentation changes. Images are mounted from `frontend/public/images`. Public configuration accepts only presentation keys and same-origin `/frontend/` image paths, never credentials or service addresses. Node builds Angular and runs a short CSS-generation command at container startup; Nginx is the serving process.

## Startup and credentials

From `C:\Dev\Ouroboros` with Docker Desktop running in Linux-container mode:

```powershell
python start.py
```

Any installed compatible launcher Python can run this command; the application and native speech dependencies run in Python 3.12 images. Existing `.venv` and `.venv-speech` remain intact. `start-speech.cmd` is only a compatibility wrapper around the same container launcher.

The launcher validates Compose, uses Docker build caching, verifies the existing infrastructure ownership receipt, starts/reuses PostgreSQL, then runs an interactive bootstrap inside the API image. Enter the existing master credentials yourself. This bootstrap authenticates before checking exact migration checksums and recovering API administration through the existing flow. Credentials are never passed in process arguments or environment variables. The original protected `.secrets/postgres_password` remains the runtime secret; if the authenticated password and stored runtime secret differ, startup stops for explicit reconciliation rather than overwriting a secret or changing a role.

API and frontend readiness are required. Assistance is started and checked separately: its failure is reported but does not block the catalogue. No migration is added or rewritten by this modularization. No `down --volumes`, data reset, normal seed, automatic alternate port or unknown-process termination is performed.

`python start.py --check` validates the five canonical files and Compose without starting services or authenticating to PostgreSQL. `--build-only` builds the application images without database access. `--api-only` uses the same API image directly on the existing public port, without starting frontend or assistance. Use it when that port is free; stop an existing owned listener explicitly before changing modes. The launcher never terminates it automatically. In direct mode `/docs`, `/health`, bearer tokens and the existing API paths remain available; no frontend assets are required.

Compose services remain running after the launcher exits. Re-running the same command reloads application services/configuration while reusing persistent data/cache and cached build layers. PostgreSQL is reused unless its own container configuration changes. An unchanged Docker build does not rerun Angular compilation. Container logs are available through the owning project's Docker Desktop; API application logs remain under `logs/`. Bootstrap and API have separate execution logs. Do not print Compose environment/secret inspection output in reports.

## Communication and authority

```mermaid
flowchart LR
    Browser -->|existing public port| Frontend[Frontend: Nginx and Angular]
    Frontend -->|existing paths /docs /browser APIs| API[Base/API: current account, CSRF, audit]
    API -->|database network| DB[PostgreSQL: existing persistent volume]
    API -->|signed body-bound delegation| Assistance[Assistance: GPT-5.4 and faster-whisper]
    Assistance --> Cache[Existing host model cache]
    Assistance --> OpenAI[Existing Responses API]
```

There are exactly four production services. The database network is internal and shared only by API/PostgreSQL. PostgreSQL also attaches alone to a separate `database_host` bridge so Docker can retain the original loopback port 6669; an internal-only attachment suppresses effective port publication. No other module joins that host-access bridge. The assistance network contains only API/assistance; the frontend network contains only frontend/API. Assistance has no PostgreSQL network attachment, driver requirement, database password, JWT signing secret or administrative credentials. Its root filesystem is read-only, with ephemeral `/tmp` and a persistent model-cache mount.

Frontend proxying preserves Host, cookies, Origin and CSRF headers. Client-address forwarding is trusted only when the immediate source matches the configured frontend service's resolved address; arbitrary browser forwarding headers are not trusted. Protected page navigation uses the existing account/role rule through a private Nginx auth subrequest. HTTPS installations must retain their approved HTTPS origin/termination; this stage adds no TLS endpoint or new published port.

Every assistance call first passes the existing API account, current-role and CSRF/bearer checks. The API issues an HMAC delegation bound to the operation, body digest, authorized subject, lifetime and nonce. Assistance verifies it and rejects replay; user-supplied IDs/roles are never sufficient. The signing key is a separate protected `.secrets/assistance_service_key`, unrelated to user JWTs. The provider file `assistance/.env` is mounted only into assistance for `OPENAI_API_KEY`, never copied into images or public assets. The existing `.secrets` directory remains API-private. Runtime processes consume these protected files without bypassing the interactive normal migration/bootstrap authentication.

Audio, transcripts and conversation bodies remain omitted from API execution logs and audit bodies. Assistance has no business-write endpoints or database audit credentials; business operations still use the existing API. Audio remains in bounded memory, is cleared after requests and is never written to persistent storage.

This design follows the separation and per-request authorization guidance in the [OWASP REST Security](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html), [Authorization](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html) and [Logging](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html) cheat sheets; it is not a blanket ASVS compliance claim. Internal HTTP is confined to local Compose bridges, not a distributed deployment security design.

## Dependencies and persistent storage

- Base/API installs `api/requirements.txt`; it does not install or execute faster-whisper/CTranslate2/PyAV models.
- Assistance installs `assistance/requirements.txt`; shared Pydantic form contracts are reused without account/database implementations.
- Frontend uses `npm ci` with the existing lockfile in a Node build stage and serves static assets through Nginx.
- PostgreSQL retains the exact existing Compose identity and `<project>_postgres_data` volume. Model files reuse the configured existing host directory; restarts do not redownload a cached model.
- Configuration, original protected secrets, provider `assistance/.env`, frontend images and API logs remain external to images. `.dockerignore` excludes private files, local environments, node_modules, build caches and QA scratch files.

API browser sessions and assistance replay/capacity state remain process-local, as before. Separate service sizing is possible; multiple API replicas/shared sessions or distributed replay coordination are future work, not implemented here.

## Verification

Use built images with `python scripts/verify_modules.py` from a declared QA environment. It creates a randomly named owned project with PostgreSQL in tmpfs, disposable accounts/secrets, no published ports, and removes only its own containers/network afterward. It never queries the normal database or deletes any named volume. `--audio <disposable.wav>` also exercises real transcription; `--live-assistant` makes one live GPT-5.4 request using the configured provider file mounted only into disposable assistance (with normal provider usage cost); `--publish` optionally uses only approved port 6969 when free. Never supply personal recordings.

See [the module QA record](MODULES_QA.md) for actual executed checks and remaining manual/normal-installation steps. Unit checks and internal HTTP checks do not establish browser rendering, physical microphone behavior or normal-database authentication.

## Source layout and retired configuration migration

```text
Ouroboros/
  start.py
  orchestration.py
  config.json / config.example.json
  compose.yaml
  frontend/
    config.json / config.example.json
    Dockerfile, nginx.conf, entrypoint.sh
    src/, assets/, public/, scripts/, package.json
  api/
    config.json / config.example.json
    Dockerfile, requirements.txt, runtime.py, assistance_client.py
    app/, scripts/
  assistance/
    config.json / config.example.json
    .env
    Dockerfile, requirements.txt, main.py
    transcription.py, form_assistant.py, scripts/
  database/
    config.json / config.example.json
    sql/migrations/, sql/queries/
  shared/
    paths.py, configfiles.py, service_auth.py
    form_contracts.py, speech.py, assistance_settings.py
    schemas/, error catalogue, UTC/audit/privacy/text-policy contracts
  scripts/, tests/, qa/, docs/, postman/
```

`shared/` contains real cross-module contracts/utilities, not duplicate runtime implementations. Fixed versioned schema/text-policy resources remain code assets, not competing installation profiles. Python service imports use api.*, assistance.* and shared.*; there are no root app/ or modules/ compatibility packages. Module-specific diagnostic/build utilities live in their module's scripts/; common QA/review orchestration remains in root scripts/. Root requirements-dev/review describe cross-module verification tools.

Private deployment values were migrated once from `.orchestration.json`, `modules/base/config/.config.json`, `modules/database/.config.json`, `modules/assistance/.config.json` and `modules/frontend/.config.json`. Unused `.app.config`, `.ai.config` and `modules/base/.config.json` variants were retired as well. Their original private JSON files are preserved only in the protected `.secrets/layout-config-before-standardization.zip` rollback archive; no startup path reads it. The provider `.env` was moved to assistance/.env without printing, parsing or duplicating its token. All applied SQL files moved by filesystem rename; exact SHA-256 bytes were compared before/after. Existing named volumes, model-cache files, protected shared secrets and runtime logs were not relocated or reset.
