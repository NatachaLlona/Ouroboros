# Canonical folder and configuration migration QA

Recorded on 2026-11-04. This record covers the source-layout/configuration task, separately from the earlier service extraction.

## Executed

- Moved backend code/runtime/dependencies/utilities into api/, model execution into assistance/, frontend image/proxy tooling into the existing frontend/, and SQL resources into database/. Removed the retired root app/ and modules/ packages; no runtime compatibility copies remain.
- Compared all five canonical private JSON documents against the previously effective configuration under the documented ownership split. Values matched; only ownership/path references changed. Original private JSON snapshots remain in the protected, inactive `.secrets/layout-config-before-standardization.zip`. The provider file moved to assistance/.env without displaying its contents.
- Compared SHA-256 for all 11 SQL migration files before/after filesystem moves. Every byte hash matched. Updated the attributes rule to database/sql/migrations/*.sql -text. No migration or database schema was added or changed.
- Built all three application images through start.py using the new Dockerfiles/contexts. Existing PostgreSQL image/volume were retained. Angular production build succeeded; the approximately 404 kB initial-bundle warning against the 350 kB warning budget remains.
- Ran the general runner with --unit-only: 132 tests PASS, zero FAIL, 67 SKIP. Its overall nonzero status correctly records incomplete historical integration/manual scenarios; it is not full QA approval.
- Ran 16 scoped Angular recording/form-assistant/runtime-config tests successfully after renaming the TypeScript configuration loader and updating imports.
- Ran disposable tmpfs PostgreSQL integration: immutable migration replay, account setup and atomic split preference persistence, proxy/static assets, protected navigation, login HttpOnly, CSRF CRUD, bearer APIs, Swagger and speech options passed. No host ports were published by QA.
- Changed disposable frontend presentation JSON and restarted its container: new name/color were delivered with the same compiled build identity, without Angular recompilation.
- Ran one real GPT-5.4 structured suggestion and real local transcription using synthetic disposable speech through the reorganized frontend/API/assistance stack. Provider key, reply and transcript contents were not printed. No normal business record was used or saved by the suggestion.
- Stopped only disposable frontend/assistance containers and confirmed that API/Swagger/login/catalogue continued to work, with controlled assistance unavailability.
- The owner confirmed a new interactive python start.py startup using the existing normal credentials. Independently inspected all four normal services as healthy, verified canonical API/database config mounts, the existing ouroboros_postgres_data volume, original 6669/6969 bindings, and six public HTTP routes returning 200. No stored database password was extracted to repeat normal migration queries.
- Module scripts and launcher resolve repository paths from their file locations. The launcher --help works without host site-packages, and canonical configuration/Compose checks pass. Private config/provider/archive paths remain ignored by Git and excluded from image build contexts.

Two wiring issues found during disposable QA were corrected before completion: one residual account-query path and CRLF in the relocated Linux frontend entrypoint. Neither required SQL changes or normal data mutations.

## Pending and scope

- Full legacy integration suite, GitHub workflow execution and manual browser/physical microphone cases were not represented as executed. The workflow now builds module images and runs the disposable module check; its remote execution remains pending.
- Browser rendering and actual user-driven form interaction remain manual. HTTP/static checks and component tests do not establish those visual behaviors.
- The normal applied migration registry was validated by the owner-authenticated startup; automated mutation QA remained strictly separate from the normal database.

No staging, commit, push or merge was performed. Persistent model files, database volume, protected shared secrets and normal business records were preserved.
