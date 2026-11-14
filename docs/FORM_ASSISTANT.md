# Shared form-assistant behavior

Assistant 2 uses the form policy in `modules/assistance/assistant_2_instructions.py`. `modules/assistance/instructions.py` selects exactly one identity policy and composes it with common security rules. Identity, greeting and colors still come from the existing public frontend configuration. Inference remains exclusively `gpt-5.4` in the assistance service; this change does not touch audio/transcription, business save logic or database migrations.

## Explicit activation and context

### Assistant responsibility boundaries

Stable internal identities are `assistant_1` (general site assistance) and `assistant_2` (registration/edit forms), declared in `shared/assistant_identity.py` and the frontend identity contract. Public names, greetings and colors remain unchanged and never select permissions or prompts.

Assistant 1's reserved policy is `modules/assistance/assistant_1_instructions.py`: general navigation and finding information, with search and complex-filter interpretation reserved for a later phase. Its profile has no active tools and inference is disabled. No intelligent navigation, assisted search or filter execution is introduced. No form draft or form conversation is sent to this identity.

Assistant 2's existing form rules stay in `modules/assistance/assistant_2_instructions.py`. Only safety, authorization, secret handling, untrusted-data treatment and error rules are shared through `modules/assistance/common_instructions.py`. Schema preparation belongs separately to `modules/assistance/structured_output.py`, not to either role's prompt. `ASSISTANT_POLICIES` declares distinct context/tool scopes; it never falls back between identities.

The existing form endpoint and internal suggestion envelope accept only `assistant_2`. Tagged history from another identity is rejected. For compatibility, missing identity on older requests/messages means Assistant 2 only on this dedicated form endpoint; it never dispatches to Assistant 1. New frontend requests and conversation entries explicitly carry `assistant_2`. Form history remains owned by its form conversation; switching to the decorative general assistant hides it and aborts pending form responses without clearing that draft's conversation. The general assistant has no active conversation transport in this phase. Names/configuration files and audio/transcription are unchanged.

`shared/form_adapters.py` registers only the currently enabled work-classification integration. Its visual order is Display Name, conditionally visible/generated Nome Tecnico, Descricao, Posicao. Validation metadata comes from the existing creation schema, and runtime context includes mode, values, automatic technical generation, automatic append, description grapheme limit and actual maximum tier. `Registration.classificationAssistant` provides frontend field status using existing form definitions, technical generation and description validation. Other registration forms and embedded Tag/category dialogs retain their existing local conversation; they are not silently enabled for AI.

Future enabled forms must supply an adapter and frontend binding, reuse this policy and existing validation/relationship contracts, and declare their allowed reads explicitly. Do not copy prompts, invent fields or enable incomplete bindings.

The model extracts all clear fields in the entire message. It cannot set the technical field without an explicit technical-name request. Existing descriptions are protected unless their change is requested; an empty description can receive a short faithful suggestion when the account contains enough information. Unicode description validation remains authoritative. Names alone do not justify invented descriptive facts.

## Application and conversation

`modules/frontend/src/app/shared/form-assistant.ts` builds acknowledgments from the form state **after** application. A model's predicted success is not an application receipt. Applied and pending proposals are identified separately. Existing manual replacement confirmation, fresh-value checks, form binding and draft epoch protect manual edits and prevent delayed/cross-form application. Suggestion application never invokes business save.

Required questions use current frontend validity in visual order, including conditional requirements and valid defaults. Generated technical names are never spontaneously requested; an invalid automatic suggestion gets a form-review notice while normal validation remains in force. Optional fields are offered together once per conversation, with refusal remembered in that form's in-memory draft conversation. Resetting that draft resets the optional-offer state. Other drafts remain independent.

## Allowed GET tools

`modules/api/form_assistant_reads.py` is the only model-read adapter. Structured requests accept an allowlisted resource and literal search fragment, never URLs, SQL, headers or arbitrary methods. Currently the only enabled resource is `work_classifications`. It uses the existing GET collection and individual routes through in-process ASGI with the original cookie/bearer identity and existing current-account authorization. The transport is loopback because it is in-process, not a new browser network connection. Original origin/fetch-site checks are preserved. No service token or privileged identity is substituted for the user.

Search uses the existing case-insensitive `display_name_work_classifications` ILIKE filter with escaped literal fragments, real page/page_size and tier ascending. It follows subsequent pages, rejects inconsistent/incomplete results and duplicate identities, and never treats an incomplete read as complete. Bounded resources: at most three distinct model-requested searches, three inference rounds, 100 pages per search (50 rows each), and an 80-second API turn deadline beneath the existing browser deadline. Oversized/internal transport or read failures fail visibly without applying guesses. A permission denial is final; no retry under another identity. Catalogue response text is data, never developer instructions.

`modules/api/form_assistant_flow.py` orchestrates these reads and validates proposals. Similarities are reported without equating names or blocking creation; real API uniqueness rules still apply. A failed read applies no proposals from that turn.

## Relative position confirmation

The model supplies typed before/after/between references; it does not resolve positions from memory. An explicit "first of" reference chooses the first actual tier-ordered substring match. Unique references with multiple matches, missing matches and nonconsecutive between anchors require clarification. The current record cannot be its own anchor; editing accounts for removing its old position before insertion.

The API returns actual names, current positions and the insertion/reordering effect in a confirmation. Short-lived random confirmation tokens are held only in bounded API memory, tied to account, mode and record, consumed once and valid for five minutes. Cancellation changes no tier. Confirmation rereads the references and current order; a changed target, anchor or effect requires a fresh confirmation. Only the field is filled, never saved. Existing technical-name and order-change save dialogs remain authoritative. API restart expires pending plans safely.

## Examples and verification

- "Chama Amei demais, coloca na posicao 3": propose both real fields in one turn.
- "Primeiro dos amei": case-insensitive filtered GET, tier ascending, actual first anchor, confirmation, reread, then fill.
- "Entre A e B": clarify if missing, ambiguous or not consecutive in the requested order.
- "Nao quero preencher os opcionais": remember refusal for this form conversation.
- An existing description or a manual edit made during inference remains protected.

Controlled behavior tests: `modules/assistance/qa/test_form_assistant_behavior.py`, `modules/assistance/qa/test_form_assistant.py` and `modules/frontend/src/app/shared/form-assistant.spec.ts`. They cover proposal transport, multiple fields, actual receipts, required order, defaults/conditions, optional refusal, technical protection, description preservation, paginated reads, permissions/failures, relative ambiguity/reconfirmation, edit rank math, cancellation, stale responses and isolation. These tests validate controlled outputs and mocks; they do not prove arbitrary natural-language model behavior.

Run `python scripts/verify_modules.py --live-assistant` for separate real-model checks using owned tmpfs containers, disposable records/accounts, no published ports and no normal-data writes. It checks a basic suggestion, multi-field extraction and actual case-insensitive relative lookup/confirmation, plus existing modular smoke checks. Provider calls incur normal configured API usage. Response contents and secrets are omitted. See [QA evidence](FORM_ASSISTANT_QA.md).

Implementation references: [OpenAI structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs), [OWASP authorization](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html) and [OWASP SSRF prevention](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html). These describe the source contracts, not a blanket compliance claim.
