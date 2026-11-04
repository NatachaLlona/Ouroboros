# Four-module QA record

Recorded on 2026-11-04. Normal database records, credentials and applied SQL files were not changed by the automated QA. This is scoped evidence, not blanket QA approval.

## Executed

- Built `ouroboros-api`, `ouroboros-assistance` and `ouroboros-frontend` from the new Dockerfiles. PostgreSQL retains its existing official image. Angular compiled successfully; its existing initial-bundle warning remains (approximately 404 kB against a 350 kB warning budget).
- Ran `start.py --check` with the existing Python 3.15 environment. The launcher uses no installed application dependencies; application processes use Python 3.12 inside Docker.
- Loaded the existing faster-whisper model inside a network-disabled Linux container, with the host cache mounted read-only. No model download or personal recording was required.
- Imported Base/API without frontend files, assistance, or installed faster-whisper dependencies in a network-disabled container.
- Sent disposable Windows-synthesized speech through the frontend proxy and Base/API to the real assistance container. A complete transcription was returned; neither audio nor transcript content was logged. The sample was not a personal recording.
- A single live GPT-5.4 structured suggestion passed through the isolated frontend/API/assistance stack with disposable form/account data. No form was saved by the suggestion and no provider key or response content was printed. Mocked provider tests also remain in place.
- Changed the disposable frontend name/color, restarted only its frontend container, and verified updated runtime JSON/CSS with the same compiled build ID: no Angular rebuild.
- Ran the owned tmpfs stack using `scripts/verify_modules.py`: frontend asset/config/CSS delivery, protected navigation/login redirect, HttpOnly session login, CSRF-authorized classification creation/listing/deletion, Swagger/OpenAPI, bearer API and authenticated speech options passed.
- Stopped only the disposable frontend/assistance services and checked API/Swagger/login/catalogue directly inside its API container. Catalogue remained available; assistant and transcription returned controlled unavailable errors.
- Targeted backend form-assistant, speech, startup/cleanup, database configuration and infrastructure tests passed. The 16 scoped Angular recording/form-assistant/runtime-configuration tests passed. Delegation tests cover body/operation binding, expiry, replay, unsigned role claims and controlled failures; orchestration/proxy tests cover optional-service failure and verified forwarding.

The old local Python Ouroboros listener was identified and left for the owner to stop. The owner subsequently confirmed successful interactive `python start.py` preparation. All four normal containers were inspected as healthy; `/`, `/health`, `/docs`, `/openapi.json`, public JSON and theme CSS returned HTTP 200. The existing volume remained `ouroboros_postgres_data`. An internal-only PostgreSQL network attachment suppressed effective port publication despite the configured binding; a separate PostgreSQL-only host-access bridge restored the original 127.0.0.1:6669 binding without SQL, migration changes or volume replacement. Disposable tests used only container networks and published no additional port.

## Pending and scope limits

- Browser rendering/navigation, actual form interactions, visual assistant presentation and physical microphone capture remain manual. Browser access failed because its access host was unavailable; the Windows fallback controller also reported an unavailable native pipe. Internal HTTP assertions do not substitute for these checks.
- The general QA runner was executed with `--unit-only`: 132 PASS, zero FAIL and 67 skipped test cases at the recorded run. Its overall exit code correctly remains nonzero because required integration/manual scenarios are incomplete. The disposable module integration above is separate evidence; it does not turn the entire historical suite into a full approval. Consult current sanitized `reports/` output.

No staging, commit, push or merge was performed. No migration, schema, catalogue rule or normal record was modified for QA.
