# Frontend delivery diagnosis — 2026-10-29

This investigation compares current source, production output and real HTTP responses, rather than relying on earlier test results. Evidence is in `reports/frontend_delivery_before.json` and `reports/frontend_delivery_after.json` (local generated reports).

## Listener and served directory

The inspected listener on 6969 was PID **12272**, parent **25284**, started at **2026-10-29 19:59:18.046 UTC**. Its command line was `"C:\Dev\Ouroboros\.venv\Scripts\python.exe" start.py`, and its process current directory was **C:\Dev\Ouroboros**. CIM identified the underlying Python executable at `C:\Users\Natacha\AppData\Local\Python\pythoncore-3.15-64\python.exe`. `scripts/inspect_listener.py` reads only the bounded process current-directory parameter; it does not dump environment variables or arbitrary command arguments.

`app/endpoints/browser.py` resolves `BUILD` to `PROJECT_ROOT/frontend/dist/browser`; `app/main.py` mounts that directory at `/frontend`. A unique inert static file created there, retrieved successfully through the live server, and immediately removed confirmed the actual directory independently of source assumptions. No catalogue or credentials were accessed or changed.

At **22:47:14 UTC**, the freshly generated index and all **seven** transitively imported JS/CSS assets matched their HTTP responses byte for byte. The build was **2561b78c4da73d71**, with main `/frontend/main-53N2OAP4.js` and stylesheet `/frontend/styles-72VMH4FJ.css`. Index SHA256: `be00fedbe982688ec169104145e1260c6c1151cf4620e51d681b0bb497eec8f1`. The public build manifest matched the source fingerprint, index, meta identifier and complete asset graph. The previous build also matched its HTTP responses; a wrong server directory was not reproduced.

**Subsequent listener inspection found no listener on 6969.** This task did not stop or restart any process. The HTTP results describe the timestamp above, not continued availability. Startup requires the owner's existing interactive credentials in the terminal.

## Cache and browser limits

HTML routes returned `Cache-Control: no-store`; fingerprinted JS/CSS returned `public, max-age=31536000, immutable`; `build-info.json` returned `no-cache`. `/ngsw-worker.js`, `/ngsw.json`, `/service-worker.js` and `/sw.js` returned 404. The current source/delivered graph contains no service-worker registration. Existing registrations and the document already loaded in the user's Chrome tab remain **not verified**. HTTP cannot establish their state. An old open document can retain loaded JavaScript; that is a possible explanation, not a diagnosed cause.

The browser access host was unavailable during this investigation. Desktop/mobile layout and actual authenticated interactions are not visually verified. No browser state, cookies or credentials were cleared.

## Requested behavior matrix

“Implemented and served” below means inspected source behavior is present in the generated graph actually retrieved over HTTP at the recorded time. It does not mean a visual or authenticated production mutation was performed. The active routed implementation uses shared registration components; older unused component files are not evidence of the delivered flow.

| Requirement | Status | Evidence and remaining manual check |
|---|---|---|
| Cadastrar / Salvar edição | Implemented and served | Shared registration actions; inspect create/edit headings and buttons. |
| Cancel/discard; prominent Cancelar | Implemented and served | Shared confirmation has primary Cancelar and initial focus; route/logout draft guards tested. Verify native browser prompt separately. |
| Unanswered platform booleans | Implemented and served | Shared tri-state control and validation; check untouched, false and true. |
| Price 00,00; blank omitted | Implemented and served | Money control and create serializer; PUT clearing remains explicit null. Verify Network request on disposable data. |
| Currency code first | Implemented and served | Typed EUR/USD/BRL options; inspect rendered selection. |
| Onde acessar empty; Aplicativo/Site | Implemented and served | Shared typed resource fields, no initial selection; legacy API values preserved during edit. |
| Conditional URL and payload | Implemented and served | Website-only presentation, create omission and PUT clearing rules; inspect disposable request/readback. |
| Autocomplete at most 20, no pagination | Implemented and served | Server request page 1/page_size 20, client cap 20; no dropdown pagination. |
| Classification names/positions | Implemented and served | Tier component reads all result pages. Actual normal classification names/positions were not queried without interactive authorization. |
| Compact advanced filters, clear, recent searches | Implemented and served | Selected filter controls and session-scoped successful-search history; test empty and populated states. |
| List context after editing | Implemented and served | Root view-state and routed round-trip regression; verify page/filter/order/scroll on return. |
| Accent #E6BD68 | Implemented and served | Exact source and HTTP CSS marker. Visual contrast review remains manual. |
| Enlarged Voltar ao início only | Implemented and served | Enlargement scoped to `.home-return`; compare other controls at desktop/mobile widths. |

