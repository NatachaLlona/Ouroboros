# Ouroboros frontend and browser security

Current phase-one registration controls: see [Individual registration UI](REGISTRATION_UI.md). It documents the unanswered checkboxes, exact comma-decimal input, currency/access selectors, conditional address, twenty-result anchored autocomplete, cancel-first unsaved-change protection, compact consultation filters and session-only recent searches. No API or database contract changes are required.

The public home, login modal and catalogue registration page now use Angular 22 with strict TypeScript, standalone components, Signals, Signal Forms and zoneless change detection under `frontend/`. FastAPI serves the optimized static build on the existing origin. Read [ANGULAR.md](ANGULAR.md) for dependency versions, Windows build/start commands, feature boundaries, three-form walkthrough and current execution evidence. Build before Python startup; there is no separate frontend runtime server, CDN, public signup or work/watchlist/history screen. Visible interface text is Portuguese; implementation and developer documentation remain English. The three original card illustrations and friendly snake mascot are local SVGs authored for this project; they do not copy the reference brands or hotlink images.

## Start the local application

Keep all existing `.app.config` fields and credentials. Explicitly add this non-secret development section when using the existing local HTTP server:

```json
"browser": {
  "origin": "http://localhost:6969",
  "allow_loopback_http": true,
  "idle_timeout_seconds": 7200,
  "absolute_lifetime_seconds": 43200
}
```

This section is present in the sanitized example for a fresh local installation. Existing private configuration is never automatically overwritten. The origin must match the browser address exactly, including scheme, hostname and port. `localhost` and `127.0.0.1` are different origins. HTTP browser sessions require both a configured loopback hostname and a loopback client address. Do not enable development HTTP on a public network or production service.

With no browser configuration, the fail-closed default is `https://localhost:<port>` and development HTTP is disabled. Production browser sessions require a real HTTPS ASGI request and an exact HTTPS `browser.origin`. They use a Secure, HttpOnly, SameSite=Strict, host-only `__Host-ouroboros_session` cookie with Path=/ and no Domain. This task does not provision TLS certificates or a production proxy. The built-in startup remains the existing HTTP local server; do not infer production HTTPS support from an HTTP preview. Proxy header trust remains disabled; arbitrary forwarded headers cannot change the browser origin or client address.

Before stopping an occupied listener, identify its executable/launch ownership. Leave unconfirmed processes alone. Stop only the confirmed Ouroboros terminal with Ctrl+C, then use:

```powershell
Set-Location -LiteralPath C:\Dev\Ouroboros
.\.venv\Scripts\python.exe start.py
```

Answer the existing interactive master-credential prompts; never extract secrets. Open **http://localhost:6969/** for the home page, **http://localhost:6969/cadastros** for the protected form page, and **http://localhost:6969/docs** for Swagger. This phase adds no database migration. Existing migrations through 011 are still required for the platform contract and are applied through normal interactive startup. No records, classifications, accounts, hashes, signing keys or volumes are replaced.

## Browser sessions and the API boundary

| Route | Behavior |
| --- | --- |
| GET / | Public home; works even when the database is unavailable |
| GET /cadastros | Reloads the current account; missing/expired session redirects to home/login, standard role gets a Portuguese 403 page |
| GET /browser/session | No-store session status, current username, catalogue permission, remaining lifetime and in-memory CSRF token; no bearer token |
| POST /browser/login | Strict username/password JSON; exact same Origin and allowed transport required; existing Argon2id verifier and shared account/client throttle |
| POST /browser/logout | Same-origin and CSRF verification; invalidate the server session and clear its cookie, including when the account can no longer create records |
| POST /platforms, POST /tags and POST /work_classifications | Existing routes, schemas, authorization, transaction-time authority checks, repository logic and central audit triggers |

The cookie is a cryptographically random opaque identifier. Only its SHA-256 digest indexes the server's bounded, locked memory store (maximum 10000 live sessions). The store retains user ID, credential version, absolute expiry and a CSRF secret; it retains no password or bearer/refresh token. Browser sessions use browser.idle_timeout_seconds=7200 (2 hours) and browser.absolute_lifetime_seconds=43200 (12 hours), independently of bearer auth.token_ttl_seconds. Accepted authenticated shell reloads and user-driven API requests renew only the idle deadline. Passive session polling and API reads without X-Ouroboros-Activity: user do not renew it. The absolute deadline never slides. Values must be integers with 60 <= idle <= absolute <= 86400. Expired entries are pruned; new logins at capacity return a safe 503 instead of growing without bounds. Login rotates the current browser session. Logout invalidates the record so replaying the former cookie fails. Shutdown clears the store. Sessions survive page reloads but expire on application restart; they are not shared across workers, consistent with the existing one-worker deployment rule.

