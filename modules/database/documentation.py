"""Generate the versioned configuration example and exhaustive schema reference."""
import json
from pathlib import Path

from database.model import CATALOGUE, MODEL, ORDER, PROTECTED, render, table_sql
from database.settings import DERIVED, TABLES, mapping


def example():
    return {
        'format_version': 1, 'naming_rules_version': 1,
        'database_name': 'ouroboros', 'schema': 'ouroboros',
        'vocabulary': {group: {'name': value} for group, value in
                       (('work','work'),('platform','platform'),('tag','tag'),('activity','watch'))},
        'base_quantity_digits': 7, 'prefixes': TABLES,
    }


def write_reference(root):
    document = example()
    configuration = json.dumps(document, indent=2)
    configuration = configuration.replace('  "format_version"', '  // Structural values are frozen after provisioning; comments are ignored.\n  "format_version"', 1)
    configuration = configuration.replace('  "vocabulary"', '  // Singular vocabulary only; activity has no table or prefix.\n  "vocabulary"', 1)
    configuration = configuration.replace('  "prefixes"', '  // Unique immutable uppercase prefixes indexed by logical table key.\n  "prefixes"', 1)
    (root/'provisioning.example.jsonc').write_text(configuration+'\n', encoding='utf-8')
    header = '''# Database: new installation, delivery one

`start.py` now starts only PostgreSQL and provisions the new schema. It does not
import or start API, Frontend or Assistance. Plan 1 records the bundled Database +
API Integration entitlement; this does not start an API process. Frontend and
Assistance are modeled as additional modules. The historical API is incompatible
with this baseline and must be adapted in a later phase before use with this database.

## Install and start

From the project directory in PowerShell:

```powershell
.\\.venv\\Scripts\\python.exe -m pip install -r modules/database/requirements.txt
.\\.venv\\Scripts\\python.exe start.py --check
.\\.venv\\Scripts\\python.exe start.py --database-only
```

The default `python start.py` has the same database-only behavior. Python 3.10+
and Docker Compose v2+ are required. Paths resolve relative to the repository,
independently of the terminal working directory. `--check` creates missing local
configuration from examples, validates it, and makes no Docker/PostgreSQL changes.
Both local files are ignored by Git; their commented examples are versioned.
Unknown fields, duplicate keys (at every depth), wrong types, nonfinite JSON
numbers, naming collisions and invalid prefixes fail closed. JSONC supports real
line and block comments, not trailing commas. Comments do not affect structural identity.

Before a first real start, deliberately retire any previous instance occupying
6669. Startup refuses occupied ports and never stops previous instances or
silently selects another port. On 2026-11-12 Docker inspection established:
the `ouroboros` Compose project belonged to this workspace and its PostgreSQL
container mounted `ouroboros_postgres_data`; the separate Foundation project
mounted `foundation_postgres_data`. Reinspect labels/mounts before stopping,
because resources may have changed since that inspection:

```powershell
docker inspect ouroboros-postgres-1 --format '{{json .Config.Labels}} {{json .Mounts}}'
docker inspect ouroboros-api-1 --format '{{json .Config.Labels}}'
docker inspect ouroboros-frontend-1 --format '{{json .Config.Labels}}'
docker inspect ouroboros-assistance-1 --format '{{json .Config.Labels}}'
# Only after confirming these are the previous workspace-owned services:
docker stop ouroboros-frontend-1 ouroboros-api-1 ouroboros-assistance-1 ouroboros-postgres-1
.\\.venv\\Scripts\\python.exe start.py --database-only
```

The new Compose project is `ouroboros-database-v1`, with exactly one service,
`postgres`, and a NEW volume `ouroboros-database-v1_installation_v1`.
`modules/database/compose.yaml` is the sole Compose input for this track. The old root
Compose file and historical volumes remain untouched. No `down --volumes`,
volume removal, global prune, volume migration or automatic stop exists in startup.
Do not run the historical root orchestration against the new database.

First start requests a SQL master password, then an operator personal name,
dedicated API username and separate application password. Both human passwords
require 8-16 characters with uppercase, lowercase, digit and special character;
whitespace/control characters are rejected. All password prompts, including SQL
master and application password confirmations, show one `*` per typed character.
Backspace removes the last character and its asterisk; Enter confirms the input.
The real password is never displayed or logged. If masking is unavailable,
password entry remains hidden; a terminal that cannot disable echo is rejected.
This requested human policy differs from OWASP's recommendation to allow longer
passwords and does not apply to future generated client credentials. No default
password exists. Do not put passwords in commands, JSONC or documentation.

The SQL secret is `.secrets/database_sql_password`, separate from the historical
secret and application hash. Its directory and file receive a protected current
Windows-user DACL (POSIX 0700/0600). It is an administrative plaintext file secret,
not encrypted storage; Docker administrators and the OS account are trusted.
Startup fails if protection fails. The application password exists only during
enrollment and as an Argon2id hash in `api_user_credential`. It is never written
to the SQL secret. Secrets are never command arguments or Docker environment values.
Python cannot guarantee erasure of immutable password strings from process memory.

Schema creation is one transaction. Enrollment (person, API identity, credential,
membership, reserved singleton, modules and initial plan) is another single
transaction under the same installation advisory lock. Interrupting either can be
resumed by the same command without partial duplicate accounts or entitlements.
Subsequent starts reuse the existing operator without enrollment or user switching.
An interrupted first start may leave the schema ready for terminal enrollment.

Restart with the same start command. PostgreSQL remains running when the command
finishes. Operational address/health/timeout values take effect on the next start;
Compose recreates the owned container when its effective configuration changes.
The SQL master username is an initdb identity: changing it does not rename or
create a SQL role and fails authentication until restored or deliberately
administered outside startup. Startup never rotates the master password.

## SQL client administration

Default DBeaver/pgAdmin PostgreSQL connection:

| Setting | Value |
| --- | --- |
| Host | `127.0.0.1` |
| Published port | `6669` |
| Database | `ouroboros` (from provisioning) |
| Application schema | `ouroboros` (from provisioning) |
| SQL user | `ouroboros_master` (from operational config) |
| Password | The SQL master password entered interactively |
| Container-internal port | `5432` |

An empty published address means `127.0.0.1`; only loopback IPs are accepted.
The port must remain 6669. SQL master administration is distinct from application
super administration. SaaS users/integrations receive no SQL credentials.
This phase neither creates SQL tenant logins nor implements OAuth or API endpoints.

## Structural identity and naming

The provisioning registry stores canonical JSON plus SHA-256 of all validated
structural values and the full logical-to-physical table mapping. On an existing
installation startup compares these values and refuses differences before applying
SQL. Existing running services are checked before Compose recreation. Comment or
whitespace changes do not matter. No table rename, ID regeneration or schema
upgrade occurs when editing JSONC. Restore the applied configuration on mismatch.
Database-name changes are rejected against the existing container's initdb identity.
Schema changes are rejected against the registry in the existing schema.

Before any volume exists, an interactive prefix conflict lists logical tables and
allows correction of one unreserved table at a time. Saving changes only the value
span, retaining comments. Revalidation repeats until all prefixes are unique.
Noninteractive conflicts and conflicts after a volume exists fail without repair.
Confirmed AU/US/QA/FM prefixes cannot be reassigned. Prefixes contain 2-8 uppercase
ASCII letters. All names are validated, length-bounded ASCII SQL identifiers;
physical collisions are rejected, including collisions with fixed technical names.

Each vocabulary group has a singular `name`. Derived names substitute work,
platform and tag tokens, and activity in `watch_list_entry`/`watch_history`.
For example work=book, activity=read produces book, book_availability,
book_classification, book_tag, read_list_entry and read_history. There is no
activity table or activity prefix. Technical names remain fixed. Prefix keys
are stable logical names even under alternate vocabulary.

## Migrations and privileges

Historical `modules/database/sql/migrations/001` through `011` remain exact immutable
bytes and are NOT replayed in this track. This is an explicit new-installation
baseline `database-v1/001`, generated from `modules/database/model.py` and the fixed
functions in `modules/database/provision.py`. Its registry version is unique independently
of its friendly ID. The checksum covers the raw bytes of both implementation
files and generated table SQL; do not edit these files after deployment without
designing a new migration track. This delivery provides no upgrade from the old
public schema. Unregistered nonempty databases are rejected.

The initdb master is a trusted PostgreSQL administrator. `ouroboros_owner`
(NOLOGIN) owns the application schema, tables, sequences and functions; only the
master receives its membership. `ouroboros_runtime` is NOLOGIN, non-superuser,
cannot create databases/roles, and is not a member of the migration role. It is a
capability role reserved for a future trusted API broker, not a customer login.
There are no runtime login credentials in this delivery. Public database privileges
and public-schema CREATE are revoked; no app-schema CREATE is granted to runtime.
The master's database search_path is pg_catalog then the app schema. Startup and
functions use qualified references with a pg_catalog-only controlled search_path.
Functions have no PUBLIC execute defaults. Runtime receives explicit DML only on
ordinary business tables, SELECT on noncredential tables and sequence USAGE.
No ordinary credential hash access or DML on reserved plan/installation/audit state
is granted. Runtime cannot update/delete audit or version evidence, migrate,
disable triggers or grant itself owner privileges.

`super_administrator` is a protected singleton referencing the person's exact
API membership. A common role named super_administrator and common permission on
installation_plan are prohibited. Runtime cannot write the singleton or plan
tables. The only granted plan mutation function, `change_plan(text)`, rechecks
the active reserved holder, person and current link with row locks in the same
transaction, and verifies the mandatory Database/API bundle. Plan 1 starts with
both mandatory modules; modules/frontend/assistance are optional module records.

The future API must authenticate before setting transaction-local
ouroboros.actor_api_user and optional ouroboros.actor_app_user. These settings are
trusted broker context, NOT a SQL-client authentication mechanism. Never grant
runtime membership to tenant-controlled SQL users. The database verifies current
actor existence/activity and current person membership when context is supplied;
trusted direct SQL administration may omit actor context. Future API authorization
and user-creation-by-integration permission checks remain required at that boundary.
Allow/deny rules persist resource/action rules, with deny precedence reserved for
that future authorization service; this phase does not evaluate API policies.

## Common columns, ownership and deletion

Every application table, including relationships and evidence, has:

| Column pattern | Type and rule |
| --- | --- |
| sequence_<physical_table> | BIGINT GENERATED ALWAYS AS IDENTITY, positive, unique, immutable |
| prefix_<physical_table> | TEXT NOT NULL, immutable by fixed CHECK |
| id_<physical_table> | Generated stored TEXT primary key: prefix + positive sequence, at least base_quantity_digits digits |
| created_at | TIMESTAMPTZ NOT NULL, server-generated UTC instant, immutable |
| created_at_timezone | TEXT NOT NULL DEFAULT UTC, immutable source context |

IDs grow past the configured width without truncation; they are never rebuilt
or reused by startup. Catalog tables marked below additionally have immutable
fantasy_name_<table> technical metadata, distinct from personal_name and display_name.
All FK deletions are RESTRICT; there are no cascading deletions. All uniqueness,
FK and CHECK expressions below are authoritative SQL and use physical names.
Columns without NOT NULL are nullable. Common metadata is omitted from the per-table
SQL fragments below, which list every other column and table constraint.

app_user owns personal links, history, subscriptions and personal tags/categories.
Ownership is immutable. Composite keys enforce same-owner/session/work/platform
references, including availability belonging to the recorded work. Tag triggers
permit reuse/copy of shared tags but reject other users' private tags and crossing
personal relationship graphs. Tag visibility and work-tag visibility are independent.
Classification is installation-shared with an independent positive unique tier;
new NULL-tier inserts append under the list lock. No normal classification is seeded.
Future reorder operations must retain membership/actor/list/record locks, deferred
uniqueness and audit evidence for every shift, as in the existing developer contract.
External person references are unique per integration API identity and external ID.
Person/API membership end dates retain prior links; only current duplicate pairs
are prohibited. Deleting memberships, changing their original API identity/start
or reopening an ended membership is prohibited by a history trigger.
api_user may exist without a person. There is no service-account
table or routine-wide master application credential.

Every business mutation emits an immutable api_audit_log event and a record_version
entry in the SAME transaction through mandatory security-definer triggers. Versions
reference the event, resource, record ID, operation and monotonic per-record version;
they intentionally contain no row snapshots. Audit stores technical actor, optional
person and transaction ID. No request bodies, SQL values, personal text, tokens,
passwords or hashes are captured. Thus no recursive sensitive-body redaction is
needed here: complete payload omission is the boundary. Evidence FK failure rolls
back business changes. Masters remain trusted and can alter the database; this is
not master-resistant tamper-proof storage or a blanket OWASP compliance claim.

Subscription charges snapshot amount, currency and paid access interval independently
of current plan/promotion price. Charge rows are append-only: updates/deletes are
rejected by the evidence trigger. Current subscription access_until is explicit.
Reminder records are schema only; no scheduler or sending exists. Watchlist counts
by platform are derived by joining entries to availability, without counters.
Submissions/matches and work verification state are persisted schema only; no
review automation or human-review UI is included.

Security design references consulted: [OWASP ASVS](https://owasp.org/projects/asvs),
[Authentication](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html),
[Authorization](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html),
[Password Storage](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html),
[Logging](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html),
[Input Validation](https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html),
[Error Handling](https://cheatsheetseries.owasp.org/cheatsheets/Error_Handling_Cheat_Sheet.html).

## Configuration examples

Root provisioning.example.jsonc:

```jsonc
'''
    sections = [header, configuration, '\n```\n\nDatabase config.example.jsonc:\n\n```jsonc\n',
                (root/'modules/database/config.example.jsonc').read_text(encoding='utf-8'), '\n```\n\n## Tables and columns\n\n']
    names = mapping(document)
    for logical in ORDER:
        sections.append(f"### {names[logical]} — {TABLES[logical]}\n\n")
        sections.append(('Derived' if logical in DERIVED else 'Fixed technical')+' name. ')
        sections.append(('Protected runtime state; no ordinary DML. ' if logical in PROTECTED else 'Business state. '))
        if logical in CATALOGUE:
            sections.append('Includes fantasy_name_'+names[logical]+'. ')
        sections.append('All referenced records restrict deletion.\n\n```sql\n'+render(MODEL[logical],document)+'\n```\n\n')
    sections.append('''## Verification

Run configuration tests without Docker:

```powershell
.\\.venv\\Scripts\\python.exe -m unittest discover -s modules/database/tests -p test_settings.py -v
```

Run real PostgreSQL verification in isolated projects/volumes (owner-approved QA
ports 2424 and 4242, never 6669) with fresh random credentials:

```powershell
.\\.venv\\Scripts\\python.exe -m unittest discover -s modules/database/tests -p test_postgres.py -v
```

Only exact test-allocated resources are cleaned up. See DATABASE_QA.md for actual
execution results and limitations. The real normal terminal password prompts and
SQL-client GUI connection require the operator; automated SQL authentication
does not establish DBeaver/pgAdmin GUI behavior.
''')
    (root/'docs/DATABASE.md').write_text(''.join(sections),encoding='utf-8')


if __name__ == '__main__':
    write_reference(Path(__file__).resolve().parents[2])