No item was found implemented but absent from the inspected HTTP graph. No missing behavior was reproduced by this audit. Appearance and behavior in the user's existing tab remain **not verified**; the discrepancy is not declared resolved merely because HTTP matches.

## Reproducible build and remaining checks

`npm run build` now stamps the finished asset graph with `frontend/scripts/stamp-build.mjs`. The footer displays the identifier embedded in the loaded document, not a subsequently fetched server version. `/frontend/build-info.json` publishes only public frontend hashes, asset paths and build time. Old fingerprinted assets remain available so already-open documents are not broken during a build.

```powershell
cd C:\Dev\Ouroboros
$env:PATH="$PWD\.tools\node-v24.15.0-win-x64;$env:PATH"
npm.cmd --prefix frontend run build
.\.venv\Scripts\python.exe start.py
```

Enter existing startup credentials only in the terminal. Do not start a second listener if 6969 is occupied; inspect ownership first. Frontend rebuilds are read by the server without a backend restart. Main URL: **http://localhost:6969/**; registration **/cadastros**; consultation **/consultas**; Swagger **/docs**. PostgreSQL remains 6669 (container 5432); approved disposable ports remain 2469/2424/4242.

```powershell
.\.venv\Scripts\python.exe scripts/inspect_listener.py
.\.venv\Scripts\python.exe scripts/diagnose_frontend_delivery.py --probe-directory --output reports/frontend_delivery_after.json --summary
```

1. Preserve any current draft before reloading. Open a fresh tab at http://localhost:6969/. Compare footer `Interface 2561b78c4da73d71` with `/frontend/build-info.json` (a later rebuild may produce another ID).
2. In DevTools Network, enable Disable cache temporarily and reload. Confirm document HTML uses the same main/CSS filenames as the manifest. Do not clear cookies or all site data. Inspect the loaded document meta with `document.querySelector('meta[name="ouroboros-build"]')?.content`.
3. Read existing service-worker registrations in DevTools Application. Record their scope/script if present; do not automatically unregister or delete browser data.
4. Using existing login privately, inspect each matrix row. Exercise writes only in disposable QA. Specifically inspect POST without blank price/irrelevant URL, and PUT clearing URL, through Network; verify returned data.
5. Check Cancelar keeps drafts, explicit discard leaves, and edit return restores resource/page/search/order/scroll. Repeat at desktop and mobile widths. These steps remain manual.

Fresh verification: production build passed (368.75 kB initial output; existing 350 kB warning exceeded, below 450 kB failure limit); **58 Angular tests in 14 files passed**, including loaded-document build identity. The focused Python frontend suite completed **9 passed, 1 skipped** (owned Docker integration not enabled), including actual TestClient shell/manifest/asset hash comparisons. Evidence: `reports/frontend_delivery_angular_tests.txt` and `reports/frontend_delivery_backend_tests.txt`. Earlier backend integration results are historical, not evidence that this user's tab is current. No API/database/security contract changed in this delivery diagnosis. Stable QA scenario 19.5 now requires these source/build/live-delivery checks before visual acceptance.