Every cookie-authenticated protected request reloads the current account and verifies active state and credential version. Current role/scopes feed the shared `require_scopes` authorization; catalogue writes repeat authority checks inside their existing transaction. Standard users may log in but cannot use catalogue creation. Password changes, inactivation and demotion therefore affect existing browser sessions. Explicit bearer Authorization always takes precedence, including rejection of invalid bearer tokens; Swagger/Postman /token behavior and scopes remain unchanged.

Cookie mutations require exact Origin, permitted transport and a synchronizer CSRF token in X-CSRF-Token. Missing/mismatched values return 403 CSRF_REJECTED. Login requires JSON and exact Origin to prevent login CSRF. Cross-site browser fetch contexts are rejected; no CORS relaxation is added. SameSite protection is additional protection, not a substitute for CSRF verification. The development cookie has the distinct name `ouroboros_dev_session`; only its explicitly enabled loopback HTTP mode omits Secure.

All /browser/* request and response bodies are omitted wholesale from technical previews and audit captures, including malformed/rejected input and CSRF responses. Cookie/CSRF/session keys are also recursively redacted. Request headers are not logged. Never put any secret in a URL, source, console, localStorage, sessionStorage or a screenshot. The frontend holds its CSRF token only in DI service memory; its cookie is inaccessible to JavaScript. Session responses are no-store. Frontend responses enforce a local-only CSP, no framing, no referrer and no MIME sniffing. Only compiled assets under frontend/dist/browser are publicly mounted; raw source and page HTML are not exposed by the static mount.

Static GET/HEAD home/assets and the form shell do not create database audit rows; technical request logging still applies. Session APIs and actual catalogue requests retain the central request audit lifecycle. HTML/asset reads never become a second CRUD implementation. No-secret capture and business/audit atomicity still apply to existing API writes.

Security decisions consulted the official [OWASP ASVS](https://owasp.org/projects/asvs), [Session Management](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html), [CSRF Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html), [Authentication](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html), [Authorization](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html), [Password Storage](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html), [Logging](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html), [Input Validation](https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html) and [Error Handling](https://cheatsheetseries.owasp.org/cheatsheets/Error_Handling_Cheat_Sheet.html) sources on 2026-10-27. This is not a blanket OWASP-compliance claim.

## Form behavior and a manual walkthrough

The current Angular client also exposes **Classificação da Obra**, using work_classification_name, display_name_work_classifications, description_work_classifications and optional tier. Empty tier omits the JSON property; explicit tier uses the existing transactional backend insertion/reordering. No IDs or timestamps are requested. See ANGULAR.md for the complete current sequence. Earlier execution evidence below describes the handwritten frontend and must not be presented as Angular evidence.

Use a disposable QA instance for example records; never create demo entries in the normal database. Use existing **API** accounts, not PostgreSQL master credentials.

1. Open home and choose **Cadastrar**, then **Cadastrar itens isolados**. Repeat through **Consultar**. Shared selection pages keep Watchlist and Watched disabled with Em breve. The login modal leaves home visible through a light-brown overlay. Verify Tab/Shift+Tab, Escape, close, password visibility and restored trigger focus.
2. Enter an API supervisor or administrator account, click **Entrar**, and confirm navigation to /cadastros. A standard account gets an explicit catalogue-permission message. Invalid login keeps the modal open. Shared login throttling returns 429/Retry-After and the UI shows a countdown.
3. Choose **Plataforma**. Fill a QA name, independent paid/free/episodes/duration checkboxes, optional price and currency, chosen access types and optional HTTP/HTTPS URL. Empty price/currency/URL send null; no access selection sends []; no value is invented. Paid status does not invent or clear a price. Price text preserves decimal precision and supports the backend's decimal/exponent syntax. Generated metadata is never requested.
4. Click **Cadastrar plataforma** once. The button shows A guardar… and prevents duplicate clicks. On success, the returned name/ID remains visible until **Cadastrar outro** or a deliberately selected new type. Editable fields/drafts are cleared immediately after confirmed success; **Cadastrar outro** opens the empty form.
5. Choose **Tag**. Enter **Nome fantasia**, for example `Fantasia épica 🐉`. Blur/Tab/Enter reveals the technical input with ghost suggestion `fantasia_epica`; keep it or enter a custom value, followed by an optional description. Technical names follow the existing lowercase ASCII/underscore pattern. Display names support Unicode/emojis; entered names are not translated or silently rewritten. No category relationship is created. Submit and inspect the returned ID/name.
6. Enter an invalid URL/price and check safe Portuguese field guidance and preserved values. The interaction ID is shown for diagnosable API errors. A network failure warns that commit status may be uncertain; do not blindly resubmit. Switching types retains each draft. Values remain only in the live page, not persistent storage; navigation/reload can discard drafts and triggers the browser's unsaved-change warning.
7. Expire/logout the session in another tab while a draft is present. Submission requests login again and preserves the draft. Login does not automatically resubmit. Review and deliberately send. Click **Sair** to invalidate the server session and clear the cookie; reloading the private URL must require login again.

## Design, accessibility and QA

Reusable variables define the seven exact requested palette values. Cream surfaces, dark green text and dark mauve controls provide measured contrast: green/cream approximately 8.30:1, grayish yellow/cream 4.88:1, dark mauve/cream 9.52:1 and muted body text/cream 5.83:1. Mauve/cream is about 4.30:1 and is used for large headings/decorative accents, not small body text. Input boundaries use brown against paper at a minimum 3:1, and image captions use an opaque dark mauve background. Disabled controls remain clearly disabled. Tests verify the palette and selected WCAG contrast pairs; screenshots/visual review remain separate evidence.

Controls have real labels, visible focus and usable touch targets. The native named dialog makes background content inert, traps Tab/Shift+Tab and supports Escape/close/focus restoration. Layouts stack cards and form/mascot on small screens; reduced motion removes transitions. Dynamic user names, returned values and errors use textContent; fixed application markup alone uses templates. No user-provided HTML is inserted.

Scenarios **19.1–19.5** link the generated manual QA plan to session/public-page/contrast and disposable PostgreSQL tests. Run `.\.venv\Scripts\python.exe scripts/run_checks.py` for required automation. Browser UI evidence is recorded separately in the delivery record and screenshots under ignored reports/frontend/. Never infer actual GUI behavior from source assertions.

The review packager allowlists frontend HTML/CSS/JavaScript/SVG source alongside the API, so installation snapshots contain the required static files. Runtime configuration, credentials, logs and the temporary preview fixture remain excluded.

The browser review used a temporary loopback preview backed by the existing UUID-owned catalogue test harness and fresh random API credentials. Its temporary credential fixture was outside source/reports. The preview was stopped and its exact Compose project/volume/root were removed only after matching its working-directory/configuration labels to the allocation. The temporary fixture was deleted. Reproduce interface testing in your own disposable QA setup; never share a fixture or use the normal database for example writes.

## Login/navigation diagnosis — 2026-10-28

The supplied interaction `2026102707026687925067` contained 22 digits. Its unique ten-digit suffix matched the complete interaction **202610270707026687925067**, POST /browser/login at **2026-10-27 07:07:02 UTC**, in `logs/application_2026-10-27_070512_c756fb82.log`. The safe trace showed a 403 before credential verification; nearby GET /browser/session requests were also rejected. No login bodies or credentials were inspected. The normal private configuration lacked the browser section, so the secure default expected HTTPS while the actual origin was http://localhost:6969. This was an origin/transport denial, not evidence of insufficient account permissions or an incorrect password.

An authorized read-only Swagger query, GET /users?username=ouro, confirmed **id 1, role administrator, is_active=true**. No role, active flag, scopes, credentials or business records were changed. The existing normal listener was identified by its sanitized workspace launch; its owner restarted it using existing interactive credentials. Only the explicit browser.origin=http://localhost:6969 and browser.allow_loopback_http=true section was added to normal configuration; all prior fields were retained. This is the documented loopback-only development mode, not a changed default or production exception.

Two UI problems obscured that diagnosis: generic 403 mapping falsely described all browser boundary rejections as catalogue permission failures, and the notice was above the viewport after clicking the lower card action. The action now has a real /cadastros href as a JavaScript-independent fallback, visible session-check progress, and focused/scrolled-into-view feedback. Existing authenticated sessions on the login redirect proceed directly to the form rather than requesting another login. The API returns the distinct BROWSER_ORIGIN_REJECTED code for origin/transport checks; the frontend also understands older running servers using endpoint context. Invalid credentials, expired sessions, CSRF failures, actual catalogue denials, malformed responses, network errors and server failures retain separate explanations. Session status includes public current role/active metadata as well as can_create; no secret is added to logging.

After the owner's restart, the real Chrome flow identified ouro and opened /cadastros with the catalogue form visible and no modal or denial. Only navigation/read checks were performed on the normal installation. Regression coverage uses the existing scenarios 19.1–19.3: absent browser configuration rejects before password verification with the right code; the home action has a native navigation fallback; and administrator/supervisor/standard outcomes agree for cookie and bearer requests. Administrator and supervisor succeed, standard remains denied. HttpOnly cookies, CSRF, current-account/transaction authority checks and bearer precedence are unchanged.

### Validation of the login fix

The login-fix regression run completed on 2026-10-28 with exit code 0: **165 tests counted, 164 PASS, 0 FAIL/errors, 1 SKIP**, no fixture failures, and mandatory automation passed. The skipped check was the optional fixed-port/Swagger check because normal database port 6669 was occupied; it was not counted as successful. All write integrations ran in owned disposable resources. The generated QA plan check also passed. [Normal browser verification screenshot](../reports/frontend/normal-login-fixed.jpg) shows the authenticated catalogue form; normal navigation and reload were verified without creating catalogue records. Existing broader production TLS/screen-reader/manual validation limitations remain unchanged.

### Authorized promotion procedure, only if an account is actually standard

No promotion is needed for ouro. For an account independently confirmed as standard, an existing active administrator can authorize Swagger with their API account, GET /users with the exact username to identify the target, then deliberately execute PUT /users/{id}/role with `{"role":"supervisor"}` to grant the least catalogue role. Use administrator only if administrative powers are independently intended. The operation uses the existing transaction-time administrator check and audit path. Current bearer/session authorization reloads the stored role on subsequent requests. Do not use direct SQL, credential resets, first-administrator recovery, automatic promotion or disabled authorization to work around frontend/configuration errors. If no authorized administrator credentials are available, stop and obtain the owner's authorized recovery procedure instead.

## Observed validation — 2026-10-27

The required `scripts/run_checks.py` run completed with exit code 0 in 612.009 seconds: **163 tests counted, 162 PASS, 0 FAIL/errors, 1 SKIP**, and no fixture failures. All seven frontend tests passed, including actual PostgreSQL cookie-authenticated platform/tag creation, transaction-time demotion, CSRF rejection and whole session-body audit omission. Scenario totals were 78 PASS, 1 SKIP and 4 MANUAL. The skipped fixed-port/Swagger check encountered occupied database port 6669; it was not validated or counted as successful. Database integrations used owned temporary ports. The runner reports mandatory automation passed and overall QA approval PENDING_MANUAL_VALIDATION. See [sanitized results](../reports/summary.md).

Actual Chrome UI checks covered public disabled actions; opening/closing the modal; keyboard wrapping, Escape and focus restoration; visibility controls with an empty password; generic invalid credentials; successful supervisor login and reload persistence; standard-user permission feedback; a real 429/Retry-After countdown; platform creation with all three access types and unknown price/currency; Unicode/emoji tag creation; preserved fields after HTTP 422; logout in another tab followed by draft-preserving re-login without automatic resubmission; deliberate reset and persistent success feedback. Double-click submission was followed by a separate authenticated count check proving exactly one platform and one tag. No demo records were written to normal data.

Desktop and 390px/360px responsive layouts were inspected; no horizontal overflow was observed. Screenshots are in ignored reports/frontend/, including [home cards](../reports/frontend/home-cards-desktop.jpg), [form/mascot success](../reports/frontend/platform-success.jpg), [mobile tag form](../reports/frontend/tag-mobile.jpg) and [throttling feedback](../reports/frontend/login-throttled-mobile.jpg). Full-page screenshot capture timed out, so the retained images are viewport captures. Temporary viewport overrides were reset and QA tabs closed. Browser storage API inspection was unavailable through the read-only browser tool; source regressions verify no web-storage/cookie-reading/console-secret paths, and HTTP/audit tests verify cookie flags and secret omission. Live production TLS, a full screen-reader review, physical password-manager paste and recovery from a real network outage remain manual checks. No Node CLI/build step is required; modules were exercised in Chrome.


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
