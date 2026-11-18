# Ouroboros API — Database v1

This API serves the existing registered Database v1 installation. It does not
mount the historical integer-ID/public-schema API, Frontend, browser sessions,
forms, Assistance, inference or speech routes. The historical implementation is
retained for reference and its existing tests. JWT/Argon2id libraries, the shared
UTC utilities and the existing bounded login throttle are reused.


## Scoped roles and permissions — current API contract

This authorization model follows the inspected Sympla reference in
`C:/Dev/ticketing_sympla/release/ticketing_sympla_app/core/rbac.py`, `auth.py`,
`identity.py` and its README identity section. Ouroboros retains its existing
FastAPI/JWT/human authentication, friendly IDs, ownership predicates, Argon2id,
transactional audit/version triggers and restrictive database relationships.
No Sympla provider token, Django dependency or Sympla database is imported.

### Independent section/action permissions

`read` authorizes GET, `write` creation POST, `edit` PUT/PATCH and credential
issuance POST, and `delete` DELETE. Actions do not imply one another. A role
with catalogue:write can create a platform but cannot list, edit or delete it.
Token issuance and GET /me require valid current credentials, not a resource grant.

| Section | Ouroboros resources |
| --- | --- |
| identity | API accounts, role assignment, activation, soft deletion and client credentials |
| roles | Custom role creation, metadata and permission replacement |
| authorization | Permission catalogue, individual grants and allow/deny restrictions |
| catalogue | test, work, platform, availability, classifications, work aliases/external references and platform plans/promotions |
| personal | user_work, user_platform, lists/history, tags/categories/relationships, work tags and submissions |
| subscriptions | subscriptions, payment snapshots and reminder records |
| settings | Bounded installation settings |
| audit | Read-only audit events and record-version evidence |

GET /permissions requires authorization:read and returns 32 codes, each with its
section, action and description. A code without an implemented operation adds no
new operation. OpenAPI publishes `x-required-permission` for protected resources.
Missing permissions return 403 with the safe error envelope and, when rejected
by the request permission check, `error.required_permission`.

Roles and individual grants combine additively. Applicable deny rules still win;
allow lists restrict existing authority and never grant it. Personal ownership
remains mandatory even for broad section permissions or an administrator. An
integration without a current person link cannot use personal resources.
Ordinary audit:read delegates see only their own audit events. The reserved
holder and existing administrator profile retain installation audit visibility.
Version reads also require read authority/ownership on the underlying record.

### First custom role and account

Use an authorized human/bootstrap token in Swagger. These examples contain only
sample values; do not place live secrets in files or command arguments.

```http
POST /roles
Content-Type: application/json

{"name":"Catalogue reader","description":"Shared catalogue reads only","permissions":["catalogue:read"]}
```

Copy the returned generated `identifier` into `role_identifier`:

```http
POST /api-users
Content-Type: application/json

{"username":"catalogue-integration","role_identifier":"RO0000001"}
```

The account response returns its existing-style `id_api_user`, generated credential
`client_id` and a random `client_secret` once. Use those Client Credentials to
obtain a Bearer token. The selected role does not create a reserved master or SQL
login. Optional app_user_name creates a linked person; it does not create a human
password credential. New account creation requires identity:write and authority
over every granted role permission. Supplying initial individual permissions also
requires authorization:edit.

### Role and individual-grant operations

| Operation | Required section permission | Behavior |
| --- | --- | --- |
| GET /roles and GET /roles/{identifier} | roles:read | Read system/custom metadata and grants; internal per-identity roles are hidden |
| POST /roles | roles:write | Create a role with a unique trimmed printable name (1–80 characters), optional description (up to 200) and permissions |
| PATCH /roles/{identifier} | roles:edit | Change supplied name/description; no empty patch or null fields |
| PUT /roles/{identifier}/permissions | roles:edit | Replace all role grants; revoke tokens of affected accounts |
| DELETE /roles/{identifier} | roles:delete | Delete only an unreferenced custom role, including its grant rows |
| PUT /api-users/{identifier}/role | identity:edit | Set role_identifier; preserve individual grants and revoke old tokens |
| PUT /api-users/{identifier}/permissions | authorization:edit | Replace all direct grants while retaining the assigned role |
| POST /access-rules with api_user_identifier and permission | authorization:write | Add one individual grant and return its identifier; invalidate existing tokens |
| DELETE /access-rules/{identifier} for a grant | authorization:delete | Remove that individual grant and invalidate existing tokens |
| GET /access-rules | authorization:read | Return restrictive rules in items and additive grants in individual_grants, each with a kind discriminator |
| GET /api-users/{identifier} | identity:read | Read safe metadata, selected role and individual/effective section permissions |
| DELETE /api-users/{identifier} | identity:delete | Soft-delete, deactivate and revoke tokens; preserve historical foreign keys |

Example individual grant:

```json
{"api_user_identifier":"AU0000002","permission":"catalogue:read"}
```

The legacy restriction body remains supported separately:

```json
{"id_api_user":"AU0000002","rule_kind":"deny","resource":"platform","action":"read"}
```

These two formats cannot be mixed. A restriction's identifier refers to an
access_rule row; a grant's identifier refers to a role_permission row in the
identity's private grant role. Both keep their existing generated ID machinery.
Global/wildcard restriction mutation is reserved to the protected holder.

System user/manager/administrator roles are immutable through role CRUD. Reserved
and identity_-prefixed names are rejected; internal individual-grant roles are
not ordinary editable roles. Assigned roles cannot be deleted, including roles
referenced by soft-deleted identities. Role metadata/permission replacement and
deletion require authority over their current permissions. Creation/replacement
also checks every requested new permission. Account role, grants, credentials
and status operations require authority over the target's current grants, plus
requested new grants. Token scope restrictions also bound delegation: a narrowed
token cannot mint broader credentials/accounts using the legacy profile path.
The caller's own role/status/grants and the reserved identity cannot be changed
through these administrative endpoints. Self client-credential operations still
require identity:edit/delete and authority over the account's existing grants.

### Compatibility and protected authority

Existing resource:create/read/update/delete permission rows and legacy profile
payloads remain accepted. Public write/edit map to the existing SQL create/update
actions; no applied action CHECK, prefix or historical permission ID is rewritten.
Fine-grained resource grants continue to work without being broadened into whole
section grants. Existing ordinary accounts receive no new section administration
grants during migration. The existing administrator system profile receives the
section catalogue consistent with its administrative purpose; it is still not
the reserved human holder. Older tokens do not automatically gain new scopes.

The old role-name payload retains its profile ceiling and legacy replacement
semantics. Use role_identifier for the Sympla-style delegated workflow and to
preserve individual grants on a role change. Custom-role administration uses
current scoped authority rather than a mandatory administrator name. The profile
matrix later in this guide describes compatibility profiles, not a hard-coded
administrator requirement on the new custom-role workflow.

Authority is rechecked under the installation membership lock in the mutation
transaction. Role/grant/status/credential changes increment the relevant account
credential versions, invalidating old JWTs. Deny/allow restrictions also apply on
every request. Mandatory evidence failures roll back role/grant/account mutations.
The reserved singleton, SQL master, current human login aliases and HTTP plan-change
prohibition remain separate. No role can grant reserved status, alter the SQL
master, expose credential hashes or bypass personal ownership.

### Migration and deployment

New `api-v1/003`, `modules/database/sql/api_migrations/003_scoped_rbac.sql`, adds
role.is_system and nullable api_user.deleted_at, marks existing system/internal
roles, extends the permission catalogue and installs narrowly granted SQL
capabilities. It preserves all previous migration/baseline bytes, identity IDs,
human/client credential hashes, memberships and normal records. SaaS accounts are
not reseeded. Run the trusted normal startup or the existing interactive
`start.py --api-migrate` path to apply it, then restart through `start.py --with-api`.
Configuration-only --check neither applies it nor proves live schema readiness.
The normal database was not migrated or seeded during implementation/QA.

