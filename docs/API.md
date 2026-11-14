# Ouroboros API — Database v1

This API serves the existing registered Database v1 installation. It does not
mount the historical integer-ID/public-schema API, Frontend, browser sessions,
forms, Assistance, inference or speech routes. The historical implementation is
retained for reference and its existing tests. JWT/Argon2id libraries, the shared
UTC utilities and the existing bounded login throttle are reused.

## Start Database + API

The active module lives at `modules/api`. Use
`modules/api/postman/Basic.postman_collection.json` for the Basic HTTPS API.
Its example environment has empty credential/token fields. Keep real values in
private local environments and keep certificate verification enabled.

Run in PowerShell from `C:\Dev\Ouroboros`, using the existing virtual environment:

```powershell
.\.venv\Scripts\python.exe -m pip install -r modules/api/requirements.txt
.\.venv\Scripts\python.exe start.py --with-api
```

`--api-inspect` is SELECT-only and requests the existing PostgreSQL master
password through the shared masked terminal reader. It checks the canonical
provisioning registry, applied baseline checksum, actual tables/columns, enabled
audit/metadata triggers and runtime capability flags. It does not read the saved
master secret. `--api-migrate` requests that same existing SQL password, applies
only the new API migration, and prepares a separate protected runtime SQL login.
It preserves the bootstrap person, dedicated API identity, membership and human
password. Never substitute the application password for the SQL master password.

`--with-api` also handles a fresh installation. The trusted host provisioner
prompts for separate SQL and super-administrator credentials, creates the schema,
activates Basic (Plan 1: Database + API Integration), and prepares the restricted
API SQL login through checksummed migrations. Subsequent starts reuse this state.
The API container connects only as `ouroboros_api_login`. Both services belong to
the Compose project `ouroboros`, using `compose.basic.yaml` and the module-local
Compose inputs. Docker Desktop shows `postgresql-1` and `api-1` in that group.
Their internal PostgreSQL address is `postgresql:5432` on `ouroboros_default`.
The API profile starts no Frontend or Assistance services. Startup validates
workspace ownership and refuses an unowned occupied port. Volumes persist across
starts. The one-time owner-authorized reset is outside the normal launcher.

- Swagger at **https://localhost:6969/docs**.
- OpenAPI JSON at **https://localhost:6969/openapi.json**.
- Health at **https://localhost:6969/health**.
- SQL administrative host port remains **6669**; API-to-PostgreSQL container
  traffic uses the shared network at `postgresql:5432`.

The default `start.py` starts Database + API. `start.py --database-only` starts
only PostgreSQL without requiring API configuration or TLS. `--check` validates the
selected configuration without SQL/Docker changes, including when combined with
an API mode. `--help` lists the explicit modes without importing site packages.

## Required HTTPS and local Windows certificates

The API terminates TLS directly in Uvicorn on the approved published port 6969.
The container port 8000 speaks TLS as well. Forwarded headers are disabled.
Swagger uses the configured HTTPS server and absolute HTTPS OAuth token URL.
The health check verifies the certificate and configured hostname.
TLS 1.2 or newer is required.

Install mkcert from its official release. Run these commands in PowerShell
from `C:\Dev\Ouroboros`. `mkcert -install` installs a local development CA in
the Windows trust store and can request Windows elevation. Each client needs
to trust this CA. The certificate covers localhost and 127.0.0.1.
Keep the CA private key on this developer machine.

```powershell
mkcert -install
New-Item -ItemType Directory -Force .secrets | Out-Null
mkcert -cert-file .secrets/api-local.pem -key-file .secrets/api-local-key.pem localhost 127.0.0.1
.\.venv\Scripts\python.exe -c "from pathlib import Path; from database.secrets import protect; protect(Path('.secrets'), True); protect(Path('.secrets/api-local-key.pem'))"
.\.venv\Scripts\python.exe start.py --with-api
```

Use the default `tls` references in `modules/api/config.jsonc` for these files. Private
keys belong in protected `.secrets` or an operator-owned external directory.
Relative references resolve from the repository root. Certificate/key contents
never belong in JSONC. The launcher restricts the key's Windows DACL to the
current user and mounts both files read-only as Docker secrets. PEM/key/PFX/P12
files are excluded from the build context. The launcher validates a full TLS
handshake, matching key, certificate dates and SAN hostname before starting
Database or API. The container repeats validation before opening SQL.
Missing, expired, mismatched or invalid material fails with a corrective English
message. `--check` validates configuration structure. Actual API startup also
validates the certificate material.

