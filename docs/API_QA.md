# API v1 verification record

The current modules relocation and consolidated suite results are recorded in
[LAYOUT_QA.md](LAYOUT_QA.md). Current commands use `qa/run.py` and each module's
`qa/run.py`. The dated records below describe their original verification runs.

The subsequent [English presentation and live prompt fix](ENGLISH_PRESENTATION.md)
was deployed to the normal API on 2026-11-14. It independently removes the native
Basic login challenge and updates Swagger presentation without requiring the
pending human-alias migration. Earlier pending-activation statements below refer
to that broader migration, not to the now-deployed browser prompt correction.

## Interrupted human-login/Swagger work resumed, 2026-11-14

Follow-up on the browser login prompt: confirmed the running API belongs to
`C:\Dev\Ouroboros` through its Compose labels and still uses the earlier image.
Updated Swagger labels to App User/API User, clarified the credential choices,
and aligned English Database enrollment prompts and documentation. The source
already avoids Basic challenges for rejected token requests; the native browser
dialog shown in the report belongs to the older deployed version.
Repeated API integration: 14 passed, two skipped for occupied normal port 6969.
Swagger DOM: one passed. Masked password input: eight passed. API image build
passed. Normal activation is pending the operator's interactive
`start.py --api-migrate`, followed by `start.py --with-api`; the running service
was preserved. No stored normal credential was extracted. Direct Windows curl
verification was blocked by local-certificate revocation checking and is not
claimed as successful. Official OWASP Authentication/Authorization guidance and
ASVS were consulted; this is not a blanket compliance claim.

The existing module relocation, human alias migrations, credential-preserving
backfill, shared alias throttling and same-origin Swagger authorization panel
were retained. Review found six new tests missing from the QA catalogue; they
are now mapped to scenario 21.1 and the manual plan has been regenerated.
The API guide and developer rules now describe the implemented login flow.

Verification repeated on this date:

- `python modules/api/qa/run.py --pattern test_service.py`: 16 tests,
  14 passed and two skipped because the normal service occupies port 6969.
  Real mutation tests used only the owned disposable PostgreSQL fixture on 2424.
- `python modules/api/qa/run.py --pattern test_swagger_ui.py`: one passed.
  The shipped Swagger bundle and plugin ran in JSDOM with synthetic credentials,
  covering human sign-in, token paste, integration authorization and repeated
  protected requests. This is not physical browser or normal-account evidence.
- `python qa/run.py --suite central`: 63 tests, 45 passed, 18 skipped,
  no failures/errors after the catalogue repair.
- QA plan generation and `git diff --check`: passed.

Local output is in `reports/resume_swagger_checks.txt`,
`reports/resume_swagger_dom.txt` and `reports/resume_central_checks.txt`.
The initial sandboxed integration attempt could not access Docker; the repeated
authorized run above completed successfully. PowerShell's redirected unittest
stderr may report NativeCommandError even for an OK test result; the suite
summaries above are the actual unittest results.

Normal-installation upgrade/activation and a login using the operator's existing
interactive credentials remain unverified in this resumption. No normal password
was retrieved or reset, no normal service was restarted and no normal business
data was mutated. The previously documented Frontend specification compilation
failure was not changed or represented as passing. No commit or push was made.

## HTTPS verification on 2026-11-13

The existing API implementation was extended with direct TLS on port 6969.
This run executed the following commands.

- `docker build -f modules/api/Service.Dockerfile -t ouroboros-api-v1:verification .`
  completed successfully.
- `.\.venv\Scripts\python.exe -m unittest discover -s modules/api/qa -v` passed
  all 19 tests. The real PostgreSQL fixture on approved disposable port 2424
  inspected the schema and privileges, applied the existing additive API
  migration and exercised authentication, revocation, ownership, roles,
  deny/allow rules, plan auditing and PUT/PATCH behavior.
- A read-only API container on approved port 6969 served health, Swagger HTML,
  OpenAPI and Client Credentials token issuance over certificate-verified HTTPS.
  The client explicitly trusted the disposable certificate and verified its
  hostname. Plain HTTP requests to health, Swagger, OpenAPI and the token route
  failed. TLS validation was never disabled.
- Containers with missing certificate or missing key exited unsuccessfully with
  the corrective TLS diagnostic before SQL access. Host startup with missing TLS
  was also verified to stop before Docker/database discovery. Certificate/key
  mismatch, invalid key and incorrect SAN hostname failed preflight. Valid
  localhost and 127.0.0.1 names completed the TLS handshake.
- The nine module architecture tests and eight masked-password tests passed.
  `start.py --database-only --check`, `start.py --with-api --check` and
  `python -S start.py --help` passed. The real disposable Database-only startup
  also ran successfully as part of the integration fixture.
- Scoped `git diff --check` passed.
- `scripts/run_checks.py` returned failure at its existing preparation/catalogue
  gate, with 82 blocked automated scenarios and four manual scenarios. No mapped
  tests executed through that runner. Its reports are in ignored `reports/`.

The API test fixture removed its exact owned PostgreSQL project/volume and API
container. Normal data, Database baseline sources and applied migrations were
preserved. The ignored local API config now has TLS file references. No local
trusted development certificate was installed for the normal service. Normal
activation requires certificate preparation from API.md and, if still pending,
the existing interactive API migration step. Physical browser interaction with
Swagger Authorize remains unverified. Automated Swagger HTML/OpenAPI/token
checks establish the HTTPS transport and published OAuth configuration.

