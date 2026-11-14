# English presentation and live authentication fix

The project owner requested English throughout the product on 2026-11-14.
Frontend headings, navigation, fields, tooltips, validation, session messages,
accessibility labels, assistant greetings and deterministic replies are English.
Assistant 2 is instructed to reply in English while preserving arbitrary input.
Database enrollment and API/Swagger presentation distinguish App User, API User,
integration Client ID and SQL administration credentials.

Public assistant settings use `assistant_name`, `assistant_2_name`,
`assistant_greeting` and `assistant_2_greeting`. The versioned example, local
public configuration, generators, frontend consumers and related tests were
updated together. Existing artwork and configured color values were preserved.
Canonical frontend routes are `/create`, `/browse`, `/catalogue` and
`/registrations`, with redirects for historical links. Numeric comma-decimal
parsing and exact values are unchanged. Existing catalogue data, Unicode input,
Database baseline sources and checksummed SQL files were not translated or reset.

## Native browser login dialog

The normal API container was still running an earlier implementation whose
invalid-credential response contained `WWW-Authenticate: Basic`. That response
causes the browser's native login dialog. Editing source files alone did not fix
the running service; previous reports that left deployment to the operator were
incomplete.

Compose labels verified that `ouroboros-api-1` belongs to this workspace and
`compose.basic.yaml`. A presentation-only image was built with the deployed
service sources, the corrected Bearer error challenge, local Swagger assets and
explicit English authorization labels. Only this API service was recreated.
The existing SQL contract was retained, so this correction required no normal
database migration or administrative credential. No password was read, reset or
displayed. PostgreSQL and its persistent volume were preserved.

Docker no longer retained the original image content digest. The recovery image
`ouroboros-api:before-prompt-fix` was therefore reconstructed from the copied
deployed service sources and the already-built dependency image. The execution
helper and source snapshot remain in ignored `.tmp/`. They contain service code,
not copied secret mounts. Future normal startup uses the canonical service source
and its existing explicit migration checks; the independent pending alias upgrade
was not bypassed or represented as applied.

Certificate-verified HTTPS checks against the normal service returned 200 for
`/health`, `/docs` and `/docs/assets/authorize.js`. Swagger HTML loads
`OuroborosAuthPlugin`. A synthetic invalid Client Credentials request returned
401 without any Basic challenge. The live panel explains Client ID correctly.
An already-open native browser dialog must be cancelled once and the old page
reloaded; the server cannot close browser-owned windows.

## Which credential belongs where

| Field | Required value |
| --- | --- |
| Linked API User username, in App User sign-in on the current normal service | The linked API identity username chosen during enrollment |
| App Password | The separate application password chosen during enrollment |
| Client ID, in OAuth2 Client Credentials | The `client_id` returned when issuing an integration credential |
| Client Secret | The matching one-time `client_secret` from that response |
| PostgreSQL Master credentials | SQL administration only; never a Swagger login |

Client ID is not an App User or API User username. `POST /api-users` returns an
initial credential for a newly created separate integration identity.
`POST /api-users/{id}/credentials` issues another credential for an eligible
existing API User, subject to current authorization. The reserved installation
identity cannot receive Client Credentials. An App Password is not a Client
Secret. No account, credential or normal business row was created for this QA.

## Verification

- Frontend production build passed; its existing initial-bundle warning remains.
- Eight scoped Angular test files: 42 passed, including login, API errors,
  public configuration, labels, navigation and form conversation behavior.
- Assistant behavior: 18 passed. Assistant transport/validation/endpoints:
  11 passed, with controlled providers and no normal business writes.
- Shipped Swagger DOM authorization test passed with synthetic credentials.
- Central suite: 63 tests, 45 passed and 18 opt-in skips after regenerating the
  QA plan. The three traceability tests were rerun successfully after the repair.
- Public query metadata was regenerated and checked against its source schemas.
- The unrestricted Angular suite still cannot compile its pre-existing obsolete
  classification-confirmation and numerical-pagination specifications. These
  were retained; the passing scoped suite does not claim full-suite approval.
- A broader run excluding only those three incompatible files executed 113
  tests: 95 passed and 18 failed. Remaining failures involve registration,
  category relationships, incomplete API mocks and edit/dirty-state expectations;
  they were not hidden or treated as language verification passes. The output is
  in `reports/english_frontend_current.txt`.

Desktop browser inspection was attempted using the computer-use skill. The
helper failed with `foreground window did not report a process id`, and refreshing
window discovery returned no Chrome window. No physical browser rendering or
successful authentication interaction is claimed. The live HTTPS response/header
checks and shipped-bundle DOM checks above completed independently.

Scoped Angular output is in `reports/english_frontend_scoped.txt`; the full-suite
compilation failure is in `reports/english_frontend_tests.txt`. No Git commit,
push, normal schema mutation or normal credential change was performed.
