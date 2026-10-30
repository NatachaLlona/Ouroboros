# Angular frontend architecture and build

Current phase-one registration controls: see [Individual registration UI](REGISTRATION_UI.md). It documents the unanswered checkboxes, exact comma-decimal input, currency/access selectors, conditional address, twenty-result anchored autocomplete, cancel-first unsaved-change protection, compact consultation filters and session-only recent searches. No API or database contract changes are required.

The approved client-rendered frontend is Angular 22. FastAPI and PostgreSQL retain all existing API, authentication and persistence responsibilities. There is one application origin, normally `http://localhost:6969`, with `/`, `/cadastros`, `/docs` and the existing API paths. No SSR, Node production service, service worker or extra state library is introduced. The infrastructure-only `compose.yaml` and its PostgreSQL image, ownership and volumes are unchanged; there is no application Docker image to retrofit. A future container image must build with Node in a separate stage and copy static assets into the Python runtime stage.

## Reproducible dependencies

Verified on 2026-10-28 against [Angular compatibility](https://angular.dev/reference/versions), [stable releases](https://angular.dev/reference/releases) and the npm registry: Angular core/common/compiler/forms/platform-browser/router, compiler-cli, CLI and build **22.2.3**, TypeScript **6.0.3**, Node **24.15.0**, RxJS **7.8.2**, tslib **2.8.1**. The lockfile also pins Vitest **4.1.12** and jsdom **29.1.1** for tests. Use `npm ci`, not an unreviewed major update. The official compatibility table currently labels its Angular 22 row `22.0.x`; the selected 22.2.3 packages' own engine/peer dependencies were also verified by npm installation and strict compilation. Node requirements are `^22.22.3 || ^24.15.0 || ^26.0.0`, TypeScript `>=6.0.0 <6.1.0`.

## Windows build, development and startup

Install official Node 24.15.0 on PATH, or use the already downloaded ignored project-local tool for this workspace:

```powershell
Set-Location -LiteralPath C:\Dev\Ouroboros
# Only needed when using this workspace's project-local Node:
$env:PATH = "$PWD\.tools\node-v24.15.0-win-x64;$env:PATH"
Set-Location frontend
npm.cmd ci --no-fund
npm.cmd run build
npm.cmd test
Set-Location ..
.\.venv\Scripts\python.exe start.py
```

Enter existing database credentials privately at the normal prompts. Open **http://localhost:6969/**. Preserve `.app.config`, `.secrets`, classifications, tags, accounts and database volumes. No migration is added by the Angular change. Existing migrations through 011 remain required. The previously verified explicit `browser.origin`/`allow_loopback_http` configuration is retained, never rewritten automatically. No permission promotion is part of deployment.

For frontend development, run `npm.cmd run watch` in a second terminal under `frontend/`, keep FastAPI on 6969, and reload the browser after a successful build. There is no separate dev origin or CORS relaxation. Run a final `npm.cmd run build` to restore optimized production assets. Node is a build tool only. `start.py` never installs npm dependencies or rebuilds assets on startup. A missing build returns a safe 503 for the shell; run the build before startup.

Before replacing a running normal server, use `scripts/inspect_listener.py` to establish ownership. Only the owner should Ctrl+C the confirmed Ouroboros terminal and rerun the command above with existing private prompts. Do not stop unrecognized listeners. Restart clears process-local browser sessions, so sign in again.

## Boundaries and tradeoffs

- `src/app/home/`: public Cadastrar/Consultar entry points and shared selection cards with native links to the protected routes.
- `src/app/auth/`: DI session service and accessible native-dialog login component. The native dialog supplies browser focus containment and keyboard behavior; small `ElementRef` lifecycle calls open/focus the dialog and restore focus. There is no manual template construction or dynamic HTML insertion.
- `src/app/catalogue/`: lazy shared create/edit and consultation routes, typed resource definitions, Signal Forms field presentation, changed-field payloads, paginated name autocomplete and page-scoped drafts. Shared shell/tabs/pagination/confirmation/selection cards live in src/app/shared/. Classifications are work-rating categories, not tag categories. Their omitted tier property is absent from JSON; explicit tier is passed to the backend without computing or updating other rows.
- `src/app/shared/`: HttpClient API boundary, safe error messages and focused notices. Only fixed relative same-origin endpoints are accepted. There is no automatic mutation retry.

Strict TypeScript and Angular templates are enabled. Components are standalone (Angular's stable default). Signals hold UI/drafts; computed values derive labels/access/errors; zoneless change detection is Angular 22's default. Stable [Signal Forms](https://angular.dev/guide/forms/signals/overview) bind form state. Forms perform ordinary required/format guidance, while full validation, authority, generated metadata, tier locking/reordering and audit transactions remain authoritative in Python/PostgreSQL. No duplicated domain repository lives in TypeScript. Route components use promises/`firstValueFrom`, bounded HTTP timeouts and cleaned-up timers; no unmanaged subscriptions/effects are introduced.

Session checks are coalesced in bounded service state. Accepted user activity updates the idle deadline from server headers; background expiry probes do not renew it. The server enforces a fixed twelve-hour absolute cap. Server authorization still reloads the account/version on every protected API request. Expiry opens login without destroying drafts; reauthentication never resubmits a POST. Inputs remain after API validation/network errors. Unknown commit status warns the user to verify before resubmitting. Confirmed creation immediately clears editable fields and drafts while preserving the persisted ID/name separately in the success confirmation; **Cadastrar outro** opens the already empty form. Type switching retains each draft. Drafts are page-scoped; leaving/reloading discards them, with a beforeunload warning for edits. Browser storage and logs never receive passwords or tokens.

## Session, CSP and static delivery

The existing HttpOnly SameSite=Strict opaque session cookie, expiry, logout, credential version, role checks and shared login throttle remain unchanged. Angular cookie-XSRF defaults are explicitly disabled: this server uses a synchronizer token from `/browser/session` or login, kept only in memory and sent as **X-CSRF-Token** for mutations/logout. Cookies are sent only to the same origin. Bearer Swagger/Postman clients keep their existing contracts.

Origin/configuration denials remain distinct from permission denial, invalid credentials, expired/revoked sessions, CSRF, 429/Retry-After and transport/server errors. Login clears the password model before awaiting the request, never retries automatically, and observes a bounded Retry-After countdown. Native dialog supports Tab/Shift+Tab, Escape, close and focus restoration; closing is disabled during the in-flight login. Dynamic user values use Angular interpolation, never sanitizer bypasses.

FastAPI serves only explicit `/`, `/cadastrar`, `/consultar`, `/cadastros` and `/consultas` SPA shells; direct private navigation still checks current backend account state and redirects unauthenticated users or sends a 403 shell for standard users. Client navigation performs the same visible session/permission flow; backend APIs remain authoritative. There is no catch-all SPA route intercepting `/docs`, `/openapi.json`, API misses or missing static files. `/frontend` mounts only `dist/browser`; raw source and HTML files are unavailable there.

HTML/session responses are `no-store`; hashed JS/CSS receive one-year immutable caching; stable illustration paths revalidate. Critical CSS inlining and font downloads are disabled, allowing local-only script/style CSP without unsafe-inline. `base-uri 'self'` permits Angular's same-origin base element. Old hashed bundles remain on rebuild (`deleteOutputPath=false`) so an already open page can still load its previous lazy chunks. Deploy the complete browser directory with index last/atomically, retaining prior bundles while clients may still use them. Do not delete old bundles while serving active clients. Asset retirement is an explicit deployment maintenance step, not automatic application-start cleanup.

Security design preserves the rules in [FRONTEND.md](FRONTEND.md) and the audit contract. Official OWASP [Session Management](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html) and [CSRF Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html) sources were consulted on 2026-10-28. Validation is not a blanket compliance claim.

## QA commands and evidence

Run the build and frontend tests before Python tests. `scripts/run_checks.py` uses disposable infrastructure for writes and the single QA catalogue for manual/automated scenario IDs. Scenarios **19.1–19.5** now include Angular behavior, all three forms and tier insertions. API paths/contracts have not changed, so Postman/OpenAPI mutation definitions are deliberately unchanged.

```powershell
.\.venv\Scripts\python.exe scripts/generate_qa_docs.py --check
.\.venv\Scripts\python.exe scripts/run_checks.py
```

For a real browser preview with newly generated disposable API accounts and no normal data:

```powershell
$env:FOUNDATION_RUN_INTEGRATION = '1'
.\.venv\Scripts\python.exe scripts/preview_angular.py
```

The preview uses **http://127.0.0.1:2469/**, fresh UUID-owned PostgreSQL and random credentials. Ctrl+C performs cleanup. The optional ignored fixture-file argument is for local QA automation only, never reports/version control. A `.tmp/angular-preview.stop` marker also requests graceful shutdown. All browser example writes must remain on this isolated origin. Never use normal data as a test fixture.

Manual sequence: (1) logged out, select **Cadastrar itens isolados**, test modal keyboard/Escape, log in as supervisor/admin and refresh `/cadastros`; (2) create a platform with all optional choices and inspect ID/readback; (3) choose Tag, enter technical name, Unicode display name and multiline description, submit/read back; (4) choose Classificação da obra, submit one with empty tier, then **Cadastrar outro** and one with tier=1, verify persisted ordering through Swagger; (5) provoke validation/network/session expiry while drafting, verify values survive and no automatic POST occurs; (6) logout, test direct private navigation, standard rejection, mobile and reduced-motion layouts. Only enter genuine intended records on the normal installation.

Actual run counts, measurements and browser evidence are recorded in the delivery section below, separate from historical handwritten-frontend evidence.

## Delivery validation — 2026-10-28

- Production build succeeded with strict TypeScript/templates and the configured bundle budgets. **18 Angular tests passed**, zero failed, across API/CSRF, session expiry/coalescing, login password clearing/throttling, exact payloads, draft preservation, duplicate submission and repeated visible feedback.
- Final full Python QA run: **165 executed: 164 passed, zero failed, one skipped**, no fixture failures or consistency errors, duration **459.727 seconds**. The skip is the definitive default-port integration because port **6669** is occupied; disposable integration used temporary ports. The skip is not successful validation. Scenario results are 78 PASS, one SKIP and four MANUAL. Earlier full execution recorded a disposable database connection error; all eight targeted audit tests and the subsequent complete run passed. The first failure remains recorded separately rather than being relabelled.
- Production npm audit reported **zero vulnerabilities**. QA catalogue/generated plan and `git diff --check` passed. The GitHub workflow now builds/tests Angular before Python checks; hosted execution was not performed.
- Real Chrome on owned disposable PostgreSQL: supervisor login navigated to registration; refresh retained the session; platform with application/website access and URL, Unicode multiline tag, omitted-tier classification and explicit-tier classification were created through Angular. Authenticated API readback verified the platform/tag and classification order **angular_insert=1, angular_append=2**. Logout and standard-user rejection worked. No normal catalogue records, credentials or permissions were changed.
- Desktop and 390×844/360×800 browser layouts were inspected. No horizontal overflow was observed, registration choices have at least 44px height, local illustrations loaded, and checked transitions emitted no unexpected console warnings/errors. Native-dialog Escape restored trigger focus; repeated standard-user denial focused its message inside the viewport. Reduced-motion CSS is retained; a full screen-reader/physical-mobile/browser-matrix review and production HTTPS deployment remain manual checks.

Final local optimized build measurements (Node 24.15.0, Angular CLI 22.2.3, Windows; decimal kB):

| Assets | Raw bytes | Independently gzipped bytes |
| --- | ---: | ---: |
| Initial JS/CSS | 343626 | 106452 |
| Lazy home | 4539 | 2128 |
| Lazy registration | 16630 | 5167 |
| All local SVGs | 8162 | Not measured |

The CLI's separate transfer estimate is **93.09 kB initial**, **1.86 kB home** and **4.58 kB registration**; these estimates are not the independently measured gzip totals. Cold home also loads its lazy chunk; the registration chunk loads on navigation. An incremental production rebuild took about 1.5 seconds in this workspace; this is not a clean-install benchmark or a backend latency measurement. There is no claim that Angular improves API latency. Machine/network conditions and browser instrumentation were not controlled for user-performance benchmarking.

Sanitized local evidence: `reports/angular_validation.json`, `reports/angular_full_checks_final.txt`, `reports/results.json` and `reports/frontend/angular-*.png`. Screenshots include desktop home/classification, mobile home/login/classification and optional tier help; passwords/tokens are absent. Preview instances and their allocated databases/volumes were cleaned up.

The owner restarted the confirmed normal Ouroboros terminal using the existing private prompts. Real browser verification at **http://localhost:6969/** confirmed Angular **22.2.3**, successful **ouro** session, navigation to **/cadastros**, direct refresh retaining access, and the work-classification form including optional tier. No normal form was submitted and no normal account, credential, classification, tag or infrastructure was changed. `reports/frontend/angular-normal-classification.png` captures the activated form. One diagnostic tab stopped accepting synthetic control input; a fresh tab confirmed the same build/flow without code changes. No unexpected console warnings/errors were reported in the verified normal tab.


## Angular catalogue refinements — 2026-10-29

The public home now has **Cadastrar** and **Consultar** actions, leading to reusable selection cards at `/cadastrar` and `/consultar`. Watched and Watchlist remain disabled with **Em breve**. Protected `/cadastros` and `/consultas` use the current browser account and existing catalogue permissions. No bulk frontend operations are provided.

The shared form shows **Nome fantasia** first: platform_name for platforms, display_name_tags for tags and display_name_work_classifications for **Classificação da Obra**. Fixed fantasy_name_<table> metadata is never an editable name. Platforms have no technical-name property. For tags/classifications, typing alone does not reveal the technical field; blur, Tab or Enter after nonblank text reveals it. Tab moves to it; clicking elsewhere does not steal focus. Ghost suggestions use the existing ASCII technical pattern; a custom value or original edit name is preserved. Enter in the fantasy-name input accepts an active/unique prefix suggestion or completes that field, never submits a record.

Autocomplete debounces escaped literal ILIKE substring searches, fetches ten records per page, disregards stale results and exposes native scrolling, explicit scroll controls, arrows, Enter and Escape. A unique prefix match has a translucent suffix; middle/end matches have no invented suffix. Selection only opens **Cancelar / Editar** confirmation. Confirming retrieves the current record, and individual PUT sends changed editable fields, preserving omissions versus explicit nulls. Empty tiers append on creation; the backend owns all tier shifts. Confirmed creation immediately clears editable state/drafts and unmounts autocomplete; the saved name/ID remains separately in the success notice. Failed writes preserve input and are never retried automatically.

Consultation starts at page=1/page_size=10, using count/page/page_size/items. Basic name search adds escaped substring wildcards. Advanced filters expose the implemented public query metadata, exported by `scripts/sync_frontend_contracts.py`; `--check` detects drift. An advanced filter on the display-name field replaces/disables the basic search. Calendar dates/ranges retain application/filter timezone semantics. Ordering uses only published scalar fields and asc/desc. Apply/order/resource changes reset the page. Out-of-range pages recover to the last available page. Edit actions retrieve by ID; trash requires explicit confirmation before a single DELETE by ID. Dependency conflicts retain the dialog and explain the restriction. Successful deletion refreshes count/page; no bulk deletion exists.

The header keeps the existing circular mark with the single wordmark **Ouroboros**. The password button is a non-submit accessible eye/crossed-eye icon. Required fields have semantic required state and bold #CA7239 asterisks plus **\* Campo obrigatório**. The remaining warm palette/artwork is preserved.

Approved listeners: main API/frontend **6969**, normal PostgreSQL host **6669**, Angular preview **2469**, explicitly chosen disposable PostgreSQL host **2424**. PostgreSQL container port stays **5432**. Never choose another listener automatically when one is occupied. Existing QA harnesses require operator-selected OUROBOROS_QA_DB_PORT and OUROBOROS_QA_API_PORT. HTTP tests and preview reuse 2469 sequentially. No private configuration, normal credentials or records are changed.

```powershell
Set-Location -LiteralPath C:\Dev\Ouroboros
$env:PATH = "$PWD\.tools\node-v24.15.0-win-x64;$env:PATH"
npm.cmd --prefix frontend run build
npm.cmd --prefix frontend test
$env:OUROBOROS_QA_DB_PORT = '2424'
$env:OUROBOROS_QA_API_PORT = '2469'
$env:OUROBOROS_QA_DERIVED_DB_PORT = '4242'
.\.venv\Scripts\python.exe scripts/run_checks.py
# Only after the checks have released these ports:
$env:FOUNDATION_RUN_INTEGRATION = '1'
.\.venv\Scripts\python.exe scripts/preview_angular.py --port 2469
# Ctrl+C cleans up the owned preview. Normal startup uses existing private prompts:
.\.venv\Scripts\python.exe start.py
```

Swagger is **http://localhost:6969/docs**, the main home is **http://localhost:6969/** and the isolated preview is **http://127.0.0.1:2469/**. A running old Python process retains its earlier in-memory OpenAPI; rebuilding Angular cannot refresh it. `/docs`, `/openapi.json`, HTML and browser-session responses are no-store. Do not restart an unidentified listener or substitute schema tests for actual Swagger UI execution.

Manual QA: open both selection pages; log in to isolated registration; type a fantasy name and test Tab/Enter/blur and custom technical input; choose/cancel/edit a suggestion; create and verify cleared fields; search a middle substring; try advanced tier/date filters and paging; edit one item; cancel then confirm trash; check dependency conflict, expiry and draft preservation; inspect desktop and 390px/360px layouts. Record actual browser evidence separately from unit/API results.

The owner additionally selected **4242** for the second disposable PostgreSQL cluster used concurrently by the derived-project isolation test. Set **OUROBOROS_QA_DERIVED_DB_PORT=4242**. This is QA-only; never substitute it for normal 6669 or HTTP/Angular 2469. The hosted workflow requires all three QA port inputs from its operator.

## Refinement delivery verification — 2026-10-29

- Final production compilation passed with strict TypeScript/templates. **28 Angular tests passed**, zero failed, covering API/CSRF, session state, login destination, keyboard completion, stale autocomplete responses, effective technical names, shared create/edit payloads, reset/draft behavior, filters, paging and confirmed individual deletion. These are unit/DOM tests, not a claim of real-browser execution.
- Final complete Python runner: **166 executed: 165 PASS, zero FAIL, one SKIP**, duration **451.974 seconds**. Scenario totals: **78 PASS, zero FAIL, one SKIP, four MANUAL**. There were no fixture failures or consistency errors. The default-port probe is skipped because normal PostgreSQL occupies 6669; disposable tests use the owner-selected ports. An earlier run's derived-project failure from reusing 2424 is retained in `reports/refinements_full_checks.txt`; the corrected concurrent test uses the separately approved 4242. The final result is in `reports/refinements_full_checks_final.txt`, `reports/results.json`, `reports/summary.md` and `reports/junit.xml`.
- A separate real HTTP preview on **127.0.0.1:2469**, with owned PostgreSQL on **2424**, passed OpenAPI validation of returned records, object/atomic-array creation, classification description/tier, name/tier/calendar filters, ten-item pagination, single reads and immutable echoes, PUT null/omission rules, CSRF denial, existing bearer access, and individual DELETE with committed audit evidence. Sanitized evidence is `reports/refinements_http.json`; no normal records were used. The preview, both concurrent QA clusters and their allocated volumes were cleaned up; its private fixture file was removed.
- OpenAPI corrections document cookie authentication alongside bearer, preserve legitimate description/tier fields and single/array examples, remove misleading null defaults on optional nonnullable PUT properties, and include the browser-login 429 error model. The focused API/OpenAPI suite passed **19 tests**. No endpoint or database field was renamed, and existing Postman/bearer clients retain their contracts. Generated QA, public query metadata, embedded Postman JSON and whitespace checks passed.
- Final initial bundle is about **354.08 decimal kB** (CLI transfer estimate **93.62 kB**). It exceeds the existing **350 kB warning** by **4.08 kB**, remaining below the unchanged **450 kB error** limit. Lazy registration is about 23.52 kB and consultation 13.69 kB. This is a local build measurement, not a controlled browser-performance benchmark.
- Current real desktop/mobile layout and Swagger UI execution remain **manual**. Computer Use ended because it could not determine the current Chrome URL with sufficient confidence; no further UI input was sent. Earlier screenshots in the dated Angular delivery section do not validate this refinement revision. Hosted GitHub execution, physical mobile and screen-reader review were not performed. Normal 6969 had no application listener when inspected; no normal application was restarted or normal credentials extracted. Start it using the existing interactive prompts after reviewing the build.

`reports/refinements_validation.json` summarizes these outcomes without credentials. No staging, commit, push or merge was performed.
