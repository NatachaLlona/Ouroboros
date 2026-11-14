# Shared form-assistant QA - 2026-11-05

## Automated evidence

- Scoped Python suite: 45 checks passed for assistant validation/transport/endpoints, controlled behavior, module boundaries, existing transcription and QA traceability.
- Scoped Angular suite: 24 checks passed across form assistant, existing audio controls and public configuration. Includes actual application receipts, partial application reporting, mandatory order/conditional status, generated technical-name behavior, optional refusal, description application, stale/manual protection, draft isolation and relative-position accept/cancel flows.
- `scripts/run_checks.py --unit-only`: 147 unit checks passed, zero failed, 67 skipped. The runner exits nonzero intentionally because full integration/manual scenario approval is incomplete (55 skipped scenarios, eight dependent scenarios blocked, four manual).
- `start.py --build-only`: API, frontend and assistance images built. Angular production bundle succeeded; the approximately 408 kB initial bundle retains the existing 350 kB warning threshold, below the hard failure budget.
- QA scenario 20.1, generated QA plan and test selectors were updated. Controlled fixtures/mock responses do not prove unrestricted real-model language understanding.

## Real provider and disposable integration

The isolated `scripts/verify_modules.py --live-assistant` check passed a real GPT-5.4 structured suggestion after correcting internal GET transport. It also passed modules/frontend/proxy/static assets, protected navigation, HttpOnly authentication, CSRF CRUD using disposable records, bearer reads, existing speech options, runtime public configuration reload without rebuild, and API availability without modules/frontend/assistance. No normal business data, credentials or volumes were modified.

The first isolated run exposed that the nested GET used the remote browser IP without its verified proxy context. The in-process transport now uses loopback while retaining the original session/bearer, origin and normal GET authorization; no privileged credential is substituted. A regression test covers remote-source transport and final permission denial.

The expanded real-model probe also passed: quoted fantasy name plus explicit numeric tier were extracted together, an actual case-insensitive "first of amei" lookup returned the first real classification, position was withheld until confirmation, and confirmation filled tier 1 without creating a business record. Earlier probes did not match the expected numeric position; the global instructions were clarified to distinguish explicit numeric positions from relative references. Those earlier runs are not counted as passing. All fixtures lived only in owned tmpfs containers; response contents were omitted. These selected real examples do not prove every possible wording.

## Pending/manual evidence

- Browser visual interaction, keyboard/focus restoration and existing save dialogs after assistant application have not been manually exercised in this task.
- The controlled tests cover optional refusal, descriptions, before/after/between, read failures and changed-position reconfirmation; do not infer real-model coverage of every wording from those mocks.
- No real microphone/transcription regression was performed or required for this change; its implementation is unchanged and existing scoped audio/transcription tests passed.
- Normal interactive startup/migration verification is not repeated using stored credentials. Built images become active through the existing `python start.py` interactive startup.

No staging, commit, push or merge was performed.

## Assistant identity separation follow-up

The subsequent responsibility split introduces distinct instruction files and stable `assistant_1`/`assistant_2` identifiers. Only common safety, authorization and error rules are shared. Assistant 1 has a separate reserved site context, no active tools and disabled inference; no new navigation/search/filter functionality was implemented. Form context, GET tools, pending position plans and history remain owned by Assistant 2. New history is tagged, foreign identity tags are rejected, and switching to general presentation hides form conversation and invalidates in-flight application without erasing that form's history.

Executed after this split: 48 scoped Python tests passed (including disabled-provider execution, cross-identity request/history rejection, policy separation and existing form/transcription/module/QA regressions), 25 scoped Angular tests passed (including switching to the general assistant while a form response is pending), and all three application images built through `start.py --build-only`. The existing frontend bundle warning remains nonfatal. QA catalogue/plan were regenerated and checked. No new real-model call or manual browser check was performed for this split; previous real-provider evidence above belongs to the preceding form-policy change.
