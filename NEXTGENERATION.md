# 🧬 Developer README — Next Generation

This document records the rules, conventions, and working practices adopted by the developers of **Ouroboros**. It is intended to help the next generation of contributors understand those decisions, preserve consistency, and continue the project with a shared way of working.

Keep these guidelines up to date as the project evolves. When an established rule changes, update this document so future developers can follow the current approach.

The main **README.md** introduces the project. **NEXTGENERATION.md** explains how developers work on it. 🧑‍💻✨

## 📍 Project status

Ouroboros is an independent entertainment-consumption catalogue derived from Foundation. Migrations005–010 provide eleven catalogue tables, supervisor roles, central auditing, UTC/source context, independent classification positions and full integer-ID test CRUD. Scalar/date filters, paging, whitelisted ordering, administrator bulk preview/confirmation and transactional evidence are implemented. See [the model](docs/CATALOGUE.md), [API contracts](docs/CATALOGUE_API.md) and [tier/test rules](docs/TIERS_AND_TEST_CRUD.md). The Portuguese Angular 22 frontend provides home/login, shared selection pages and platform/tag/work-classification create/edit/consultation with confirmed individual deletion on the same FastAPI origin. Advanced search and AI remain future work.

Configuration, logging, Docker Compose PostgreSQL preparation, credential prompts, and the initial test-table migration are implemented. Python 3.10 or newer and the declared Psycopg driver are required. Run `python start.py` from the configured virtual environment. FastAPI health, local OAuth2 password-grant tokens, and scope-protected test endpoints are implemented. Startup now serves the API until Ctrl+C; PostgreSQL remains running afterward.

## 📂 Workspace organization

Store each project in its own folder, for example:

- `C:\Dev\Foundation`
- `C:\Dev\Ouroboros`

Each project has its own Git repository and hidden `.git` directory. Do not initialize a shared repository in `C:\Dev`.

In VS Code, select **File → Open Folder**, open the project folder, and use **Terminal → New Terminal**. Commands below use PowerShell.

```powershell
cd C:\Dev\Ouroboros
```

## 👤 Git identity and authentication

Commit identity records who authored a change. GitHub authentication controls access to the remote repository. They are separate settings.

Configure your own identity once per Windows user:

```powershell
git config --global user.name "YOUR_NAME"
git config --global user.email "YOUR_VERIFIED_EMAIL"
```

The project owner's established identity is **NatachaLlona**. Other contributors must use their own identity.

Check your configuration:

```powershell
git config --global user.name
git config --global user.email
```

Use Git Credential Manager for GitHub authentication. Never put passwords or tokens in this guide, commit messages, or remote URLs.

## 🔎 Check whether Git is initialized

```powershell
git status
git rev-parse --show-toplevel
```

- **`On branch main`** means Git is initialized.
- **`fatal: not a git repository`** means the current folder is outside a repository.
- The repository root should match the intended project folder. If it points to a parent folder, investigate before proceeding.

For a new project only, initialize Git from its root:

```powershell
git init -b main
```

## 🌱 First commit for a new project

Create the README and `.gitignore` before staging files.

```powershell
git add --all
git status
git diff --cached
git commit -m "chore(init): initialize Ouroboros with README and gitignore"
```

**Our staging convention:** use `git add --all` to stage new files, modifications, and deletions throughout the repository, while respecting ignore rules for untracked files. Review the staged changes before committing.

> 🔐 Ignore rules do not stop Git from tracking a file that was already committed. Keep local configuration, credentials, logs, caches, and virtual environments out of version control. Track a sanitized configuration example when needed.

## ☁️ Publish a new repository

