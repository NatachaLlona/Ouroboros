# Canonical folder and configuration migration QA

## Modules relocation and HTTPS verification, 2026-11-13

The active layout is `modules/{api,assistance,database,frontend}`. Postman lives
under `modules/api/postman`. Root startup, provisioning and general orchestration
retain their locations. `modules/database/config.jsonc` is the operational
database configuration. The previous Basic startup change introduced 26969 in
API configuration, validation and Compose. This task restored 6969 throughout
the active configuration, OpenAPI, Postman and current execution instructions.

The existing `ouroboros_installation_v1` volume was reused. Its recorded creation
time is 2026-11-13T08:21:18Z. Normal startup reused the registered baseline and
existing operator. The relocation performed no reset. Compared with the
pre-move byte inventory, README.md, database/model.py, database/provision.py and
all 31 SQL files have identical SHA-256 hashes in their new locations.

The normal services `ouroboros-postgresql-1` and `ouroboros-api-1` are healthy in
project `ouroboros`. Their internal/published ports remain 5432/6669 and
8000/6969. Swagger returns 200 using the normal Windows certificate trust store.
OpenAPI publishes `https://localhost:6969` and the HTTPS `/oauth/token` URL.
Plain HTTP cannot access Swagger. The former 26969 port has no listener.
`start.py --database-only` reused the existing installation successfully.
Absolute-path invocation from another directory and site-package-free help
were also verified. Frontend and Assistance services were not started.

Tests now have one owner in central `qa/` or a module's `qa/` directory.
The consolidated command was
`.\.venv-speech\Scripts\python.exe qa/run.py --suite all`.

| Suite | Tests | Passed | Skipped | Failures/errors |
| --- | --- | --- | --- | --- |
| Central | 63 | 45 | 18 | 0 |
| Database | 44 | 43 | 1 | 0 |
| API | 127 | 77 | 50 | 0 |
| Assistance | 39 | 39 | 0 | 0 |
| Frontend | Compilation failed | — | — | Existing unmatched test contracts |

The Frontend specifications reference `paginationItems`, `clampPaginationPage`,
`Pagination.request`, `pendingTechnicalName` and `pendingInsertionTier`, which
were already absent from the implementation before this relocation. Those
specifications were retained and their failure is reported. The production
Frontend build completed with exit code 0 and the existing bundle-budget warning.
The overall QA command therefore returned failure. The report files are
`reports/summary.md`, `reports/results.json` and `reports/junit.xml`, with local
execution detail in `reports/layout_all.txt`.

The two API container smoke tests skipped their fixed port because the normal
installation owns 6969. Other historical destructive integration scenarios
remain opt-in. PostgreSQL mutation fixtures used only their disposable QA
projects and approved QA ports. Preflight, Python compilation and diff whitespace
checks passed. Remote GitHub workflow execution was not performed.

The interrupted human-login and Swagger follow-up was reviewed on 2026-11-14;
see [the resumed verification record](API_QA.md). Its API/DOM tests and central
QA pass, with documented skips. Normal-installation human authentication and an authenticated query through
Swagger remain pending. The operator reported an error, and the exact failing
operation/status is awaited. The browser automation host is unavailable.
No normal credential was recovered or replaced to bypass that dependency.

## Earlier layout verification record

Recorded on 2026-11-04. This record covers the source-layout/configuration task, separately from the earlier service extraction.

## Executed

- Moved backend code/runtime/dependencies/utilities into modules/api/, model execution into modules/assistance/, frontend image/proxy tooling into the existing modules/frontend/, and SQL resources into modules/database/. Removed the retired root app/ and modules/ packages; no runtime compatibility copies remain.
- Compared all five canonical private JSON documents against the previously effective configuration under the documented ownership split. Values matched; only ownership/path references changed. Original private JSON snapshots remain in the protected, inactive `.secrets/layout-config-before-standardization.zip`. The provider file moved to modules/assistance/.env without displaying its contents.
- Compared SHA-256 for all 11 SQL migration files before/after filesystem moves. Every byte hash matched. Updated the attributes rule to modules/database/sql/migrations/*.sql -text. No migration or database schema was added or changed.
- Built all three application images through start.py using the new Dockerfiles/contexts. Existing PostgreSQL image/volume were retained. Angular production build succeeded; the approximately 404 kB initial-bundle warning against the 350 kB warning budget remains.
- Ran the general runner with --unit-only: 132 tests PASS, zero FAIL, 67 SKIP. Its overall nonzero status correctly records incomplete historical integration/manual scenarios; it is not full QA approval.
- Ran 16 scoped Angular recording/form-assistant/runtime-config tests successfully after renaming the TypeScript configuration loader and updating imports.
- Ran disposable tmpfs PostgreSQL integration: immutable migration replay, account setup and atomic split preference persistence, proxy/static assets, protected navigation, login HttpOnly, CSRF CRUD, bearer APIs, Swagger and speech options passed. No host ports were published by QA.
- Changed disposable frontend presentation JSON and restarted its container: new name/color were delivered with the same compiled build identity, without Angular recompilation.
- Ran one real GPT-5.4 structured suggestion and real local transcription using synthetic disposable speech through the reorganized modules/frontend/API/assistance stack. Provider key, reply and transcript contents were not printed. No normal business record was used or saved by the suggestion.
- Stopped only disposable modules/frontend/assistance containers and confirmed that API/Swagger/login/catalogue continued to work, with controlled assistance unavailability.
- The owner confirmed a new interactive python start.py startup using the existing normal credentials. Independently inspected all four normal services as healthy, verified canonical API/database config mounts, the existing ouroboros_postgres_data volume, original 6669/6969 bindings, and six public HTTP routes returning 200. No stored database password was extracted to repeat normal migration queries.
- Module scripts and launcher resolve repository paths from their file locations. The launcher --help works without host site-packages, and canonical configuration/Compose checks pass. Private config/provider/archive paths remain ignored by Git and excluded from image build contexts.

Two wiring issues found during disposable QA were corrected before completion: one residual account-query path and CRLF in the relocated Linux frontend entrypoint. Neither required SQL changes or normal data mutations.

## Pending and scope

- Full legacy integration suite, GitHub workflow execution and manual browser/physical microphone cases were not represented as executed. The workflow now builds module images and runs the disposable module check; its remote execution remains pending.
- Browser rendering and actual user-driven form interaction remain manual. HTTP/static checks and component tests do not establish those visual behaviors.
- The normal applied migration registry was validated by the owner-authenticated startup; automated mutation QA remained strictly separate from the normal database.

No staging, commit, push or merge was performed. Persistent model files, database volume, protected shared secrets and normal business records were preserved.