For production, set `tls.certificate_file` to the operator's PEM certificate
chain and `tls.private_key_file` to its protected unencrypted PEM key. Set
`tls.server_name` to the certificate's DNS hostname used by clients. Supply the
required chain and distribute private-CA trust when applicable. Publication stays
on 127.0.0.1 at port 6969. Remote exposure requires an operator-managed ingress
appropriate for that loopback binding. After renewal rerun `start.py --with-api`.
The displayed Swagger URL follows `tls.server_name`.

The local preparation follows the official mkcert instructions and OWASP TLS
guidance. [mkcert](https://github.com/FiloSottile/mkcert),
[OWASP TLS Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html).

## Configuration and secrets

`modules/api/config.jsonc` is copied from the commented `modules/api/config.example.jsonc` when
absent. Unknown/missing fields, duplicate keys at any depth, wrong types,
nonfinite JSON values and invalid bounds are rejected. Paths resolve from the
repository, independently of the terminal working directory. Database names,
schema, vocabulary, table names and prefixes come only from root
`provisioning.jsonc` and the matching registered contract. No structural database
mapping is duplicated in API configuration.

| Parameter | Meaning |
| --- | --- |
| host / port | Local publication, fixed to 127.0.0.1:6969 |
| tls.certificate_file / private_key_file | Protected PEM certificate-chain/key references |
| tls.server_name | Certificate SAN hostname and HTTPS Swagger/OpenAPI origin |
| startup_timeout_seconds | Docker readiness wait, 10–3600 seconds |
| connect_timeout_seconds | SQL connection establishment, 1–60 seconds |
| statement_timeout_ms | SQL statement deadline, 100–60000 milliseconds |
| connection_acquire_timeout_seconds | Wait for API connection capacity, 1–60 seconds |
| max_connections | Bounded concurrent runtime connections, 1–32 |
| token.issuer / audience | Exact signed JWT identity/recipient checks |
| token.clock_skew_seconds | Allowed JWT clock skew, 0–30 seconds |
| limits.request_bytes | Complete body budget, with an absolute 1 MiB ceiling |
| limits.batch_items | Atomic creation array limit, absolute ceiling 300 |
| limits.page_size | Maximum requested page size, absolute ceiling 100 |
| limits.token_ttl_seconds | Issued lifetime, absolute ceiling 86400 seconds |

Every limit has integer `minimum`, `maximum` and default `value`. When a known
installation setting exists in `operator_setting`, its persisted minimum,
maximum and current value must all be integral and within the operator's JSONC
range. The current value must also fit the persisted narrower range. Invalid
settings are rejected with the permitted range; values are never silently
clamped. Unknown historical setting names are not interpreted by this module.
Batch/page/token adjustments take effect for subsequent requests. The body budget
and operational connection/container settings take effect on API restart.

`PUT /settings/{name}` accepts only `{ "value": <integer> }`; it cannot alter the
operator's JSONC boundaries, plan, roles or protected database records. A narrower
JSONC range that excludes an existing persisted setting must be reconciled by the
trusted SQL operator before serving requests.

Secrets are not in JSONC, source, command arguments, environment values, Swagger
examples or logs. API setup creates `.secrets/api_sql_password` and
`.secrets/api_token_signing_key` under protected current-user Windows DACLs
(POSIX 0700 directory/0600 files). Those files and both TLS files are mounted read-only in
the API container. The PostgreSQL master secret is never mounted there. The
container is read-only, has a temporary `/tmp`, drops capabilities and runs with
one Uvicorn worker. The signing key persists across restarts.

The SQL role `ouroboros_api_login` inherits only `ouroboros_runtime`, cannot create
objects/roles/databases, is not a superuser and is not a member of
`ouroboros_owner`. Runtime has no direct credential-table SELECT or ordinary
identity/authorization-table DML. Narrow SECURITY DEFINER capabilities provide
credential lookup and authorized account/permission/credential/setting/rule
operations. Their search_path is pg_catalog and all table references are
qualified. PUBLIC function execution is explicitly revoked. The SQL broker is
trusted to authenticate before binding actor context; tenants receive no SQL
credentials and cannot set that context themselves.

## Authentication

### Integration tokens

`POST /oauth/token` implements OAuth 2.0 Client Credentials using
`application/x-www-form-urlencoded`:

```text
grant_type=client_credentials
client_id=<issued credential ID>
client_secret=<issued secret>
scope=<optional space-separated resource:action permissions>
```

`client_secret_basic` is also supported through HTTP Basic. Use exactly one
authentication method; conflicting body/Basic credentials, duplicate fields,
unknown fields and unsupported grants are rejected. An optional requested scope
must be a subset of the identity's current authority. There is no redirect,
authorization-code flow or implicit human login. HTTPS is required for every
API connection, including local loopback.

Accounts are stored in the existing `api_user` table. Their Client Credentials
secrets use separate `api_user_credential` rows with kind `client_credentials`.
`client_id` is that credential's generated ID; it is not a SQL role or a person's
name. Secrets are generated with cryptographic randomness and Argon2id-hashed;
they are returned only once to the authorized caller that creates them. Such
secrets are not subject to the bootstrap human password's 16-character maximum.
There is no plaintext secret retrieval endpoint or routine-wide master credential.
Do not copy live credentials into Swagger examples, logs or documentation.

`POST /api-users` creates an ordinary identity, one of the permitted operational
profiles, optional new person/membership, individual permission grants and an
initial client credential in one audited transaction. Its response returns
`id_api_user`, `client_id` and `client_secret`. Store that one-time secret safely.
`POST /api-users/{id}/credentials` with an empty JSON object issues an additional
secret to its owner or an authorized administrator. Client credentials cannot
be issued for the reserved bootstrap identity. `DELETE /credentials/{client_id}`
revokes an owned credential or an authorized administrative target and increments
the identity's credential version, invalidating its existing tokens.

### Existing human bootstrap identity

The normal presentation-only release deployed on 2026-11-14 labels its login
field **Linked API User username**, using the existing **App Password**. It
removes the native browser Basic-authentication prompt without a schema upgrade.
The broader App User alias behavior described below belongs to the additive
upgrade. See [live verification and exact credential choices](ENGLISH_PRESENTATION.md).

`POST /auth/user-token` accepts only `username` and `password` and verifies the
existing `human_password` credential. It does not create, reset or convert that
credential and cannot authenticate a Client Credentials secret. This explicit
human endpoint is separate from OAuth Client Credentials. Swagger's **Authorize**
panel's **App User** section accepts **App User or linked API User** with the **App Password**,
or an existing **Human Access Token**. Both login names resolve to the same
unambiguous active human identity; ambiguous names and expired links are rejected.
Integrations use the separate **OAuth2 Client Credentials** section with their
issued `client_id` and matching `client_secret`. Client ID is an integration
credential identifier, not an App User or API User username. Obtain the pair from
`POST /api-users` when creating a separate integration identity, or from
`POST /api-users/{id}/credentials` for an eligible existing API User. The reserved
installation identity cannot receive Client Credentials. PostgreSQL administration credentials
are never application login credentials. Authorization remains in browser memory
and is cleared by a page reload; Swagger assets are served from the same origin.

The additive Database upgrade `003_app_username.sql` introduces the explicit App
Username and backfills only unambiguous eligible historical names. API migration
`api-v1/002` (`002_human_identity.sql`) adds human alias resolution. Existing
credential hashes, IDs and memberships are preserved. Use the existing interactive
startup/migration path to apply pending upgrades; never replay or edit registered
migrations. Both aliases share the same account authentication rate limit.

Signed HS256 tokens bind subject, credential ID/kind, credential version,
registered installation fingerprint, requested scope, issuer, audience, issued
time, not-before time, expiration and a random token ID. Every protected request
reloads active identity, live credential status, current version, current roles,
current personal links and effective permissions. Expired/tampered/revoked tokens
fail. Permission removal and deny rules apply immediately; a newly added
permission requires a new token if it was outside the old token's scope.
Authentication attempts reuse the bounded single-worker throttle: ten per
account and fifty per client address in five minutes, with hashed keys and
Retry-After. No request or response bodies are logged, including rejected tokens,
human passwords and one-time client secrets.

## Authorization matrix

All actions deny by default and require the relevant `resource:action` scope AND
current database authorization. List rules do not grant permissions. Any matching
deny rule overrides allow and role grants. If applicable allow-list entries
exist, an entry must match the resource/action; absence of a match restricts
access. Global and identity-specific rules both apply. Rules never dispense
with authentication, ownership checks or operational-profile ceilings.

| Profile | Initial authority and hard ceiling |
| --- | --- |
| user | Read its own personal resources. Every write requires an explicit persisted permission. No other person's private resources. |
| manager | Same personal reads; may create manager/user accounts. Business writes require explicit grants. Cannot create administrator/reserved accounts, promote itself, manage an existing manager, or assign authority it does not currently possess. |
| administrator | Seeded permissions for exposed administrative/business actions. Can manage ordinary accounts, explicit grants, rules and editable settings. Cannot assign the reserved function, change the contracted plan or access credential hashes. |
| super_administrator | Unique active holder, recognized by the protected singleton and exact active membership. Business administration and reserved SQL plan authority. Plan changes have no HTTP operation in this delivery. |

Profile and permission assignments persist in `role`, `permission`,
`api_user_role` and `role_permission`. Per-identity explicit grants use a private
`identity_<api_user ID>` role; they do not change shared profile permissions.
`PUT /api-users/{id}/permissions` replaces only those explicit grants, while
`PUT /api-users/{id}/role` replaces the operational profile and clears old role
assignments. Both require an administrator/reserved holder and reject self or
reserved targets. `PATCH /api-users/{id}` accepts only `is_active`, with the same
ceiling; deactivation and permission/profile replacement revoke earlier tokens.
Managers cannot use these existing-account operations.

The API serializes authority transitions and authenticated business operations
with the installation membership advisory lock within each SQL transaction.
Authority is revalidated in that transaction. Classification writes then take
the classification list lock before record locks, retain deferred uniqueness,
and audit/version every shifted record. Database masters remain trusted and
must preserve these contracts for direct SQL changes.

For personal resources, the API derives the person from one unambiguous active
person/API link whose person is active. No client-supplied `id_app_user` is
accepted in business bodies or used as proof of ownership. Zero/multiple active
links deny personal access. A client token alone does not prove a human login;
an integration with no link may operate on authorized shared catalogue resources
but cannot access lists/history. Personal ownership predicates apply before
pagination/counts and to reads, edits, deletion, relationships and every batch
entry. Administrative tokens also respect these personal ownership predicates.
Shared tags/categories can additionally be read by linked identities with read
permission. Owner fields cannot be replaced through PUT/PATCH.

`user_work:update` grants no `work:update`. Availability uniqueness and same-work
references, same-owner relationship keys and append-only charges remain enforced
by PostgreSQL. Private tags cannot cross owners. An administrator's access to
resources never includes secret/hash retrieval or arbitrary physical-table CRUD.

## HTTP business contract

The stable API resource keys below are logical names; validated provisioning maps
them to singular physical names, including alternate vocabulary. ID/metadata
field names in HTTP responses remain logical (`id_work`, etc.). Physical names
and SQL identifiers never come from request path/body strings.

Each exposed business collection has GET (bounded pagination, optional exact
`id` filter) and POST (one object or a bounded atomic array). Each individual
record has GET, PUT, PATCH and DELETE, except append-only charges, which have
only POST/GET. There is no destructive collection-wide PUT/DELETE in this
delivery and no generic table-name endpoint. Unknown/duplicate business query
fields are rejected. Pagination defaults to page 1 and ten records. Counts are
restricted to authorized records before paging.

| Shared catalogue resources | Personal resources |
| --- | --- |
| test, work, platform, work_availability, work_classification | user_work, user_platform |
| work_title_alias, work_external_reference | watch_list_entry, watch_history |
| platform_plan, platform_promotion | tag, tag_category, tag_relationship, tag_category_relationship, work_tag |
| | platform_subscription, subscription_charge, subscription_reminder, work_submission |

Submissions persist data only; no match-review automation or human review flow
is exposed. Reminder records do not send reminders. No app-user signup,
external-reference enrollment, generic role CRUD, generic plan CRUD, raw
credential CRUD, migration CRUD or writable audit/version endpoint is mounted.

- **PUT replaces the complete editable representation.** All required fields in
  its OpenAPI schema must be supplied. Omitted nullable fields become null;
  omitted fields with defaults reset to those defaults. IDs, owners and creation
  metadata are not editable or accepted as echoes. A classification replacement
  must supply its valid current/new tier; an omitted/null tier cannot replace an
  existing classification's required position.
- **PATCH changes only submitted fields.** Omitted fields retain their previous
  values. Null is accepted only by a nullable field. The complete merged state
  is validated before SQL. An empty patch is rejected.
- The historical API treated PUT as partial. That contract is deliberately
  incompatible and is not silently retained. Migrate partial callers to PATCH;
  do not run historical API containers against this schema.
- POST arrays commit or roll back together; indexed objects have the same strict
  field validation as individual creation. Classification batch output is
  reread after final shifts. Monetary values use decimal validation and business
  responses serialize exact decimal strings rather than floating-point prices.
- Unknown/extra body fields, including owner/role/plan/ID/audit fields, are
  rejected rather than ignored. SQL values use parameters; identifiers are
  composed only from the registered allowlisted mapping.
- UTC instants use the shared aware-datetime implementation. Naive timestamps
  are rejected. Unknown historical/source context remains unknown.

`GET /me` returns only the current technical identity/profile/link summary.
`GET /api-users` returns bounded non-secret ordinary account metadata.
`GET /audit` is restricted to administrators/reserved holder and returns bounded
read-only events. `GET /record-versions/{resource}/{id}` first authorizes the
underlying record and its owner, then returns bounded event-linked versions.

## Contracted plan and evidence

`GET /installation/plan` shows the active installation plan to the reserved human
holder. Bootstrap activates Basic automatically with Database + API Integration.
Frontend and Assistance exist in the module model and have no active Basic
entitlement. Plan changes have no HTTP/Swagger operation in this delivery.
Client Credentials cannot be issued for the reserved identity. The SQL
`change_plan` function rechecks the holder, active person and exact live link
under transaction locks and verifies that the selected existing plan bundles
Database + API Integration. The API does not invent or create additional plans;
the product/operator must define available plan compositions separately.

Each business mutation and privileged capability writes its existing mandatory
audit event and record version in the same SQL transaction. The technical actor
and optional acting person are bound from the verified identity, never payload
owner fields. Payloads, secrets and hashes are completely omitted. Versions
retain their event linkage. Commit, deferred constraints and audit persistence
finish before successful HTTP headers are sent. Audit/constraint failure rolls
back business changes. This is not master-resistant tamper-proof storage.

`modules/database/sql/api_migrations/001_api_runtime.sql` is registered as `api-v1/001`
with its exact SHA-256. `modules/database/sql/upgrades/002_basic_plan.sql` adds the Basic
display name as `database-v1/002`. Existing historical SQL and Database baseline
sources remain immutable. The API migration changes capabilities and seeds ordinary
role/permission definitions; it creates no replacement modules/database/table/ID scheme,
does not reseed normal classifications and does not change the initial Plan 1.
Its version is unique in the existing friendly-ID migration registry. Repeated
setup verifies its checksum and does not replay it. Later changes require a new
numbered API migration rather than editing an applied file.

## Errors and verification

Errors return `{ "error": { "code", "message", "interaction_id" } }` with safe
English messages. Validation errors omit rejected input and secrets. SQL errors
do not reveal statements/parameters. Typical statuses: 400 unsupported/conflicting
OAuth input; 401 missing/expired/revoked credentials; 403 denied authority; 404
missing/unowned record; 405 unsupported method; 409 uniqueness/FK conflict; 413
body budget; 422 invalid/extra fields or invalid complete state; 429 authentication
attempt limit; 503 unavailable database/capacity/configuration. Responses have
no-store caching and interaction IDs. Startup diagnostics report only safe
categories/classified causes, never private driver text or connection strings.

Automated commands:

```powershell
.\.venv\Scripts\python.exe modules/api/qa/run.py --pattern test_config.py
docker build -f modules/api/Service.Dockerfile -t ouroboros-api-v1:verification .
.\.venv\Scripts\python.exe modules/api/qa/run.py
```

The integration suite uses an exact UUID-owned PostgreSQL project/volume on the
approved QA port 2424. The real API container smoke test uses 6969 only if free;
it never chooses a fallback or stops an existing listener. Only resources created
by those tests are removed. Normal data is never seeded/mutated for QA.

Security decisions follow [OWASP ASVS](https://owasp.org/projects/asvs) and the
[Authentication](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html),
[Authorization](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html),
[Password Storage](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html),
[Logging](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html),
[Input Validation](https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html)
and [Error Handling](https://cheatsheetseries.owasp.org/cheatsheets/Error_Handling_Cheat_Sheet.html)
guidance. Test results do not establish blanket OWASP compliance. See
[API_QA.md](API_QA.md) for actual execution evidence and remaining manual checks.