Security decisions follow the project [OWASP references](https://owasp.org/projects/asvs)
and [Authorization guidance](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html).
Passing focused tests is not a blanket OWASP compliance statement.

### Scoped-RBAC verification

On the operator-selected disposable PostgreSQL port 4242, all 11 scoped-RBAC
tests passed. They cover action independence, custom roles, delegation ceilings,
narrow token scopes, credential impersonation prevention, role/direct-grant token
revocation, individual grant add/remove, soft deletion, protected system identities,
personal ownership, deny precedence and rollback on mandatory audit failure.
The existing API integration suite passed 14 tests; its two real port-6969
container/restart checks skipped because the normal service was preserved.
Three API configuration tests, five central startup tests and the automated
Swagger authorization harness passed. Both configuration-only startup modes
passed. All 157 OpenAPI operations match this guide's inventory and protected
operations publish their required permission. Applied baseline/SQL files retain
their exact bytes. Generated output is private in reports/scoped_rbac*.txt.

The initial QA attempt refused occupied port 2424, which belongs to the normal
Sympla database. After the operator explicitly selected 4242, the suites ran
sequentially in UUID-owned projects and removed only their own containers/volumes.
No normal account, credential, role or permission was changed, and neither
Sympla nor Ouroboros was restarted. Applying api-v1/003 and inspecting the normal
installation through the existing interactive master-credential workflow remain
deployment steps; successful --check does not substitute for that migration.


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
.\.venv\Scripts\python.exe -c "from pathlib import Path; import sys; sys.path.insert(0, 'modules'); from database.secrets import protect; protect(Path('.secrets'), True); protect(Path('.secrets/api-local-key.pem'))"
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
secret only with identity:edit and authority over the target's current grants,
including for self-issuance. Client credentials cannot
be issued for the reserved bootstrap identity. `DELETE /credentials/{client_id}`
requires identity:delete and authority over the target's grants, then increments
the identity's credential version, invalidating its existing tokens.

### Existing human bootstrap identity

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

## Legacy profile compatibility matrix

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
assignments when the legacy role-name payload is used. The role_identifier
payload preserves direct grants instead. Scoped authority and target-delegation
ceilings apply to the new workflow; self/reserved targets are protected.
`PATCH /api-users/{id}` accepts only `is_active`; deactivation and permission/role
replacement revoke earlier tokens. A manager profile alone does not grant these
operations; explicit effective permissions are required.

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
external-reference enrollment, generic plan CRUD, raw
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
`GET /audit` requires audit:read and returns bounded read-only events. Ordinary
delegates see their own actor events; administrator/reserved holders retain
installation visibility. `GET /record-versions/{resource}/{id}` requires audit:read
and authorizes the underlying record and owner before returning bounded versions.

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
[API_QA.md](../../docs/API_QA.md) for actual execution evidence and remaining manual checks.

## First protected query in Swagger

1. Start Docker Desktop. In PowerShell run `Set-Location C:\Dev\Ouroboros`.
   If needed create the environment with `py -m venv .venv`, then install the
   dependencies as shown above. Run
   `.\.venv\Scripts\python.exe start.py --with-api --check`.
   Expect `Database + API configuration validated; no services or SQL data changed.`
2. Open `modules/api/config.jsonc`, copied from `config.example.jsonc` if absent.
   Keep the fixed host/port and fill TLS file references for your trusted PEM
   certificate/key. Follow the certificate preparation commands above.
   Root `provisioning.jsonc` and `modules/database/config.jsonc` remain separate;
   follow [DATABASE.md](../database/DATABASE.md) for their fields.
3. Run `.\.venv\Scripts\python.exe start.py --with-api`.
   Expect `Database + API ready. Swagger: https://localhost:6969/docs` with the
   default server name. A validation failure is a failure, not partial readiness.
4. Open `https://localhost:6969/health`; expect `{"status":"ready"}`.
   Then open `https://localhost:6969/docs` with certificate verification enabled.
5. Click **Authorize**, use the **App User** section, and enter the existing App
   Username (or its unambiguous linked API Username) and App Password. The custom
   local Swagger control obtains a Human Access Token in memory. Alternatively
   call `POST /auth/user-token` and paste its token into **Human Access Token**.
   Do not paste a password or SQL credential into the token box.
6. Expand `GET /me`, click **Try it out**, then **Execute**. Expect HTTP 200 with
   `id_api_user`, `username`, `roles`, `person`, `super` and `kind`; the token is
   not returned by this query. Without authorization expect 401.
7. With catalogue read permission try `GET /work?page=1&page_size=10`. Expect
   HTTP 200 with a page of authorized records (possibly empty), not a permission
   grant caused by opening Swagger. Reloading the page clears authorization.

If the live database has not yet received the additive human-alias migration,
its alias behavior is not established by the source documentation. Use the
existing interactive `--api-inspect` / `--api-migrate` workflow, preserving all
existing credentials. No password reset/retrieval, public registration or email
recovery route is implemented here.

| Credential label | Meaning | Where to use it |
| --- | --- | --- |
| App Username | app_user.username human login alias, distinct from display name | App User sign-in / auth/user-token |
| API Username | api_user.username technical identity login alias when linked to an eligible human credential | Same human endpoint with App Password; not a Client ID |
| App Password | Existing human password stored only as an Argon2id hash | Human sign-in only |
| Client ID | Generated api_user_credential ID for a client_credentials row | OAuth2 Client Credentials |
| Client Secret | Random integration secret returned once at issuance | OAuth2 Client Credentials; not the App Password |
| PostgreSQL Master Username / Password | SQL initdb administrator | SQL client and trusted interactive provisioning; never Swagger |

## Complete API field defaults and activation

Every key is required. Defaults below mean template values when the local file
is absent; missing keys in an existing file fail instead of silently defaulting.
All file edits require `start.py --with-api` to recreate/restart the API and load
them. Existing requests do not reread JSONC. There is no live file watcher.

| Field | Accepted values and purpose | Template default |
| --- | --- | --- |
| host | Exactly 127.0.0.1, loopback publication | 127.0.0.1 |
| port | Integer exactly 6969, published HTTPS port | 6969 |
| tls.certificate_file | Nonblank path to valid PEM certificate/chain; relative to repository or absolute | .secrets/api-local.pem |
| tls.private_key_file | Nonblank path to protected matching unencrypted PEM key | .secrets/api-local-key.pem |
| tls.server_name | DNS hostname or IPv4 matching certificate SAN; 1–253 characters using letters, digits, dots and hyphens, beginning/ending alphanumeric | localhost |
| startup_timeout_seconds | Integer 10–3600, Docker readiness seconds | 120 |
| connect_timeout_seconds | Integer 1–60, SQL connect seconds | 5 |
| statement_timeout_ms | Integer 100–60000, SQL statement milliseconds | 10000 |
| connection_acquire_timeout_seconds | Integer 1–60, concurrency-capacity wait seconds | 5 |
| max_connections | Integer 1–32, concurrent SQL connections in this single worker | 8 |
| token.issuer | String of 1–128 characters, JWT issuer to issue and require | ouroboros-api |
| token.audience | String of 1–128 characters, JWT audience to issue and require | ouroboros-integrations |
| token.clock_skew_seconds | Integer 0–30, JWT validation tolerance seconds | 0 |

Changing issuer/audience causes tokens issued with old values to fail subsequent
validation after restart. TLS renewal also requires restart. Neither operation
changes SQL credentials or application password hashes.

Each `limits.<name>` object contains exactly `minimum`, `maximum`, `value`.
All three must be integers between 1 and the absolute ceiling, and satisfy
`minimum <= value <= maximum`. The minimum/maximum define the operator's allowed
range; value is the default when no recognized persisted adjustment exists.

| Limit name | Meaning | minimum / maximum / value defaults | Absolute ceiling |
| --- | --- | --- | --- |
| request_bytes | Complete HTTP request body bytes | 1024 / 1048576 / 1048576 | 1048576 |
| batch_items | Number of objects in an atomic POST array | 1 / 300 / 100 | 300 |
| page_size | Maximum requested page length | 1 / 100 / 50 | 100 |
| token_ttl_seconds | Newly issued token lifetime in seconds | 60 / 3600 / 900 | 86400 |

Persisted setting updates use `PUT /settings/{name}`. Batch/page/token limits
are read for subsequent requests/issuance; already issued token expiration does
not change. The request body middleware takes its budget from the JSONC value
when the app starts: changing a persisted request_bytes setting does not rebuild
that middleware. Restart loads the effective persisted request_bytes value
(or the JSONC default if absent) before constructing the middleware. The settings response can therefore show a persisted
request_bytes adjustment that is not the currently installed middleware budget.

## Active and historical implementations

`start.py` selects `compose.basic.yaml`, which includes the module Compose files.
`modules/api/Service.Dockerfile` runs `python -m api.service.runtime`, creating
`api.service.app.create_app`. This is the implementation inventoried below.
Root `compose.yaml`, `modules/api/Dockerfile`, `api.runtime`, and `api.app` are
historical public-schema/four-module code retained for explicit disposable tests.
They are not the current Basic deployment. Their old `/token`, `/users`, plural
catalogue, browser, forms and speech routes are absent from this OpenAPI. Do not
use the historical Postman collection as the Basic route contract.
`qa/support/legacy` contains sanitized fixture schemas, not another operational
configuration. Original local JSON values are archived privately under
`.tmp/retired-module-configuration`; canonical JSONC installation values remain.

## Representative full replacement and partial update

These are explanatory examples for owned disposable data, not instructions to
mutate normal installation records. Substitute an existing authorized ID.

```http
PUT /platform/PL0000001
Authorization: Bearer <access token held privately>
Content-Type: application/json

{"name":"Example platform","description":null,"is_paid":false,"supports_episodes":false,"supports_duration":true,"url":null}
```

PUT returns 200 with the complete record. Supplying only `name` is still a full
replacement: optional description/URL reset to null and omitted booleans reset
to false. It requires `platform:update`; it cannot change owner/ID/creation fields.

```http
PATCH /platform/PL0000001
Authorization: Bearer <access token held privately>
Content-Type: application/json

{"description":"Updated note"}
```

PATCH preserves the existing name, flags and URL, and requires the same update
permission. `{"url":null}` explicitly clears a nullable URL; `{}` is rejected.
For `work`, a complete PUT must include `title` and `title_language`.
For a classification PUT include its required current/new tier as well as name
and display_name. Missing references or restrictive deletes can produce 409.

## Exhaustive OpenAPI operation inventory

Generated from `create_app(...).openapi()` without opening a SQL connection.
Every business operation below requires an authenticated human or client bearer
token plus its current permission/scope. Personal resources also require the
current unambiguous person link and owner predicate; shared tag reads follow the
visibility exception described above. Deny rules and profile ceilings still apply.
OpenAPI security schemes alone do not express these database authorization rules.

| Method | Path | Purpose | Authentication | Permission / additional restriction |
| --- | --- | --- | --- | --- |
| POST | `/oauth/token` | Issue an integration token using OAuth 2.0 Client Credentials | Client Credentials | Active client credential, optional scope subset |
| POST | `/auth/user-token` | Authenticate a linked human identity; never a Client Credentials secret | Human username/password | Active unambiguous human identity |
| GET | `/health` | Health | Public | SQL readiness only |
| GET | `/me` | Me | Bearer | Current active credentials |
| POST | `/api-users` | Create an authorized account and return its new client secret once | Bearer | identity:write |
| GET | `/api-users` | Accounts | Bearer | identity:read |
| GET | `/api-users/{identifier}` | Account | Bearer | identity:read |
| DELETE | `/api-users/{identifier}` | Soft-delete an ordinary API identity and invalidate its tokens | Bearer | identity:delete |
| PATCH | `/api-users/{identifier}` | Activate or deactivate an ordinary identity, revoking its existing tokens | Bearer | identity:edit |
| PUT | `/api-users/{identifier}/role` | Assign Role | Bearer | identity:edit |
| PUT | `/api-users/{identifier}/permissions` | Replace individual permission grants without changing the operational profile | Bearer | authorization:edit |
| POST | `/api-users/{identifier}/credentials` | Issue Client | Bearer | identity:edit |
| DELETE | `/credentials/{identifier}` | Revoke | Bearer | identity:delete |
| GET | `/installation/plan` | Current Plan | Human bearer | Reserved holder and installation_plan:read |
| GET | `/settings` | Settings Read | Bearer | settings:read |
| PUT | `/settings/{name}` | Settings Replace | Bearer | settings:edit |
| POST | `/access-rules` | Add Rule | Bearer | authorization:write |
| GET | `/access-rules` | Rules | Bearer | authorization:read |
| DELETE | `/access-rules/{identifier}` | Remove Rule | Bearer | authorization:delete |
| GET | `/audit` | Audits | Bearer | audit:read |
| GET | `/record-versions/{resource}/{identifier}` | Versions | Bearer | audit:read plus underlying resource read/ownership |
| GET | `/test` | List authorized records | Bearer | catalogue:read |
| POST | `/test` | Create one record or an atomic batch | Bearer | catalogue:write |
| GET | `/test/{identifier}` | Read an authorized record | Bearer | catalogue:read |
| PUT | `/test/{identifier}` | Replace all editable fields; omitted optional fields reset to defaults | Bearer | catalogue:edit |
| PATCH | `/test/{identifier}` | Update only supplied fields | Bearer | catalogue:edit |
| DELETE | `/test/{identifier}` | Delete an authorized record | Bearer | catalogue:delete |
| GET | `/work` | List authorized records | Bearer | catalogue:read |
| POST | `/work` | Create one record or an atomic batch | Bearer | catalogue:write |
| GET | `/work/{identifier}` | Read an authorized record | Bearer | catalogue:read |
| PUT | `/work/{identifier}` | Replace all editable fields; omitted optional fields reset to defaults | Bearer | catalogue:edit |
| PATCH | `/work/{identifier}` | Update only supplied fields | Bearer | catalogue:edit |
| DELETE | `/work/{identifier}` | Delete an authorized record | Bearer | catalogue:delete |
| GET | `/platform` | List authorized records | Bearer | catalogue:read |
| POST | `/platform` | Create one record or an atomic batch | Bearer | catalogue:write |
| GET | `/platform/{identifier}` | Read an authorized record | Bearer | catalogue:read |
| PUT | `/platform/{identifier}` | Replace all editable fields; omitted optional fields reset to defaults | Bearer | catalogue:edit |
| PATCH | `/platform/{identifier}` | Update only supplied fields | Bearer | catalogue:edit |
| DELETE | `/platform/{identifier}` | Delete an authorized record | Bearer | catalogue:delete |
| GET | `/work_availability` | List authorized records | Bearer | catalogue:read |
| POST | `/work_availability` | Create one record or an atomic batch | Bearer | catalogue:write |
| GET | `/work_availability/{identifier}` | Read an authorized record | Bearer | catalogue:read |
| PUT | `/work_availability/{identifier}` | Replace all editable fields; omitted optional fields reset to defaults | Bearer | catalogue:edit |
| PATCH | `/work_availability/{identifier}` | Update only supplied fields | Bearer | catalogue:edit |
| DELETE | `/work_availability/{identifier}` | Delete an authorized record | Bearer | catalogue:delete |
| GET | `/work_classification` | List authorized records | Bearer | catalogue:read |
| POST | `/work_classification` | Create one record or an atomic batch | Bearer | catalogue:write |
| GET | `/work_classification/{identifier}` | Read an authorized record | Bearer | catalogue:read |
| PUT | `/work_classification/{identifier}` | Replace all editable fields; omitted optional fields reset to defaults | Bearer | catalogue:edit |
| PATCH | `/work_classification/{identifier}` | Update only supplied fields | Bearer | catalogue:edit |
| DELETE | `/work_classification/{identifier}` | Delete an authorized record | Bearer | catalogue:delete |
| GET | `/work_title_alias` | List authorized records | Bearer | catalogue:read |
| POST | `/work_title_alias` | Create one record or an atomic batch | Bearer | catalogue:write |
| GET | `/work_title_alias/{identifier}` | Read an authorized record | Bearer | catalogue:read |
| PUT | `/work_title_alias/{identifier}` | Replace all editable fields; omitted optional fields reset to defaults | Bearer | catalogue:edit |
| PATCH | `/work_title_alias/{identifier}` | Update only supplied fields | Bearer | catalogue:edit |
| DELETE | `/work_title_alias/{identifier}` | Delete an authorized record | Bearer | catalogue:delete |
| GET | `/work_external_reference` | List authorized records | Bearer | catalogue:read |
| POST | `/work_external_reference` | Create one record or an atomic batch | Bearer | catalogue:write |
| GET | `/work_external_reference/{identifier}` | Read an authorized record | Bearer | catalogue:read |
| PUT | `/work_external_reference/{identifier}` | Replace all editable fields; omitted optional fields reset to defaults | Bearer | catalogue:edit |
| PATCH | `/work_external_reference/{identifier}` | Update only supplied fields | Bearer | catalogue:edit |
| DELETE | `/work_external_reference/{identifier}` | Delete an authorized record | Bearer | catalogue:delete |
| GET | `/user_work` | List authorized records | Bearer | personal:read |
| POST | `/user_work` | Create one record or an atomic batch | Bearer | personal:write |
| GET | `/user_work/{identifier}` | Read an authorized record | Bearer | personal:read |
| PUT | `/user_work/{identifier}` | Replace all editable fields; omitted optional fields reset to defaults | Bearer | personal:edit |
| PATCH | `/user_work/{identifier}` | Update only supplied fields | Bearer | personal:edit |
| DELETE | `/user_work/{identifier}` | Delete an authorized record | Bearer | personal:delete |
| GET | `/user_platform` | List authorized records | Bearer | personal:read |
| POST | `/user_platform` | Create one record or an atomic batch | Bearer | personal:write |
| GET | `/user_platform/{identifier}` | Read an authorized record | Bearer | personal:read |
| PUT | `/user_platform/{identifier}` | Replace all editable fields; omitted optional fields reset to defaults | Bearer | personal:edit |
| PATCH | `/user_platform/{identifier}` | Update only supplied fields | Bearer | personal:edit |
| DELETE | `/user_platform/{identifier}` | Delete an authorized record | Bearer | personal:delete |
| GET | `/watch_list_entry` | List authorized records | Bearer | personal:read |
| POST | `/watch_list_entry` | Create one record or an atomic batch | Bearer | personal:write |
| GET | `/watch_list_entry/{identifier}` | Read an authorized record | Bearer | personal:read |
| PUT | `/watch_list_entry/{identifier}` | Replace all editable fields; omitted optional fields reset to defaults | Bearer | personal:edit |
| PATCH | `/watch_list_entry/{identifier}` | Update only supplied fields | Bearer | personal:edit |
| DELETE | `/watch_list_entry/{identifier}` | Delete an authorized record | Bearer | personal:delete |
| GET | `/watch_history` | List authorized records | Bearer | personal:read |
| POST | `/watch_history` | Create one record or an atomic batch | Bearer | personal:write |
| GET | `/watch_history/{identifier}` | Read an authorized record | Bearer | personal:read |
| PUT | `/watch_history/{identifier}` | Replace all editable fields; omitted optional fields reset to defaults | Bearer | personal:edit |
| PATCH | `/watch_history/{identifier}` | Update only supplied fields | Bearer | personal:edit |
| DELETE | `/watch_history/{identifier}` | Delete an authorized record | Bearer | personal:delete |
| GET | `/tag` | List authorized records | Bearer | personal:read |
| POST | `/tag` | Create one record or an atomic batch | Bearer | personal:write |
| GET | `/tag/{identifier}` | Read an authorized record | Bearer | personal:read |
| PUT | `/tag/{identifier}` | Replace all editable fields; omitted optional fields reset to defaults | Bearer | personal:edit |
| PATCH | `/tag/{identifier}` | Update only supplied fields | Bearer | personal:edit |
| DELETE | `/tag/{identifier}` | Delete an authorized record | Bearer | personal:delete |
| GET | `/tag_category` | List authorized records | Bearer | personal:read |
| POST | `/tag_category` | Create one record or an atomic batch | Bearer | personal:write |
| GET | `/tag_category/{identifier}` | Read an authorized record | Bearer | personal:read |
| PUT | `/tag_category/{identifier}` | Replace all editable fields; omitted optional fields reset to defaults | Bearer | personal:edit |
| PATCH | `/tag_category/{identifier}` | Update only supplied fields | Bearer | personal:edit |
| DELETE | `/tag_category/{identifier}` | Delete an authorized record | Bearer | personal:delete |
| GET | `/tag_relationship` | List authorized records | Bearer | personal:read |
| POST | `/tag_relationship` | Create one record or an atomic batch | Bearer | personal:write |
| GET | `/tag_relationship/{identifier}` | Read an authorized record | Bearer | personal:read |
| PUT | `/tag_relationship/{identifier}` | Replace all editable fields; omitted optional fields reset to defaults | Bearer | personal:edit |
| PATCH | `/tag_relationship/{identifier}` | Update only supplied fields | Bearer | personal:edit |
| DELETE | `/tag_relationship/{identifier}` | Delete an authorized record | Bearer | personal:delete |
| GET | `/tag_category_relationship` | List authorized records | Bearer | personal:read |
| POST | `/tag_category_relationship` | Create one record or an atomic batch | Bearer | personal:write |
| GET | `/tag_category_relationship/{identifier}` | Read an authorized record | Bearer | personal:read |
| PUT | `/tag_category_relationship/{identifier}` | Replace all editable fields; omitted optional fields reset to defaults | Bearer | personal:edit |
| PATCH | `/tag_category_relationship/{identifier}` | Update only supplied fields | Bearer | personal:edit |
| DELETE | `/tag_category_relationship/{identifier}` | Delete an authorized record | Bearer | personal:delete |
| GET | `/work_tag` | List authorized records | Bearer | personal:read |
| POST | `/work_tag` | Create one record or an atomic batch | Bearer | personal:write |
| GET | `/work_tag/{identifier}` | Read an authorized record | Bearer | personal:read |
| PUT | `/work_tag/{identifier}` | Replace all editable fields; omitted optional fields reset to defaults | Bearer | personal:edit |
| PATCH | `/work_tag/{identifier}` | Update only supplied fields | Bearer | personal:edit |
| DELETE | `/work_tag/{identifier}` | Delete an authorized record | Bearer | personal:delete |
| GET | `/platform_plan` | List authorized records | Bearer | catalogue:read |
| POST | `/platform_plan` | Create one record or an atomic batch | Bearer | catalogue:write |
| GET | `/platform_plan/{identifier}` | Read an authorized record | Bearer | catalogue:read |
| PUT | `/platform_plan/{identifier}` | Replace all editable fields; omitted optional fields reset to defaults | Bearer | catalogue:edit |
| PATCH | `/platform_plan/{identifier}` | Update only supplied fields | Bearer | catalogue:edit |
| DELETE | `/platform_plan/{identifier}` | Delete an authorized record | Bearer | catalogue:delete |
| GET | `/platform_promotion` | List authorized records | Bearer | catalogue:read |
| POST | `/platform_promotion` | Create one record or an atomic batch | Bearer | catalogue:write |
| GET | `/platform_promotion/{identifier}` | Read an authorized record | Bearer | catalogue:read |
| PUT | `/platform_promotion/{identifier}` | Replace all editable fields; omitted optional fields reset to defaults | Bearer | catalogue:edit |
| PATCH | `/platform_promotion/{identifier}` | Update only supplied fields | Bearer | catalogue:edit |
| DELETE | `/platform_promotion/{identifier}` | Delete an authorized record | Bearer | catalogue:delete |
| GET | `/platform_subscription` | List authorized records | Bearer | subscriptions:read |
| POST | `/platform_subscription` | Create one record or an atomic batch | Bearer | subscriptions:write |
| GET | `/platform_subscription/{identifier}` | Read an authorized record | Bearer | subscriptions:read |
| PUT | `/platform_subscription/{identifier}` | Replace all editable fields; omitted optional fields reset to defaults | Bearer | subscriptions:edit |
| PATCH | `/platform_subscription/{identifier}` | Update only supplied fields | Bearer | subscriptions:edit |
| DELETE | `/platform_subscription/{identifier}` | Delete an authorized record | Bearer | subscriptions:delete |
| GET | `/subscription_charge` | List authorized records | Bearer | subscriptions:read |
| POST | `/subscription_charge` | Create one record or an atomic batch | Bearer | subscriptions:write |
| GET | `/subscription_charge/{identifier}` | Read an authorized record | Bearer | subscriptions:read |
| GET | `/subscription_reminder` | List authorized records | Bearer | subscriptions:read |
| POST | `/subscription_reminder` | Create one record or an atomic batch | Bearer | subscriptions:write |
| GET | `/subscription_reminder/{identifier}` | Read an authorized record | Bearer | subscriptions:read |
| PUT | `/subscription_reminder/{identifier}` | Replace all editable fields; omitted optional fields reset to defaults | Bearer | subscriptions:edit |
| PATCH | `/subscription_reminder/{identifier}` | Update only supplied fields | Bearer | subscriptions:edit |
| DELETE | `/subscription_reminder/{identifier}` | Delete an authorized record | Bearer | subscriptions:delete |
| GET | `/work_submission` | List authorized records | Bearer | personal:read |
| POST | `/work_submission` | Create one record or an atomic batch | Bearer | personal:write |
| GET | `/work_submission/{identifier}` | Read an authorized record | Bearer | personal:read |
| PUT | `/work_submission/{identifier}` | Replace all editable fields; omitted optional fields reset to defaults | Bearer | personal:edit |
| PATCH | `/work_submission/{identifier}` | Update only supplied fields | Bearer | personal:edit |
| DELETE | `/work_submission/{identifier}` | Delete an authorized record | Bearer | personal:delete |
| GET | `/permissions` | List independent section/action permissions | Bearer | authorization:read |
| GET | `/roles` | Roles | Bearer | roles:read |
| POST | `/roles` | Create | Bearer | roles:write |
| GET | `/roles/{identifier}` | Detail | Bearer | roles:read |
| PATCH | `/roles/{identifier}` | Patch | Bearer | roles:edit |
| DELETE | `/roles/{identifier}` | Remove | Bearer | roles:delete |
| PUT | `/roles/{identifier}/permissions` | Replace | Bearer | roles:edit |
Total: **157 operations**. Swagger/static assets and `/openapi.json` are framework documentation routes outside this operation inventory.

Collection queries accept page (integer >=1, default 1), page_size (integer >=1,
default 10, within effective limit), and optional exact id for business lists.
The current OpenAPI does not declare the middleware/repository exact-id filter
as a typed parameter; it is implemented in the request query handling. Unknown
and duplicate query keys are rejected. This is not the historical rich-filter
or destructive bulk API. subscription_charge has only collection POST/GET and
individual GET: no PUT, PATCH or DELETE. Record-version reads authorize the
underlying current record, so a deleted record is not automatically readable
through that endpoint even though evidence remains in the database.

## Earlier configuration/documentation verification

Historical evidence for the earlier configuration/documentation revision, before
the scoped-RBAC migration and its additional routes:

| Verification | Actual result |
| --- | --- |
| `start.py --database-only --check` and `start.py --with-api --check` | Both passed with existing installation values |
| Database `test_settings.py` | 7 passed |
| API `test_config.py`, `test_tls.py`, `test_swagger_ui.py` | 3 + 3 + 1 passed; Swagger authorization uses the automated UI harness |
| Central QA before the final fixture fixes | 63 run, 18 skipped, no failures |
| Central `test_infrastructure.py`, final `test_module_architecture.py` | 9 + 10 passed, including retirement guards and disposable configuration preservation |
| Database `test_database.py`, `test_user_migration.py` | 9 + 3 passed |
| Database `test_postgres.py` | 16 passed on UUID-owned disposable projects at approved QA ports 2424/4242, including actual database-only startup/restart |
| API `test_service.py` | 16 run: 14 passed, 2 skipped; real restricted-login PostgreSQL and HTTP application tests |
| Source/documentation comparison | 43 table headings, seven FK diagrams, all 148 OpenAPI operations, local document links and immutable baseline/SQL bytes checked |
| Existing normal HTTPS service | Certificate-verified GET health, Swagger HTML, OpenAPI route parity passed; unauthenticated GET /me returned 401 |

Commands for the module suites use
`.\.venv\Scripts\python.exe modules/<module>/qa/run.py --pattern <filename>`;
central focused checks use
`.\.venv\Scripts\python.exe qa/run.py --suite central --pattern <filename>`.
Private generated output is under ignored `reports/module_docs_*.txt`.

The API container smoke and combined Compose restart tests skipped because the
normal owned service already occupies approved port 6969. It was preserved, with
its SQL service, database and volumes. No alternate port was selected. The live
service belongs to this workspace's `compose.basic.yaml`; both normal containers
were healthy. No normal passwords, hashes, signing keys or tokens were extracted,
and no normal business mutations were used for QA. Interactive normal enrollment,
normal protected sign-in, a SQL-client GUI connection, and a fresh combined
container launch were not repeated. The existing normal schema's migration
registry was not inspected through extracted or substituted credentials.

The canonical local JSONC objects were compared before/after comment insertion;
their parsed values are unchanged. Original incompatible local JSON files were
archived byte-for-byte in ignored `.tmp/retired-module-configuration`. Exact
baseline source and SQL migration bytes match the prerequisite commit. README,
Frontend, Assistance and authentication/authorization implementations received
no edits in this configuration/documentation commit.

## PostgreSQL master replacement

Changing Database master_user is a host-only authenticated interactive workflow,
documented in [DATABASE.md](../database/DATABASE.md#what-happens-if-master_user-changes).
Normal `--with-api` startup runs it before preparing/starting the API. It does not
rotate the restricted API SQL password, signing key or SaaS credentials and has
no HTTP endpoint. `--api-inspect` and `--api-migrate` remain recovery tools for the
already active master; use normal startup to finish a pending handover first.