Create the repository at [GitHub → New repository](https://github.com/new). For this project, use **Ouroboros** under **NatachaLlona**, with **Private** visibility.

When publishing an existing local repository, create an empty remote: do not generate another README, `.gitignore`, or license in the GitHub form.

Copy the HTTPS URL from GitHub, then run:

```powershell
git remote add origin https://github.com/NatachaLlona/Ouroboros.git
git push -u origin main
```

Add `origin` once per repository. If it already exists, inspect it before changing anything:

```powershell
git remote -v
```

## 🔄 Everyday workflow

Start with a clean working tree and receive remote changes:

```powershell
git status
git pull --ff-only
```

After completing and verifying a coherent change:

```powershell
git add --all
git status
git diff --cached
git commit -m "docs(init): translate README to English"
git push
```

Replace the example message with an accurate description of the change.

- **Commit** saves a local history entry.
- **Push** sends local commits to GitHub.
- **Pull** receives and integrates remote changes.

If `git pull --ff-only` reports divergent histories, inspect the situation and choose an intentional merge or rebase. Do not use force push as a routine workaround.

## 🏷️ Commit message conventions

Use [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/):

```text
type(scope): short description in English
```

### 🧩 Types

| Type | Purpose |
| --- | --- |
| `chore` | Maintenance and project preparation |
| `docs` | Documentation changes |
| `feat` | New functionality |
| `fix` | Bug fixes |
| `refactor` | Code restructuring without a behavior change |
| `test` | Test additions or updates |
| `build` | Build system and dependency changes |
| `ci` | Continuous integration and delivery automation |

### 🎯 Scopes

| Scope | Area |
| --- | --- |
| `init` | Initial project preparation |
| `api` | Endpoints and API behavior |
| `database` | Database access, schema, and migrations |
| `config` | Application configuration |
| `logging` | Logging behavior and formatting |
| `auth` | Authentication and authorization |
| `docker` | Container configuration |

### 📏 Writing rules

- Use lowercase types and scopes.
- Write a concise English description without a final period.
- Start with an imperative verb, such as **add**, **fix**, **update**, **configure**, or **translate**.
- Describe the actual change; avoid vague messages such as `updates`.
- Use `init` during initial preparation, then select the relevant area.
- Keep each commit understandable as one coherent change.

```text
chore(init): initialize Ouroboros with README and gitignore
docs(init): translate README to English
docs(init): add Next Generation developer guide
feat(api): add health endpoint
feat(database): create test table
feat(auth): add OAuth2 token endpoint
chore(docker): configure PostgreSQL container
```

The application-related examples illustrate the naming convention; they do not imply those features are already implemented.

## 🧰 Quick reference

| Goal | Command |
| --- | --- |
| Check current changes | `git status` |
| Check repository root | `git rev-parse --show-toplevel` |
| Stage all changes | `git add --all` |
| Review staged changes | `git diff --cached` |
| Inspect remote URLs | `git remote -v` |
| View recent history | `git log --oneline -10` |
| Receive remote changes | `git pull --ff-only` |
| Send commits | `git push` |

## Configuration and startup

- `start.py` prepares a basic console logger before loading configuration, initializes the configured logger, and coordinates Docker checks, credential prompts, PostgreSQL health, authenticated TCP connection, migrations, and completion. Record successes only after verification; all general events use `application`. The configured logger records failures in both console and file once initialized. Failures return a nonzero exit code. Bootstrap errors omit raw configuration and exception details that could expose secrets.
- Resolve paths from the project root, not the current working directory.
- `.app.config` is local UTF-8 JSON and is ignored. If absent, copy `.app.config.example` without overwriting an existing local file. The sanitized example is explicitly allowed by `.gitignore` and must remain versioned.
- `host`: a string; missing, null, empty, or whitespace-only values normalize to `localhost`.
- `port`: an integer from 1 to 65535; booleans and numeric strings are invalid. The example uses `6969`.
- `database.name` and `database.user`: strings prompted when empty and saved in local JSON. Names contain 1-63 lowercase letters, digits, or underscores and cannot start with a digit. The user is the database master, not an API account. Never store passwords or tokens in JSON.
- `logging`: an object with `level`, `format`, and `directory`. Configured levels are only `INFO` and `DEBUG`; local and example files select `DEBUG`. Events still support all five standard severities. Invalid configuration must fail explicitly.

## 🪵 **Logging and concurrency**

Use `ApplicationLogger` and `log_event` for internal stages. Request metadata lives in an immutable `RequestContext` held by ContextVar; AnyIO copies it into synchronous workers. The middleware binds the logger/context, generates the ID once, and resets both in nested `finally` blocks even after errors/cancellation. Components do not manually propagate interaction IDs, methods, paths, or categories. Outside a request the category is `application`, the interaction ID is empty, and HTTP fields are empty. Explicit event IDs no longer override this policy.

The ID uses UTC `YYYYMMDDHHMMSS` plus ten cryptographically random decimal digits, formatted as a 24-character string with leading zeros preserved. Never trust an incoming client ID. Return the generated ID in `X-Interaction-ID` on success and error responses. Random digits reduce collision probability but provide no mathematical guarantee of uniqueness.

The default configurable format is **LEVEL | INTERACTION_ID | DATETIME | CATEGORY | METHOD PATH | COMPONENT | CLASS | SOURCE:LINE | MESSAGE | CONTEXT**. Use `%(level)-8s`, `%(interaction_id)-24s` as the second field, and `%(category)-11s`; widths are minimum widths, never truncate other identifiers, paths, or messages for alignment; application events reserve 24 blank spaces. Supported placeholders include `level`, `interaction_id`, `datetime`, `category`, `method`, `path`, `method_path`, `component`, `class_name`, `source`, `line`, `message`, and `context`. Datetime is timezone-aware, caller source/line is preserved through the helper, and control characters are escaped.

Both local and example config select **DEBUG**. Only configured **INFO** or **DEBUG** is allowed; all five event severities remain supported. INFO includes INFO/WARNING/ERROR/CRITICAL; DEBUG also includes DEBUG. Do not add alternate filter settings. `logging.body_max_chars` is 2048 by default (64-65536) and bounds the Unicode JSON serialization of the sanitized body. When it fits, keep the actual object under `context.body`; when oversized, use a bounded `body_preview` string and `truncated: true`. Do not serialize a fitting body twice. Emit the preview once in DEBUG, recursively redact sensitive keys in objects/lists, mark truncation explicitly, never inspect `/token` or `/users/me/password` bodies, and omit binary/upload/non-JSON content. A separate 1 MiB inspection ceiling omits oversized JSON previews without rejecting or changing the request body. Never log Authorization, query strings, secrets, password hashes, or token values. Key-based redaction does not detect secrets hidden under arbitrary free-text values: callers must not send them to logs.

INFO events cover request received, successful main operation, final status/duration, startup, and shutdown. DEBUG covers component entry, validation start/result, bounded body previews, connection acquisition, and query completion without SQL parameters. Expected validation/authentication rejections use WARNING, not internal-failure ERROR. Unexpected errors log safe exception categories and source/line/function frames, without raw exception messages, SQL values, or stack source snippets. HTTP errors remain generic.

One process execution writes UTF-8 console/file events into `application_YYYY-MM-DD_HHMMSS_random.log`, with daily rollover, append, and prior logs retained. Logger-owned handlers are not attached globally. Uvicorn access logs remain disabled. Older daily-only files are preserved.

Run **one Uvicorn worker**. Keep real blocking Psycopg/hash operations in FastAPI's synchronous handlers/dependencies, which execute through AnyIO's thread pool. Set the shared pool limit to 40 slots during lifespan and restore it on shutdown. Async middleware offloads blocking file logging and JSON preview work. Do not create a thread per request. The database provider gives each operation its own transaction/connection, bounded by `database.max_connections` (default 8, range 1-32). Capacity waits are bounded by `database.connection_acquire_timeout` (default 5 seconds, range 1-300); exhaustion produces safe 503. Always release capacity in `finally`; never share a live cursor between requests.

### 🎨 **Log presentation and console colors**

Keep literal UTF-8 accents and emoji in both destinations: `Ouroboros está vivo! 🐍💻`. Context uses `ensure_ascii=False`. Maintain recursive redaction before serialization, bounded previews, explicit truncation, and escaping of newlines, controls, Unicode line separators, and invalid lone surrogates. One event must remain one physical line. A fitting body is an object in JSON context; only a truncated document falls back to text. Never weaken `/token` or Authorization exclusions.

Console and file use separate formatters. Console color is added **after** plain formatting and only around the level label, preserving visible column widths and leaving the shared LogRecord unchanged. DEBUG is gray, INFO green, WARNING yellow, ERROR red, CRITICAL bold red. Require `isatty()` and terminal compatibility, respect the presence of `NO_COLOR`, reject `TERM=dumb`, and disable colors on redirection. On Windows, use native `GetConsoleMode`/`SetConsoleMode` for VT processing; fail closed if unsupported. The default console stream is configured for UTF-8. No new dependency is needed. File output never receives ANSI sequences. Test redirected Unicode, mock compatible-console color behavior, and separately report whether the real VS Code terminal was visually verified.

**Example** (illustrative source positions):

```text
INFO     |                          | 2026-10-18T11:33:11.048+01:00 | application |  | ouroboros | - | start.py:30 | Ouroboros preparation completed | {}
DEBUG    | 202610181133110482759163 | 2026-10-18T11:33:11.048+01:00 | request     | POST /test | ouroboros | - | app/main.py:45 | Request JSON body received | {"body": {"value": "Ouroboros está vivo! 🐍💻"}, "truncated": false}
```

## Local verification

Run `python -m unittest discover -s tests -v` from the project root. Tests isolate their configuration and logs in temporary directories. They cover configuration creation and preservation, host defaults, invalid ports and levels, startup success and failure, execution from another working directory, application categories with blank IDs, repeated request IDs, source location, timezone, severity filtering, console/file output, daily rollover and append, handler duplication, configurable formatting, and control-character escaping.

## PostgreSQL development conventions

### Responsibilities and dependencies

- `app/config.py`: load and validate JSON, supply backward-compatible defaults for new database settings, and atomically save non-secret choices without dropping other fields.
- `app/credentials.py`: interactive user selection, masked password input, and restricted persistent secret creation. Ctrl+C, Escape, or EOF cancels safely. Passwords must never enter command arguments, JSON, logs, or exception messages.
- `app/database.py`: safe subprocess invocation, Docker checks, Compose startup, and authenticated database connections. Use Psycopg 3 from `requirements.txt`; install with `python -m pip install -r requirements.txt` in the virtual environment.
- `app/database_test.py`: parameterized insert/read operations for `public.test`; transaction ownership belongs to the caller.
- `app/migrate.py`: transactional migrations, advisory lock for concurrent startup, applied-version tracking, SHA-256 checksums, and schema compatibility checks. Never edit an applied SQL migration; add a new numbered file.
- `sql/migrations/001_create_test.sql`: idempotent table creation, `id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY`, `value TEXT NOT NULL`, and no extra value index. No artificial text length limit or demonstration inserts.
- `compose.yaml`: infrastructure only; fixed `postgres:17.11-bookworm`, named volume, loopback-only published port, file secret, and healthcheck. Never use `latest` or automatically remove existing volumes.
- `start.py`: orchestration only. Check CLI, Compose, and Engine before credential prompts; start/reuse PostgreSQL with a bounded wait, verify credentials, migrate, then serve the configured FastAPI application. On graceful shutdown, release API connections and in-memory credentials while leaving PostgreSQL running.

### Database configuration

| Field | Default | Validation |
| --- | --- | --- |
| `database.name` | empty | Prompt when blank; validated database name |
| `database.user` | empty | Offer to reuse an existing master user or prompt for another |
| `database.port` | 6669 | Integer 1-65535, different from application port |
| `database.startup_timeout` | 120 | Integer 1-3600 seconds, including initial image download |
| `database.connect_timeout` | 10 | Integer 1-300 seconds |
| `database.statement_timeout` | 30 | Integer 1-3600 seconds; applies to migration statements and lock waits |

The application host/port are not PostgreSQL connection settings. Connect to PostgreSQL at `127.0.0.1` using its separately configured port. Commands always pass argument lists with `shell=False`; never interpolate credentials or identifiers into SQL. Use parameterized queries for values and Psycopg SQL composition for any future dynamic identifiers.

### Persistence and secret lifecycle

The normal Ouroboros Compose project is `ouroboros`; its named volume is `ouroboros_postgres_data`. PostgreSQL initialization variables only apply to an empty volume. Retain the original container's POSTGRES_DB and POSTGRES_USER environment values during recreation, while allowing independent runtime selection of another database or existing master role. Authenticate against the postgres maintenance database and create a missing target database with autocommit and psycopg.sql.Identifier only when permitted. Do not alter roles, passwords, grants, or earlier databases. A retained initialized volume is always reused; initialization variables never substitute for runtime provisioning.

Request a password every execution. `.secrets/postgres_password` is a plaintext initialization secret with restricted filesystem access, not encrypted storage. Restrict the directory before writing: Windows protected DACL for the current user only; POSIX directory 0700 and file 0600. Fail if protection cannot be applied. Compose mounts this file for `POSTGRES_PASSWORD_FILE`, so keep it available for container startup and recreation. Existing secret contents are preserved on later runs, including failed authentication attempts. Do not rotate PostgreSQL master passwords through application startup; self-service API password replacement is separate.

Keep `.secrets/`, `.app.config`, and logs ignored; verify the example configuration is not ignored. Do not forward inherited `PGPASSWORD` or `POSTGRES_PASSWORD` to Docker commands, display raw Docker/driver errors, or log connection strings. Docker and database administrators are trusted. Remove a secret manually only after its associated container is deliberately retired and its volume lifecycle is understood.

For safe stop/start commands, load the non-secret Compose environment from `.app.config` as documented in README. Use `docker compose -p ouroboros stop postgres` and `docker compose -p ouroboros start --wait postgres`. `down` preserves data unless explicitly given destructive volume flags; never use `down --volumes` for normal project shutdown. Use `python start.py` for credential validation and migrations.

### Verification and environment limits

Run the existing unit suite after changes. `FOUNDATION_RUN_INTEGRATION=1` enables a real PostgreSQL test with a UUID project, isolated volume, temporary secret, random credentials, and separate port. Only resources created by that test are cleaned up, after stop/start persistence is checked. Never delete existing project volumes to make tests pass. Test records must never enter the normal database.

Verified on Windows with Python 3.15, Psycopg 3.3.6, Docker CLI 29.8.2, and Compose 5.6.0: unit checks, protected secret ACL, real first initialization, repeated migrations, identity generation, 50,000-character round trip, stop/start persistence, and rejection of invalid credentials. Missing Docker/Engine paths are also covered by isolated failure tests. Automated tests never choose or replace the owner's normal database or API credentials. Masking, Backspace, and cancellation are tested with simulated key input; final terminal interaction remains a manual check.

Official references: [PostgreSQL image initialization and file secrets](https://hub.docker.com/_/postgres), [Compose startup waiting](https://docs.docker.com/reference/cli/docker/compose/up/), and [Psycopg installation](https://www.psycopg.org/psycopg3/docs/basic/install.html).

## API development conventions

### Structure and startup

`app/main.py` provides an application factory and registers health, token, test, and users routers. Keep strict schemas in `app/schemas/`, shared collection pagination in `app/pagination.py`, authorization in `app/auth.py`, administrator recovery in `app/api_credentials.py`, account persistence in `app/api_users.py`, test data access in `app/database_test.py`, and fixed queries in `sql/queries/`. Values must always use driver parameters; never concatenate filters into SQL.

`start.py` independently confirms database name and master user, requests the master password, prepares PostgreSQL and the selected database, runs migrations, imports any legacy API account, explicitly recovers the first administrator if necessary, loads the protected signing key, and starts Uvicorn on normalized host/port. With an active administrator, startup offers no unrestricted terminal enrollment. Do not add reload or multiple workers. Each request gets short-lived connections with caller-owned transactions; connection contexts commit/roll back and close. Lifespan clears provider password/signing-key references; Python cannot guarantee secure erasure of immutable strings. Ctrl+C stops the API, not PostgreSQL.

Install pinned runtime and verification dependencies with `python -m pip install -r requirements.txt` in `.venv`. Tests use FastAPI TestClient and HTTPX. Current Starlette emits an HTTPX deprecation notice; tests still pass. A future TestClient dependency update can migrate to its recommended HTTPX2 client.

### 👤 **Database API users and token validation**

`sql/migrations/002_create_api_users.sql` introduces `public.api_users`: identity BIGINT primary key, unique non-null text username, Argon2id password hash, automatic TIMESTAMPTZ created_at, non-null boolean is_active default true, and non-null TEXT[] scopes. Migration **003_add_api_user_role.sql** adds non-null text role default `standard`, with a CHECK accepting only `standard` and `administrator`. Never edit applied migrations. No additional role/permission tables are introduced. API users are not PostgreSQL master roles.

Configuration `auth` retains only issuer, audience, and token_ttl_seconds; `api_users` retains only last_api_username. The preference never proves existence or grants access. Continue validating token lifetime as integer 1-86400 and using the protected persistent signing key. Runtime authentication must always query PostgreSQL, not legacy fields or a cached account.

Startup accepts legacy auth.username/password_hash only for migration. `migrate_legacy_user` imports the exact validated Argon2id hash and both current test scopes, commits first, and only then removes both legacy fields and atomically writes sanitized configuration. Reuse an identical existing account; fail on differing hash/scopes/active state without overwriting anything. Block configuration saves containing the legacy hash, so no temporary/backup configuration copy contains it. A crash after database commit is handled by idempotent reimport. Do not print/log hashes or passwords.

After migrations/import, query for an **active administrator**. A fresh database's first terminal account is administrator. If existing accounts have no active administrator, require explicit `promote` plus an existing active username, or `create` plus a unique username/masked password, after successful master database authentication. Never select the first ID automatically; existing users remain standard until explicit choice. Once an active administrator exists, startup requires no API password or enrollment prompt. All subsequent enrollment/role changes use administrator-only APIs. Preserve hashes, IDs, scopes and other fields during promotion; last_api_username is only a preference.

`POST /token` accepts URL-encoded credentials and optional scopes, checks database Argon2id/is_active, and returns a generic 401 for invalid/inactive credentials. Keep immutable numeric-string sub, version 2, selected-database binding, iat/exp/iss/aud/scopes, HS256 and full claim validation. Reload current role/state on every request. Standard token permissions intersect current stored test scopes; revoked write access yields 403 and missing/inactive users yield 401. Standard users cannot request administrative scopes. Administrator token issuance may advertise all currently registered OAuth2 scopes, but current administrator authorization must never depend on that static list. Token responses retain no-store headers and configured expires_in.

The password grant remains for the controlled local client. There are no refresh tokens, public signup or deletion APIs. Password replacement uses authenticated self-service or the administrator-only reset described below. Retain the version-2 immutable-subject/database-bound token contract and require the current credential_version claim.

### 🔌 **Database selection and definitive ports**

API/Swagger default to **6969** (`http://localhost:6969/docs`); PostgreSQL is published at **127.0.0.1:6669:5432**, retaining container port 5432. Keep both host ports configurable and distinct; update local/example JSON, Compose fallback, Postman base_url, README examples and embedded collection together. Port changes may recreate the container but must retain its existing named volume.

Prompt order is database confirmation/new name, independent master-user confirmation/new name, then masked master password. Choosing another database never automatically changes the username. Existing master roles are authenticated, not created or modified. Connect to postgres for database existence checks; use an autocommit connection and Identifier composition for CREATE DATABASE. Explain missing CREATEDB privileges clearly. Never delete an existing database or volume to make selection work.

### 🧪 **Account migration verification**

`tests/test_accounts_integration.py` uses its own UUID Compose project, creates both databases and restricted roles only in that disposable cluster, verifies the exact legacy hash and cleanup of configuration, repeats the import, rejects conflicts without overwrites, authenticates two accounts, tests inactivity and permission reductions, and checks preservation of earlier records/databases. Port checks bind 6969/6669 only when free; if occupied, do not stop the existing service and explicitly skip that fixed-port assertion. Other account checks continue on an ephemeral database port. Unit tests also ensure database/master prompts are independent and no temporary legacy-hash configuration copy is written.

Historically, the Foundation stage passed **45 tests**, including real fixed-port API/Swagger/PostgreSQL checks in isolation. Its existing local account was then imported and its legacy configuration fields removed after successful commit; record count and a SHA-256 data fingerprint matched, prior databases remained present, and the named volume was retained. That evidence belongs to Foundation, not this Ouroboros phase. Postman desktop UI import and physical terminal key interaction remain separate manual verification.

### Endpoint contracts and queries

- `GET /health`: public; execute a real database query and return simple JSON with 200 or 503, without backend exception details.
- `POST /test`: require `test:write`; accept only a required strict string `value`, forbid extra fields and null, preserve whitespace/content, and impose no artificial length limit. Return 201 with the database-generated ID and value.
- `GET /test`: require `test:read` or current administrator; return the shared paginated envelope with configurable scalar ordering, defaulting to ID ascending. Optional `id` is positive and within PostgreSQL BIGINT range. Optional `value` is an unmodified `ILIKE` pattern. Combine filters with AND before counting/pagination. Missing `value` disables that filter; empty `value` matches an empty value. No matches returns 200 with count 0 and empty items.
- SQL for current paginated reads uses `catalogue_page.sql` through `collection_queries.py`, including inherited test/user lists. Values remain parameters and ordering identifiers are whitelisted. The earlier fixed-ID page_test/page_users templates are retained historical query files. Inserts/readback use `insert_test.sql`/`read_test.sql`; `list_test.sql` stays internal. Use `%` for any sequence and `_` for one character. Backslash escapes literal `%`, `_`, and backslash. Do not add wildcards automatically. Encode percent as `%25` and backslash as `%5C` in URLs; Swagger accepts raw patterns.

### Request logging and safe errors

Follow **Logging and concurrency** above for context propagation, numeric IDs, DEBUG previews, redaction, truncation, and cleanup. Validation errors expose field locations/error categories without rejected values. All errors retain X-Interaction-ID. Preserve safe 401/403 challenges, 422 validation errors, 503 backend errors, and generic unexpected 500 responses.

### Verification

The full suite with `FOUNDATION_RUN_INTEGRATION=1` checks actual PostgreSQL-backed endpoint creation/readback, generated IDs, 50,000-character content, case-insensitive exact/prefix/suffix/contains searches, `%`/`_` and escaped wildcards, combined filters, empty/no matches, and SQL injection strings as data. It also checks public health during real database stop/restart, an actual Uvicorn HTTP socket, graceful shutdown, and preservation of database data afterward. Other tests cover malformed/expired/wrong-signature/wrong-issuer/wrong-audience JWTs, scope restrictions, strict input validation, credential/hash/key persistence, OpenAPI scopes, consistent IDs, and secret-free logs.

All integration data remains in UUID-named disposable Compose resources; never write test data to the normal database. Keyboard masking and Ctrl+C in the owner's terminal remain manual verification; automated tests simulate keys and request graceful server shutdown without stopping normal PostgreSQL.

References: [FastAPI OAuth2 and JWT](https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/), [FastAPI scopes](https://fastapi.tiangolo.com/advanced/security/oauth2-scopes/), and [PyJWT validation](https://pyjwt.readthedocs.io/en/latest/usage.html).

## 🧪 **Manual and automated test maintenance**

- **Canonical collection:** `postman/Ouroboros.postman_collection.json`, Postman Collection v2.1, is the only maintained import source. Historical local YAMLs include three List all entries copies (plain, -1, -2) with old array assertions/different order; preserve them and personal settings, do not import alongside JSON or silently synchronize private artifacts. Document replacing an existing JSON import while retaining private environments/custom requests. Never publish credentials from `.postman/`, `.resources/`, YAML metadata or exports.
- **Keep contracts synchronized:** update requests, status assertions, automatic token/ID capture, README examples, expected results, and the complete collapsible JSON block whenever endpoints change. Run `python scripts/sync_postman_readme.py` after editing the collection; a test enforces byte-equivalent embedded JSON.
- **Safe defaults:** `api_username`, `api_password`, `access_token`, and `test_id` are empty in versioned JSON. Set credentials only in a private local environment. Do not shadow the captured collection token/ID with empty environment variables. Never log or version passwords, tokens, hashes, or personal credentials. Review exports before staging.
- **Optional Params:** request 04 (List all entries) keeps a structured URL with `id={{test_id}}` and `value=%Ouroboros%`, both `disabled: true`. Preserve raw percent signs in Params and automatic single URL encoding; do not encode `%25` into the Params value. Verify neither/id/value/both checkbox combinations, keep Bearer authentication, and retain separate filter requests 05-07. Never add GET filters to the insertion POST.
- **Filter contract:** use `Ouroboros está vivo! 🐍💻` consistently in POST and `%Ouroboros%` queries. ID-filter scripts must assert exactly the inserted row and value; value scripts must check every row case-insensitively; combined scripts must check both conditions. Retain automatic token/ID capture and empty versioned credentials.
- **Manual tests:** follow README's numbered 01-08 sequence in Postman Desktop. They operate on the selected database; every POST persists another row. Document interface import separately from schema/request checks; do not claim GUI import or sandbox execution without doing them.
- **Automated tests:** install `requirements-dev.txt`; use isolated temporary files and UUID Docker projects. Never write examples to or clean normal project data. The opt-in suite replays basic and administrative request definitions, exercises a real HTTP server with overlapping requests, and verifies PostgreSQL filters, pagination, roles, persistence, and authentication. This is not execution of Postman's JavaScript sandbox.
- **Logging/concurrency checks:** verify automatic IDs across internal stages, overlap without context mixing, cleanup after success/error/cancellation, INFO/DEBUG filtering, ERROR in both modes, aligned blank application IDs, single-line redacted/truncated previews, and bounded connections. Retain earlier authentication/database coverage.
- **Documentation style:** English, clear headings, emojis, **bold** emphasis, tables, and useful code blocks. Distinguish observed test results from manual steps and unverified UI behavior.
- **Schema provenance:** `tests/schemas/postman-v2.1.schema.json` is the official Postman schema downloaded from https://schema.postman.com/collection/json/v2.1.0/draft-04/collection.json for offline validation.

## 🧭 **Startup safety, project identity, and Swagger maintenance**

### 🛠️ **Diagnostics and cleanup**

`start.py` names each stage and reuses `error_details` for exception category and safe source/line/function frames. Unexpected exceptions must never log raw exception text, source snippets, locals, connection strings, passwords, tokens, or hashes. Application-owned safe ConfigurationError/DatabaseError guidance may be shown; safe diagnostics fall back to the bootstrap logger if the configured logger fails. Never claim data preservation/integrity on generic failure or cancellation paths.

`cleanup_actions` attempts every callback independently, even when cleanup reporting fails. Keep the primary failure; collect resource/type/frame diagnostics separately and return nonzero for any cleanup failure. Close database, authentication, every logger handler, and the bootstrap handler without one failure skipping the next. Logger initialization cleanup must not replace its original exception. Lifespan restores the AnyIO limit and records cleanup failures; `run_api` returns them to the entry point. Normal serving Ctrl+C is informational and returns 0 after successful cleanup; startup cancellation returns 130, and incomplete EOF returns failure. Do not turn normal Ctrl+C into an unexpected error.

### 🧱 **Derived-project isolation**

Foundation retains identity `foundation` and volume `foundation_postgres_data`; never rename, migrate, replace or adopt that volume. Ouroboros uses `ouroboros` and `ouroboros_postgres_data`. The tracked example selects `ouroboros`; another derived workspace must choose its own identity. Local infrastructure.workspace binds configuration to its directory. The middleware-independent startup guard rejects mismatched roots and containers whose Compose working-directory labels do not match. The ignored `.secrets/infrastructure_identity.json` receipt records project/root ownership; a matching receipt is required before reusing a volume without a container. Never silently adopt an unowned existing volume.

Derived projects start from tracked source/templates only, with a unique identity, own available API/database host ports, fresh configuration, fresh secrets, own API users, and their own `<project_name>_postgres_data` volume. Do not copy local `.app.config`, `.secrets`, data volumes, private Postman settings, or runtime artifacts. Preserve blank workspace only for the initial fresh setup; it is bound/saved on startup. Use configured `--project-name` for every Compose operation; no hardcoded fallback to Ouroboros in source or Compose. The README’s AcmeService example is instructional. Ouroboros phase one is implemented separately from Foundation.

### 🔐 **Swagger contract**

Keep the OAuth2 password flow pointing to `/token`, with documented test:read/test:write scopes. `/health` and `/token` remain public; protected endpoints keep Argon2id/database-user, active-state, JWT, current-scope, and 401/403 validation. Prefer Swagger **Authorize**: credentials, scopes, authorize, close, then POST JSON and GET filters. **Try it out on POST /token does not automatically set global authorization.**

The token form uses application/x-www-form-urlencoded. username/password are required. grant_type supports only `password`, supplies that default, and accepts omitted/empty values by using the default; reject `string` and other grants. scope is optional, space-separated, with omitted/empty resolving only to current allowed permissions. client_id/client_secret are unused by this controlled local client and should remain empty. Describe Send empty value: optional omission and empty fields are both tested. Do not embed real credentials in examples or log token bodies.

The previous schema had a grant_type pattern but no default: equivalent HTTP calls with `string` reproduced 422; omitted, empty, and password succeeded. Do not claim this proves the user's exact UI sequence. Browser/desktop automation failed to initialize during this stage, so real Swagger interface testing remains manual. Verify OpenAPI and equivalent form/authorization/POST/GET requests separately from browser evidence. Preserve existing Postman compatibility when grant_type is omitted.

### 🌍 **Documentation and password storage**

Keep English documentation with emojis, **bold** emphasis, tables, and runnable examples. The canonical developer guide is **NEXTGENERATION.md**; a downloaded `(1)` copy never changes that filename. Plaintext passwords are forbidden in configuration JSON, source, logs, and versioned files. The PostgreSQL initialization secret remains in its protected ignored plaintext file for POSTGRES_PASSWORD_FILE, not an encrypted vault; API hashes remain in the database and the signing key remains protected outside Git.

PowerShell JSON/Unicode examples must use UTF-8 bytes and application/json; charset=utf-8. On Windows PowerShell 5.1, save `.ps1` files containing literal Unicode as UTF-8 with BOM, read JSON with Get-Content -Raw -Encoding UTF8, and configure `$OutputEncoding` for native pipelines when needed. Explicit `.venv` Python paths require no activation; a bare python command is valid only when it selects that interpreter.

## 📚 **Collection pagination and fixed-role administration**

**Breaking contract:** collection GETs return `{count, page, page_size, items}`, including GET `/test` (formerly a bare array) and GET `/users`. Share the dependency/schema in `app/pagination.py`: page is an integer >=1, default 1; page_size is an integer 10–50, default 50. Reject fractional text; never coerce `1.0` into a page. Count matching rows before pagination; retain count on an empty out-of-range page, return 0 when no rows match, and apply selected ordering, defaulting to ID ascending for inherited lists. Apply LIMIT/OFFSET in SQL; count and items must be obtained in **one statement snapshot**, including empty pages. Fetch only the bounded page into Python. Single-object endpoints such as health are exempt. Separate page requests do not promise a frozen snapshot across HTTP calls. References: [PostgreSQL snapshots](https://www.postgresql.org/docs/17/transaction-iso.html) and [transaction advisory locks](https://www.postgresql.org/docs/17/explicit-locking.html).

**Central authorization:** all protected endpoints use `require_scopes` through FastAPI Security. Standard accounts retain test:read/test:write and current scope intersection, with no user-management permission. Administrator access covers all shared-authorization endpoints, including future scopes, without a static all-scopes list as its authority. OAuth2 advertises users:manage for discoverability; that scope can only be requested by an administrator. Never trust a JWT role claim: retrieve current account/active state/role on every request. A token issued before demotion cannot retain administrative access. `/health` and `/token` remain public; PostgreSQL master credentials are never API credentials.

**Administrative APIs:** POST `/users` accepts strict username/password/optional role (standard by default), hashes Argon2id before persistence, returns 201 or duplicate 409. GET `/users` is paginated. PUT `/users/{id}/role` replaces the fixed role, returns 404 for missing users and 409 for last active administrator demotion. All require an active administrator, returning 401/403 appropriately. Expose only id, username, role, is_active, created_at; never return hashes/passwords. No account deletion or role/permission tables; supervisor is added by migration 006 and password reset follows the later contract.

**Concurrency:** bootstrap, managed creation and role replacement share transaction advisory lock **719230818**, distinct from migrations. Recheck the API actor under that lock and lock affected rows. Count active administrators only after taking the lock; reject removing the last one. Do not derive authorization from a count performed outside the transaction. Tests must exercise competing self-demotions and confirm exactly one active administrator remains. Direct privileged master SQL is outside these API safeguards and must uphold the invariant independently.

**Administrative audit:** after committed creation/role replacement, record administrator_id, user_id, previous_role and new_role. Request context supplies interaction ID automatically. Use SecretStr for password request representations, retain recursive body redaction and safe parser/exception responses, and verify both INFO and DEBUG. Do not log plaintext, hashes or tokens, including failure paths.

**ASGI failures:** before response start, emit one safe 500 with interaction ID. After response start, never send another response or silently swallow failure; log original safe category/frames once, then raise ResponseStartedError with a fixed safe message and suppressed exception context so server traceback formatting cannot reveal the original text. Always reset request/logger context. Validation responses preserve loc/type and use known-category English guidance (required/type/limits/invalid value) without rejected values or parser context.

**Postman maintenance:** scripts read `.items` and verify count/page/page_size. Preserve unchecked id/value Params and percent encoding, exact-ID and combined assertions. Contains pages need not contain the newly inserted row when results span pages. Keep requests 01–08 and the additional 09–20 administrator/standard folder, automatically capture each token/user ID, and leave every credential/token/ID variable empty in versioned JSON. Document persistent user creation/role changes and fresh usernames on reruns. Keep the complete README JSON synchronized using `scripts/sync_postman_readme.py`; distinguish HTTP replay, OpenAPI, actual Swagger clicks, Postman import and JavaScript sandbox execution.

### 📝 **Google-style code documentation**

Use English **Google-style docstrings** for relevant modules, classes and functions. Explain purpose; include Args, Returns and Raises when meaningful. Document persistence, transaction ownership, required permissions, side effects and concurrency guarantees where they affect use. Do not invent empty sections, mechanically repeat parameter names or restate simple instructions. Internal comments explain decisions/reasons. Update stale documentation with behavior changes, remove redundant code when safe, and avoid abstractions without a concrete purpose.

Example:

```python
def change_role(actor_id, user_id, role):
    """Replace a role under the administrator-membership lock.

    Args:
        actor_id: Administrator revalidated inside the transaction.
        user_id: Immutable target account ID.
        role: Validated replacement role.

    Returns:
        Public account metadata and its previous role after commit.

    Raises:
        UserManagementError: If access was revoked or demotion would remove
            the last active administrator.
    """
```

## 🧪 **QA delivery and traceable checks**

**Single source:** maintain stable scenario IDs, English names, objectives, prerequisites/data, actors, exact manual steps, HTTP contracts, approval criteria, types and explicit unittest selectors in `qa/scenarios.json`. Never recycle or renumber an existing ID. A scenario can require several tests, and all must pass. Add new tests to a relevant scenario; static inventory checks reject missing or unmapped selectors. Keep visual browser/Postman/physical terminal/hosted workflow checks manual unless that interface was actually executed.

**Generated documentation:** edit the catalogue and `docs/QA_SETUP.md`, then run `python scripts/generate_qa_docs.py`. Do not independently edit generated `docs/QA_TEST_PLAN.md`. Verify using `--check`; a test requires exact equality. `docs/README.md` indexes architecture, API, operations and QA material; the project README presents the project, while NEXTGENERATION remains the conventions guide. Use English, clear emoji headings, **bold**, useful tables/examples and explicit expected-negative HTTP statuses.

**Collection traceability:** catalogue postman_requests owns each canonical request's scenario assignment. After changing IDs/names/links run `python scripts/sync_qa_postman.py`, then `python scripts/sync_postman_readme.py`. Assertions and request descriptions carry the exact catalogue identity. Preserve original requests and unchecked filters. Request 10 now omits role to verify the default. Requests 21–39 continue the same user's promotion/demotion, preserving original/pre-demotion tokens and capturing actual IDs. Keep every credential/token/ID variable empty, including lifecycle probes. Never overwrite personalized YAML or add a competing canonical collection.

**Runner:** `.\.venv\Scripts\python.exe scripts/run_checks.py` is the full local/CI entry point. It checks Python/dependencies/Docker, enables real UUID-isolated tests with random credentials/free ports, and never reads normal configuration/secrets. Safe results distinguish PASS/FAIL/SKIP/BLOCKED/MANUAL; dependent lifecycle phases block after failed preparation. Missing required prerequisites or skipped/incomplete mandatory automation returns nonzero. Fixed-port checks are optional and independently reported; do not stop an occupied service. `--unit-only` is explicitly partial/nonzero; `--preflight-only` verifies tools, never approval. Successful mandatory automation still leaves human QA sign-off pending.

**Sanitized reports:** write ignored reports/summary.md, results.json and junit.xml with stable scenario IDs/names and separate scenario/test totals. Discard raw test stdout/stderr, assertion messages, exception messages/locals, requests and configuration. Only public selectors, outcomes, fixed reasons and exception categories may enter reports; do not upload logs, secret files or environments. Reproduce failed selectors in isolation rather than exposing private assertion values. Fixture/cleanup errors prevent full automated approval. Cleanup targets only exact resources allocated by that run; do not discover/delete resources by broad prefixes.

**Pipeline:** `.github/workflows/qa-checks.yml` uses workflow_dispatch, Docker-enabled Ubuntu, Python 3.12, minimum contents:read permission and a bounded timeout. Preparation, same runner, summary and reports are visible steps; upload only sanitized reports on always(), including failures when possible. A local YAML check is not a GitHub run: require actual revision/run URL/artifacts before pipeline approval. Never add personal/production secrets. PyYAML is a declared development dependency for structural workflow checks; Python 3.15 can use the supported pure-Python build without a native compiler.

**Final request outcome:** final event is `HTTP request finished`, with outcome completed for normal processing (including expected 4xx/5xx), failed for unexpected processing/send errors, or cancelled. Preserve the status accepted by the ASGI send callback; before any accepted status use null/response_started false, not a fabricated 499/500. A streamed failure after accepted 200 headers must keep 200 and outcome failed. Do not send another response after accepted headers or a failed transport. Log safe diagnostics once, propagate a fixed safe exception and always clean context. Automated tests cover before/after headers, transport failure, expected errors and cancellation; this is not evidence of a client physically receiving bytes.

## 🔑 **Own-password security and precise QA evidence**

Migration **004_add_credential_version.sql** adds positive BIGINT credential_version default 1 without replacing existing hashes/users/data. New JWTs require that integer claim; compare it with the current active database account on every request. Tokens missing the claim require reauthentication after upgrade. A password change invalidates only that account's earlier tokens, not peers or the persistent signing key.

**PUT /users/me/password:** allow both active profiles via shared authentication with no administrator/test scope requirement. Identify the caller only from verified sub/version; strict SecretStr current_password/new_password, no extra fields. Under FOR UPDATE, recheck version/active state, verify current Argon2id and reject unchanged new password. Commit only new Argon2id/version together; stale concurrent callers get 401. Return empty 204, wrong current/same password 400, invalid authentication 401, invalid JSON/types/fields 422. Omit the **whole body** at all logging levels, not just sensitive keys. After commit log exactly **API password changed**, INFO, with user_id and the automatically propagated request context.

### 🔐 **Administrator password reset and review conventions**

PUT `/users/{id}/password` requires a current active administrator and strict SecretStr `new_password` only. Use the shared 15-1024 Unicode character new-password policy and Argon2id; existing passwords remain valid for authentication. Reject self-targeting with 400 and direct callers to self-service with current-password verification. Under advisory lock 719230818, lock/recheck actor role, active state and credential_version, then lock the target and atomically update its hash/version. Missing target is 404, missing/revoked authentication 401, insufficient permission 403, invalid body/path 422. Inactive targets remain inactive. Only the target's earlier tokens are revoked; in-flight requests already authorized may finish.

Exclude the entire body of all `/users/.../password` paths from inspection, including malformed/rejected requests. After commit emit INFO **API password reset** with administrator_id, user_id and outcome=completed; transactional safe rejections emit WARNING **API password reset rejected**, outcome=rejected/status. Interaction ID comes from request context. Authentication/schema failures occur before the operation and use generic safe rejection/final request events, without claiming a verified actor or successful reset.

Swagger collection controls must have explicit query metadata, descriptions, constraints, defaults and examples. GET `/users` exposes public ID, exact username, username_pattern, role, active status and shared creation-day/range filters, plus page/page_size and whitelisted order_by/order_direction. Canonical Postman request 61 demonstrates page=2/page_size=10 and optional unchecked test id/value. User collection examples expose their own public filters. Requests 62–76 use fresh isolated reset accounts; all secret/token/ID variables remain empty. Preserve historical private YAML artifacts. Record actual Sonar availability, fallback tool versions/findings and manual checks separately; successful scans do not prove absence of vulnerabilities.

**Public disposable examples:** the main QA guide uses API/Swagger 6969, PostgreSQL host 6669/internal 5432, database/master ouroboros_qa with suggested OuroborosQA-Database-2026!, API admin/AdminPassword-2026! and default/DefaultPassword-2026!. These specifically requested documentation examples are public suggestions only, never runtime defaults, automatically created credentials, existing private values or filled Postman variables. Real credentials remain forbidden in versioned content. Alternative ports belong in troubleshooting; never stop an occupied service. Automation retains random credentials/free ports.

**Per-scenario log evidence:** maintain log_evidence in the single catalogue: real execution-file pattern, how to locate the current run, exact messages, level/category/method/path, context fields/values, conditions, required/optional/absent events and forbidden data. Distinguish DEBUG absence at INFO. X-Interaction-ID changes per request and is not a user/record ID; never require fixed random IDs, timestamps or line numbers. HTTP tests use tests/support_log_evidence.py to assert the same catalogue rules on actual request logs; consistency checks require every documented event message to exist in source. Static/manual-only cases must explicitly avoid claiming an application event that is not emitted.

**Fixture outcomes:** SafeResult retains safe fixture scope, phase and exception category without arbitrary error text. Aggregation matches class/module scopes to each mapped selector. Preparation failures cause BLOCKED when verification is prevented; teardown/class/module cleanup failure causes FAIL, even when individual tests remain PASS. Preserve those individual records and fail the overall run. Test all four fixture phases, unaffected scopes, actual teardown exceptions and sanitized artifacts; do not rely solely on the global exit flag.

**Response log timing:** HTTPX response hooks run after headers and may precede body delivery and the ASGI middleware's final offloaded log write. The test evidence helper consumes the response body, reads a live capture and waits at most two seconds for that response's exact interaction ID and `HTTP request finished` event. Missing completion still fails the existing evidence assertions; headers alone are not a completed middleware operation.

## Language conventions

Use English for code identifiers, including variable and class names, comments, log messages, and all project documentation. Conversation with the project owner may remain in Portuguese.

## 📝 Maintain this guide

Add sections as the project evolves: verified setup instructions, configuration fields, startup and shutdown, migrations, endpoint examples, logging conventions, tests, and troubleshooting.

Document confirmed behavior. Mark proposals as planned until implemented. Use placeholders for personal configuration and secrets. Keep instructions in **English**, with clear headings and useful examples.

## 🐍 **Ouroboros catalogue phase one**

Ouroboros derives its API infrastructure from Foundation; migrations **001–004** and the historical `public.foundation_migrations` tracking table retain their names and checksums. Migration **005** adds exactly eleven catalogue tables and no seed records. See [CATALOGUE.md](docs/CATALOGUE.md) for the authoritative column summary and pending decisions.

- Keep database-generated BIGINT identity sequences independent per table. IDs concatenate the fixed prefix with at least seven decimal digits, using `greatest(7, length(sequence::text))` so `lpad` cannot truncate. Generated stored IDs and guarded sequence/prefix/fantasy components remain immutable; deleted numbers are not reused in normal operation. Never use MAX + 1 or reset sequences on the normal database.
- Fixed Portuguese fantasy names are stored on every row; friendly record display names are separate, editable Unicode fields. Technical tag/category/classification names use lowercase ASCII snake_case. Do not add unapproved uniqueness rules.
- Same-work provenance and availability must be enforced through composite foreign keys. Use restrictive deletes; never cascade consumption history. Index referencing keys without duplicating an existing leading primary/unique index.
- Synopsis text must be English; a SQL CHECK cannot reliably detect language. Preserve supplied titles and their language codes.
- Platform paid status is independent of optional decimal price; an absent price does not mean free. Episode and duration flags are independent expectations. Availability-specific prices/free overrides are not modeled.
- Tags apply universally to a work; optional watchlist/history provenance records where an association was introduced. It is not a complete tag-change history. Ordered reusable tag relationships do not apply to works until explicitly associated.
- Individual domain CRUD is implemented in the subsequent phase-one API work. Do not add AI, advanced search, frontend, work types, classification display order, prediction history, in-progress state, reassessment scheduling, tag removal history, soft deletion or audit-event tables without separate approval.
- Review **feat/initial-tables** before any merge into **main**. Never commit, push or merge without the owner’s request. Use `git add --all`, then `git status` and `git diff --cached` before an authorized commit.
- Integration tests use exact UUID-owned disposable infrastructure with fresh random credentials and ephemeral ports. Cleanup may remove only that run’s allocated resources; never Foundation or normal Ouroboros data. Preserve the inherited `FOUNDATION_RUN_INTEGRATION` opt-in for compatibility.

Historical test counts and observations elsewhere in this guide describe Foundation stages, not current Ouroboros execution evidence. Current evidence belongs in sanitized reports and the phase delivery record.

## 🔌 **Phase-one catalogue CRUD conventions**

The current [catalogue API guide](docs/CATALOGUE_API.md) owns the endpoint/permission/filter matrix. It supersedes earlier schema-only statements about CRUD and two-role operation. Migration **006** extends the fixed role CHECK to **standard, supervisor, administrator**, without editing migrations 001–005 or replacing accounts.

- Preserve separation: fixed named contracts/query schemas in `app/schemas/catalogue.py`, routers in `app/endpoints/catalogue.py`, transactional persistence in `app/catalogue_repository.py`, trusted ordering/snapshot composition in `ordering.py` and `collection_queries.py`, and SQL templates in `sql/queries/`. Never use client-selected table/column names or raw direction tokens.
- Every catalogue resource has seven endpoint forms, including filtered administrator bulk PUT/DELETE. Ordered classifications are approved in migration009; no seed data or additional domain tables are introduced. POST/PUT/GET-by-ID and page items share the same complete persisted record model.
- Supervisor can use test scopes, own-password change and catalogue GET/POST/PUT/DELETE by ID. It cannot administer users, reset another password or DELETE all. Standard has no catalogue access; administrator retains all protected APIs. Derive supervisor catalogue access from current role even for old test-only tokens. Authentication always reloads current role/state/version.
- Catalogue writes take membership lock **719230818**, then lock/revalidate the actor row/version, then catalogue rows. All privileged paths share consistent ordering with administration. Keep last-active-administrator protection for demotion to **either** standard or supervisor. User creation/role replacement must revalidate API credential version too. Direct master SQL remains outside these API invariants.
- PUT intentionally supports omissions and full GET-record echoes. Omitted fields preserve locked values; null clears only nullable fields. Unknown properties and empty objects are 422. Immutable metadata and added_at may be echoed unchanged; changes are 422. watched_at stays editable. Validate the complete merged record under its row lock, then assign only submitted mutable fields; never use unprotected read/merge/write.
- All collection GETs expose every supported filter, page/page_size and real enum order_by/order_direction fields. Any public stored scalar is sortable; private user fields never are. Default catalogue sequence ascending and inherited ID ascending, with NULLS LAST in both directions and unique-ID ascending tie-breaks. Count and items share one statement snapshot; separate requests do not promise a frozen snapshot.
- Every filter is ANDed before ordering/count/pagination. Document exact versus unmodified ILIKE semantics explicitly, preserving empty text and escaped wildcard behavior. Use driver parameters for values and trusted SQL identifiers for names. No arbitrary short text limits or automatic synopsis-language detection.
- DELETE by ID returns empty 204, missing 404, dependencies 409. Administrator collection DELETE/PUT accept strict scalar and creation-range filters, require explicit confirm=true for execution, reject page/order/display controls, support dry_run previews, and return bounded counts/summary. No filters selects the whole table; zero matches returns zero. Never TRUNCATE, cascade or reset sequences. Do not add bulk mutations for infrastructure/users/audits.
- Emit safe deletion audit only after commit: actor_id/resource/target_id/deleted_count/outcome plus automatic interaction ID. Expected transaction rejections record rejected status without committed counts. Shared pre-repository failures use existing safe rejection events; never expose database error text.
- Maintain canonical examples through `scripts/sync_catalogue_postman.py`, then `sync_qa_postman.py` and `sync_postman_readme.py`. All collection GETs show editable filters, optional fields unchecked, paging and valid ordering. Both deletion examples are skipped unless a private local `catalogue_destructive_opt_in=isolated` is set; DELETE all additionally ships with confirm=false. Opt-in is only for explicitly selected disposable QA flows, never normal data.
- QA scenarios **14.1–14.7** cover the new API work. Use owned UUID Docker resources and fresh per-test databases for destructive verification. Manual Swagger/Postman/terminal/hosted-CI evidence remains separate from schema and HTTP automation. No commit, push or merge is part of this request.

## 🛡️ Permanent security and next-phase rules

Follow the [audit, datetime and bulk contracts](docs/AUDIT_DATETIME_BULK.md). New API mutations must use the Database provider and its request audit context; do not bypass transactional mutation triggers. Audit entry/finalization must not hold locks across business work or overwrite committed evidence. Keep audit reads read-only, bounded and authorized; omit returned audit bodies from their own access records. Add migrations rather than changing applied files.

Use `app/datetimes.py` for UTC server clocks, canonical instants, source context and presentation. Never invent historical creation dates, infer geographical zones from offsets, accept timezone-naive datetime inputs or filter formatted strings. New bulk APIs require strict known filters, preview support, explicit confirmation and authority revalidation inside the transaction. Preserve sequences and restrictive foreign keys.

Consult official [OWASP ASVS 5.0.0](https://owasp.org/projects/asvs) and the [Cheat Sheet Series](https://cheatsheetseries.owasp.org/) for Authentication, Authorization, Password Storage, Logging, Input Validation and Error Handling, linked individually in the contract guide (consulted 2026-10-19). Concrete review checks are current-account authorization on every request; transaction-time privilege checks; parameterized SQL and whitelisted ordering; Argon2id; current-password self change; administrator reset of another account; credential-version revocation; bounded redaction and whole token/password body omission; protected audit reads; safe centralized errors and audit rollback tests. Scans/tests do not establish blanket OWASP compliance. No password GET/recovery endpoint may return an existing password. Future email recovery must reset passwords. Do not store plaintext or reversible passwords. Never include credentials, hashes, tokens, signing keys or connection strings in logs/audits/errors/public response schemas.

The audit error catalogue is versioned JSON and validated before startup. Include app JSON resources in review packaging. Update the single QA catalogue, generated plan, canonical Postman JSON and embedded README together; actual bulk examples remain isolated opt-in with confirm=false. GUI/JavaScript execution must be evidenced separately from HTTP/schema tests.

## 🪜 Classification tiers and complete test CRUD

- Tier positions are distinct from identity sequences. Migration009 is the sole sequence-based backfill; emit safe inspection/fallback facts. Lock membership719230818, actor, classification list719230819, then records; use deferred uniqueness during atomic shifts. Restore individual audit mode before the primary mutation so primary target/differences remain correct. Bound final summaries after adding counts; explicitly flag omitted samples/details.
- Keep test IDs as integers. All seven test routes share strict full-record, UTC/date and filter contracts; individual writes use current test:write, bulk writes current administrator. Revalidate permissions/version within the business transaction.
- Shared pagination may inline its fixed filtered CTE with NOT MATERIALIZED; count and page must still share one SQL statement/snapshot. Never infer a production capacity target from local benchmarks. Record environment, datasets, p50/p95, throughput, errors, plans and cleanup; pin optional review tools separately in requirements-review.txt.

Migrations009–010 add independent classification tier positions and complete integer-ID test CRUD with shared creation dates, UTC presentation, strict filters and confirmed administrator bulk operations. See [the authoritative contracts](docs/TIERS_AND_TEST_CRUD.md) for the one-time inspected backfill, atomic append/insert/move/delete behavior, bulk tier exception, scope matrix and restart instructions. Never reseed or replace the existing nine normal classifications. Destructive QA remains isolated; review measurements and findings are documented separately.

## Calendar-filter development rule

Use shared calendar/date-bound parsing and UTC boundary calculation in app/datetimes.py for every publicly filterable timestamp. Expose exact-day and optional date/timestamp ranges consistently in GET and bulk schemas. Resolve omitted filter_timezone from application_timezone before calculating mixed boundaries; display_timezone never controls filtering. Calendar upper dates include the whole final local day via next-day midnight, while timestamp upper bounds remain exclusive instants. Never add 24 hours to a UTC start to calculate a local day or cast stored rows to dates. Keep strict validation, NULL-history exclusion and GET/preview predicate parity. See the calendar-day section in [the datetime contract](docs/AUDIT_DATETIME_BULK.md).

## Atomic array POST development rules

All eleven catalogue POST routes and /test accept either the existing object or a nonempty array of existing create-schema objects. Preserve object response compatibility; array results use CreatedBatch with created_count/full items in request order, including final persisted classification tiers. See [the authoritative creation contract](docs/BATCH_CREATION.md). Do not extend token, users, passwords or audits to array creation.

Use one connection/transaction, one current actor authorization recheck, server-generated metadata, parameterized reused INSERT RETURNING, safe zero-based item errors and all-or-nothing business/audit evidence. Do not introduce implicit references, cross-table creation, new uniqueness constraints, resets or seed data. Classification arrays retain membership/actor/list lock order, sequential tier edits, cached locked list size, deferred uniqueness and bounded shift evidence; refresh created tiers once before returning.

api.max_batch_size defaults to 300 (integer 1?10000); api.max_creation_body_bytes defaults to 4194304 (integer 1024?67108864). Keep body acceptance limits separate from bounded audit/log capture and retain both. Batch evidence samples at most 20 IDs/shifts, prioritizes counts under small capture budgets, and never copies full records into summaries. Ordinary creation permissions also apply to arrays; administrator bulk PUT/DELETE confirmation rules do not apply to POST. Maintain Swagger examples, canonical Postman/embedded JSON, scenarios 17.1?17.6 and generated QA plan together. All test mutations remain in owned disposable infrastructure.

## Backend review development rules

Migration011 adds platform_access_types and platform_url without rewriting historical values. Follow the [backend review contract](docs/BACKEND_REVIEW.md) for their operation matrix, user filters, shared new-password policy and bounded login admission. Keep newly set passwords at 15-1024 Unicode characters through app/password_policy.py; never apply this minimum to existing-password verification or rewrite stored hashes. Single-worker login limits are 10/account and 50/direct client per 300 seconds with at most 10000 hashed entries, no active-limit eviction, 429/Retry-After and automatic expiry. Disable Uvicorn proxy header handling; do not trust arbitrary forwarded addresses. Keep reference readOnly metadata on fields rather than duplicating it on referenced models. QA scenarios 14.2/14.3/14.6/14.7 map all four relationship regressions; 18.1-18.4 cover these backend additions. Regenerate all maintained QA/Postman artifacts together.

## First frontend and browser session rules

Browser origin/transport denials must use BROWSER_ORIGIN_REJECTED and never be presented as account-permission failures. Diagnose safe interaction traces and current public account metadata before proposing role changes. Catalogue actions need a native /cadastros navigation fallback, visible progress and focused/visible feedback; a banner outside the viewport is not sufficient. Preserve the shared administrator/supervisor scope semantics for bearer and browser sessions and never auto-promote an account to fix configuration. See the normal login/navigation diagnosis in docs/FRONTEND.md.

The approved frontend is Angular 22 with strict TypeScript, standalone feature components, Signals, stable Signal Forms and zoneless change detection under frontend/. Scope includes home/login, reusable selection pages and individual platform/tag/work-classification creation, consultation, editing and confirmed deletion. Build optimized hashed static assets before FastAPI startup; Node is a build tool, never a production runtime. Keep the lazy registration route, same-origin HttpClient/Router services and exact API payload contracts. Follow docs/ANGULAR.md for reproducible versions, commands, caching, CI and isolated QA. Do not restore the obsolete handwritten frontend or rebuild on every application start. Visible interface text is Portuguese; identifiers/comments/logs/developer docs remain English. Use original local SVG assets and the exact palette with measured contrast. Follow [the browser/security/operation contract](docs/FRONTEND.md).

Keep opaque bounded server-side sessions, HttpOnly SameSite=Strict cookies, Secure under HTTPS, same-origin/synchronizer CSRF checks and current account/version/role checks. The default fails closed for HTTP. Development HTTP requires explicit browser.allow_loopback_http plus a matching loopback origin and peer; never silently enable it for existing configuration or production. Never trust arbitrary proxy headers. Preserve bearer precedence and existing /token clients. All browser bodies (including CSRF-bearing responses) are wholly omitted from logs/audits; never persist browser secrets in web storage or source. Cookie catalogue mutations use existing routes, authorization, repositories and transactional auditing. Static shells/assets are outside database auditing; API mutations remain audited. Sessions are process-local and cleared on restart/shutdown.

Maintain scenarios 19.1-19.5 in the single catalogue and regenerate the manual plan. Test writes only in owned disposable infrastructure. Distinguish actual browser/keyboard/mobile checks and screenshots from HTTP/schema tests. Preserve drafts on validation/network/expiry errors, prevent duplicate clicks, render user values as text and reset editable state immediately after confirmed creation, retaining success identity separately. No public signup or work/watchlist/history forms are in this phase.

## Angular refinement development rules

Reuse shared catalogue layouts, typed resource definitions, field rendering, confirmation, pagination and selection cards. Keep UI labels separate from API keys: Nome fantasia maps to platform_name/display_name_*; never confuse it with immutable fantasy_name_<table>. Technical suggestions are effective validated values, never submitted placeholders. Preserve manual/original names, request sequencing, keyboard completion without POST, changed-field PUT semantics, immediate success reset and non-secret drafts on failure. Consultations fetch one ten-item page, use generated public filter/order metadata, escape literal ILIKE wildcards and require confirmation for individual DELETE. No bulk frontend writes.

Browser sessions have explicit 7200-second idle and 43200-second absolute deadlines, independent of bearer lifetime. Renew only accepted authenticated user activity; passive background checks never renew and absolute expiry never slides. Test with controlled clocks. Approved ports are 6969 application/API, 6669 normal PostgreSQL host, 2469 Angular preview and owner-selected 2424 disposable PostgreSQL host; container PostgreSQL remains 5432. Require operator-selected QA ports, never allocate a silent fallback. Preserve the round mark, single Ouroboros wordmark, Portuguese accessible eye control and semantic required fields with sparse #E6BD68 accent. See docs/ANGULAR.md and docs/FRONTEND.md for current workflows; historical delivery sections describe their stated earlier revision only.

The owner additionally selected **4242** for the second disposable PostgreSQL cluster used concurrently by the derived-project isolation test. Set **OUROBOROS_QA_DERIVED_DB_PORT=4242**. This is QA-only; never substitute it for normal 6669 or HTTP/Angular 2469. The hosted workflow requires all three QA port inputs from its operator.

## Phase-one registration control rules

Use the current [registration UI contract](docs/REGISTRATION_UI.md). Only the home-return link receives scoped enlarged navigation styling. Keep required-field legend placement, #E6BD68 markers, existing routes and disabled future workflows. Registration labels use Cadastrar item. Shared platform boolean checkboxes start unanswered and require explicit true/false, with a clear reset; never coerce unanswered to false.

Separate exact decimal-comma parsing/API strings from two-place pt-PT monetary display. Use installed Angular formatCurrency for ordinary display, with exact decimal-string arithmetic/fallback where Number would lose precision. Do not rewrite input while typing or round stored/API values through floating point; disclose extra precision. Omit blank POST price_amount; preserve PUT omission versus explicit null clearing. Keep optional currency null, explicit zero, only configured EUR/USD/BRL choices and legacy code preservation. New access selections are only application or website singleton arrays; preserve multi/link legacy arrays until explicit replacement. Site alone reveals the URL; retain hidden drafts but omit them on non-Site POST and explicitly clear persisted URLs when changing access on PUT.

Autocomplete is now an anchored top-twenty first-page dropdown without paging/load-more or a permanent no-results block, superseding the earlier paginated autocomplete behavior only. Preserve debounce, stale-result guards, literal substring predicates, deterministic ordering, keyboard precedence and existing edit confirmation. Consultation pagination remains unchanged. Classifications must retrieve the complete tier/name order in bounded pages before exposing positions as complete. Create defaults to implicit append; edit preselects current tier with 1..N moves. Failures/count drift require retry; only backend transactions shift other rows. No new endpoints, enums, migrations, fields or dependencies are introduced by these UI rules.

## Phase-one cancellation, consultation and search-memory rules

Use shared create/edit forms with exact Cadastrar/Salvar edição actions, a Cancelar action and actual baseline dirty tracking. Guard route exits, cancellation, resource changes and logout with one cancel-first discard prompt. Use native beforeunload only for browser unload, with its documented browser limits. Confirmed successes and clean/restored originals never prompt. Default dialog focus and prominent styling belong to cancellation; affirmative buttons are explicit secondary actions without implicit form submission. Preserve direct ordinary saves and no automatic mutation replay.

Keep consultation at ten items per page, independent of twenty-name autocomplete. No create button belongs in consultation. Selected public filter fields render compact shared value controls beside the fixed primary Search/Clear column; picker overlays never displace Search. Removing a field removes its predicate. Retain up to five successful applied criteria sets per resource in session-scoped service memory, never results or credentials. Clear on logout/expiry/new sign-in, offer reapply-at-page-one and clear history. Preserve resource, successful criteria, ordering, page and rendered scroll on return from individual edits. No persistence endpoint, Works catalogue or later-phase workflow is added. The exact #E6BD68 accent is decorative on light surfaces; keep dark readable labels/legend and semantic required state rather than claiming the accent itself meets text contrast. See docs/REGISTRATION_UI.md for measured contrast, current behavior and verification.
# Frontend delivery verification rule

When UI changes are reported missing, identify listener ownership and current directory before restarting anything. Compare the current source fingerprint, generated index and complete imported asset graph with actual HTTP delivery, including cache headers. `npm run build` must run the provenance stamper; compare the loaded document's footer/meta build ID with `/frontend/build-info.json`. HTTP evidence does not establish the state of an already-open browser tab or existing service-worker registrations. Preserve drafts, cookies and normal data; do not automatically clear browser storage. See [delivery diagnosis](docs/FRONTEND_DELIVERY_DIAGNOSIS.md) for safe commands and timestamped findings.
## Focused Platform form rule

Platform price/currency controls are visible only while paid is true. Retain drafts across toggles, omit both from unpaid creation payloads (including invalid hidden drafts), and clear them on successful creation/reset. Validate visible price as before. Platform name/access red required markers precede their labels; other resource markers remain unchanged.

Platform registration uses two-state false-initialized booleans and requires user input only for display name and access type. Scope its bold #DC3545 required markers and transferred outlined back-link styling to Platform; preserve other resource screens. Keep empty selector prompts as presentation only, exact approved name/price help, currency without explanatory captions, and hide internal price precision notes in this form. Preserve exact payload serialization and legacy edit values. This supersedes older Platform tri-state instructions. See docs/REGISTRATION_UI.md.

## Shared labels and contextual help — Change 01

Use `FieldLabel` in `frontend/src/app/shared/field-label.ts` for field-label presentation and help. All fantasy-name fields in create/edit and search use `FANTASY_NAME_LABEL` and `FANTASY_NAME_HELP_TEXT`; do not duplicate their wording in templates. Required markers precede labels with a space and use bold #DC3545. Derive their visibility from existing requirements; this visual rule does not introduce validation requirements. Preserve field IDs and required/invalid semantics. Remove redundant optionality wording, move explanatory field help to associated tooltip descriptions, and retain visible errors, progress, confirmations and actual data. Help buttons are non-submit, keyboard reachable, open on hover/focus/touch and close on Escape/outside click without submitting or dismissing a parent dialog. Keep exact fantasy-name help distinct from filter syntax guidance. This supersedes older permanent-help and marker-color presentation instructions only; no API, schema, mutation or authentication behavior changes.

Tooltip/currency visual correction: keep the information glyph small, borderless and raised immediately after the label text, with an invisible enlarged hit area. Description fields have no help icon/tooltip; price uses centralized `PRICE_HELP_TEXT`. Use the existing currency component with a normal dropdown trigger and an anchored panel containing search followed by plain listbox rows; no duplicate placeholder or option buttons. Production uses `style-src 'self'`, so put these scoped styles in `frontend/styles/shared-fields.css`, included in the external Angular stylesheet bundle. Do not use Angular component `styles`/`styleUrl` injection here or weaken CSP to fix presentation. Verify external CSS delivery under the actual policy; JSDOM component tests alone do not establish visual behavior.

Soft Amber (`--soft-amber: #D99A45`) is an additive shared palette token for information glyphs; preserve all other palette tokens and required-marker red #DC3545. Keep the existing glyph size/position and interactions. The floating tooltip belongs above and to the right of its glyph, with a rightward offset rather than centered placement. Price errors use the approved Portuguese “centavos” wording without changing validation/formatting.
## Description limits and classification position controls

Follow [DESCRIPTION_AND_TIERS.md](docs/DESCRIPTION_AND_TIERS.md). `app/text_limits.json` is authoritative for the description limit; frontend constants are generated before npm build/test/watch. Apply the Unicode 16 extended-grapheme limit only to the three `description_` fields, including create/array/update/bulk inputs; never extend it to observations/synopsis. Pin both segmentation implementations and verify shared official conformance vectors before changing versions. Preserve historical oversized output and unrelated omitted-description edits; never silently truncate or migrate normal TEXT data. Reuse DescriptionInput with live counter, optional/no-tooltip presentation, whole-edit overflow prevention and deferred IME commit. Inspect normal historical lengths only with existing interactive credentials, never extracted secrets.

Use the same SearchableDropdown for currency and numeric classification positions. Automatic append is an empty UI value and omitted POST tier; displayed N is explanatory, not transaction authority. Keep persisted edit tier and backend transactional shifts. Paginate only the current-order view at ten rows, retaining its approved items and total while dropdown choices cover the complete verified order. Preserve deterministic ordering and failure handling. These rules supersede earlier position-name options and unlimited description input instructions only.