Files changed for HTTPS are `.dockerignore`, `modules/api/config.example.jsonc`, local
`modules/api/config.jsonc`, `modules/api/compose.yaml`, `modules/api/service/config.py`,
`modules/api/service/tls.py`, `modules/api/service/launcher.py`, `modules/api/service/runtime.py`,
`modules/api/service/app.py`, `modules/api/modules/api/qa/test_config.py`, `modules/api/modules/api/qa/test_tls.py`,
`modules/api/modules/api/qa/test_service.py`, `docs/API.md`, this record and `NEXTGENERATION.md`.
README changes and other pre-existing workspace edits were preserved.

## Earlier API verification

Date: 2026-11-12. No staging, commit, push or merge was performed.

## Authenticated live inspection

The operator ran `start.py --api-inspect` in the normal PowerShell terminal using
the existing masked SQL master credential and supplied this result:

```text
Authenticated live schema and runtime privileges verified. Registered migrations: database-v1/001
```

The implementation inspected the real registry/structural identity, baseline
checksum, API-relevant columns, enabled audit/metadata triggers and runtime role
flags. The saved master secret was not extracted. Initial connection failures
were classified through safe diagnostics; private libpq messages and credentials
were not emitted. The normal API migration is a separate explicitly requested
terminal operation, not a schema reset or baseline replay.

## Automated execution

- `python -m unittest discover -s modules/api/qa -v`: **14 passed** (four configuration
  and ten real PostgreSQL/HTTP integration tests).
- `docker build -f modules/api/Service.Dockerfile -t ouroboros-api-v1:verification .`:
  **passed**, including dependency installation/packaging and the exact Database
  baseline sources/migration file needed for runtime contract verification.
- The integration suite started the real built API container, connected it over
  the isolated PostgreSQL network with `ouroboros_api_login`, and fetched
  `/health` plus `/openapi.json` on the approved free API port **6969**. It did not
  mount a master secret, start Frontend/Assistance, or select an alternate port.
- `python -m unittest discover -s modules/database/qa -p test_password_input.py -v`:
  **8 passed**, preserving masked password/confirmation/backspace and safe hidden
  fallback behavior.
- `python -m unittest discover -s tests -p test_module_architecture.py -v`:
  **9 passed**, including site-package-free launcher help and legacy module
  regression checks.
- `python -S start.py --help`, `start.py --database-only --check` and
  `start.py --with-api --check`: **passed**. Unit checks also verify that
  `--api-migrate --check` does not read credentials or mutate SQL/Docker.
- Scoped `git diff --check`: passed. Historical migration and Database baseline
  source files were not edited for this delivery.

The real integration suite covered:

1. Runtime login/non-superuser privileges, valid tokens, missing authentication,
   expiration and credential-version/credential revocation. The bootstrap human
   password cannot authenticate the Client Credentials grant.
2. Manager creating manager/user; rejection of administrator/reserved profiles,
   self-promotion, existing-account permission administration, and grants beyond
   the manager's effective authority.
3. Personal ownership before list counts, unowned GET/PATCH rejection, owner
   spoofing rejection, an unlinked integration denied personal access, and
   `user_work:update` not granting `work:update`.
4. Complete PUT replacement and reset of omitted optional fields, required-field
   rejection, partial PATCH preservation, nullable clearing and extra protected
   owner/role/plan/ID/creation field rejection.
5. Administrator denied plan change; the existing reserved human holder changing
   a disposable existing plan with same-transaction technical/person audit and
   record-version linkage. Generic protected-table endpoints remain absent.
6. Deny overriding allow, allow failing to create a missing permission, and
   administrative removal of an explicit deny rule.
7. JSONC strict keys/types/duplicates, persisted/operator bounds, configuration
   check modes, bounded atomic batches, duplicate request JSON rejection and
   OpenAPI Client Credentials/PATCH definitions without credential-table CRUD.
8. Actual read-only API container with restricted secrets/network; public health
   and English OpenAPI availability.
9. Account deactivation revoking current tokens, independent classification
   append/insert/move behavior and rejection/rollback of an invalid creation batch.
10. Administrative explicit-permission replacement revoking old tokens, renewed
    tokens receiving only current grants, and PUBLIC function execution removed.

All mutable fixtures used UUID-owned PostgreSQL infrastructure on explicit QA
port **2424**, fresh random credentials and a new volume. The fixture first
interrupted enrollment inside hashing, verified rollback, resumed normal bootstrap
and reused the Database baseline. Tests inspect the actual schema before mounting
API endpoints. Cleanup removes only the exact QA project/volume and API container
allocated by that run. No normal catalogue/classification/account data was used
as a mutation fixture.

## Existing full-check limitation

`python scripts/run_checks.py` was executed. Its pre-existing catalogue
consistency gate still blocks the run because three speech tests are unmapped in
qa/scenarios.json. It reported 82 blocked automated scenarios and four manual
scenarios, with zero mapped tests executed. This is not a green full-project QA
approval. The unrelated speech/catalogue mapping and Frontend/Assistance sources
were not modified by this API delivery.

Swagger/OpenAPI HTTP/schema availability and security tests are automated;
physical browser interaction with Swagger Authorize is not claimed. Existing
normal data was not mutated for QA. The prior working tree already contained
unrelated README/Frontend/Assistance changes; those were preserved, not authored
or reverted by this delivery.

## Normal service activation

Authenticated inspection is complete. Applying `api-v1/001` in the normal
installation and starting its API require the operator's interactive
`start.py --api-migrate` step, followed by `start.py --with-api`. Final normal
activation evidence is recorded separately once those operations complete.
