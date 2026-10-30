# Description limits and searchable classification positions

## One application policy

`app/text_limits.json` is the single application configuration source. It initially specifies `description_max_length: 4000` and grapheme Unicode version **16.0.0**. The backend loads it through `app/text_limits.py`. `frontend/scripts/generate-text-limits.mjs` generates the public `DESCRIPTION_MAX_LENGTH` and Unicode-version constants; npm build, test and watch generate them before compiling. Components and validators consume the generated constant, never a local numeric limit. Change the JSON, rebuild the frontend and restart the API to deploy a new limit consistently. `node frontend/scripts/generate-text-limits.mjs --check` detects stale generated configuration.

Both implementations use Unicode 16 extended grapheme clusters under [UAX #29 revision 45](https://www.unicode.org/reports/tr29/tr29-45.html): Python [uniseg 0.10.1](https://pypi.org/project/uniseg/0.10.1/) and JavaScript [unicode-segmenter 0.14.5](https://github.com/cometkim/unicode-segmenter/tree/unicode-segmenter%400.14.5). Versions are pinned deliberately; browser ICU/Intl versions do not control application counting. Shared `qa/grapheme-vectors.json` contains **1,093 official Unicode 16 conformance cases**, source/license references included. Both test suites verify every segmentation boundary against this same fixture. Refresh deliberately with `scripts/update_grapheme_vectors.py` when changing the segmentation policy and both dependencies together.

Letters, digits, whitespace, punctuation, combining sequences and composed emoji all participate in counting. `e` plus combining acute counts as one, as do family/profession emoji and a two-indicator flag. No trimming, normalization or silent backend truncation occurs.

## Exact API scope

The rule applies only to `description_tags`, `description_tag_categories` and `description_work_classifications`. Descriptions remain optional/nullable. Omitted POST uses the existing default; omitted PUT preserves, empty string remains empty and explicit null clears. POST objects/arrays, individual PUT and existing administrator bulk PUT all reject supplied overflow through the normal **422 VALIDATION_ERROR** envelope. Batch validation remains all-or-nothing. There are no new endpoints or database migrations: PostgreSQL **TEXT** stays unchanged. Observations, synopsis and other text fields retain their existing contracts.

Generated OpenAPI input schemas describe the rule and publish `x-max-graphemes` and `x-unicode-version`; they intentionally do not impose a misleading `maxLength` bound on composed text. Read schemas are unbounded so historical oversized descriptions remain readable. An unrelated partial PUT does not revalidate an omitted historical description against today's limit; only supplied description content must comply. Existing mutation authorization, locks and central audits remain authoritative.

No normal description was inspected or changed during implementation. Whether normal data contains oversized descriptions is **not verified**: the normal server/interactive credentials were unavailable. Once normal startup is running, the owner can inspect privately without catalogue writes:

```powershell
cd C:\Dev\Ouroboros
.\.venv\Scripts\python.exe scripts/inspect_description_lengths.py
```

Enter the existing API username/password only in that terminal. The script uses ordinary bearer authentication and read-only paginated API calls, prints counts plus oversized IDs/lengths, and never prints descriptions, credentials or tokens. It does not extract saved secrets or automatically fix/delete/truncate anything. The scan is not a transaction snapshot; rerun if records change concurrently.

## Shared description editor

`DescriptionInput` is reused by shared registration/editing and the earlier individual Tag/Classification form components. It has no required marker or tooltip. Its discrete counter is inside the lower-right reserved padding, separate from editable text, and reads `0 / 4000` initially. Counter and error descriptions remain associated with the textarea.

The editor uses grapheme validation rather than native maxlength (which would count a different unit). Typing or pasting an insertion above the limit is rejected as a **whole edit**, with a visible limit notice, rather than slicing an emoji or cutting a paste in the middle. Noncancelable input has a commit-time guard that restores the last accepted value. IME drafts are allowed to compose without interception; final composition commits only if valid. Initial oversized values are displayed unchanged with a warning. Users can progressively shorten them; changing such a description requires bringing it within the limit. Leaving it untouched permits unrelated updates. Successful form reset clears the model and counter normally.

## Classification position dropdown and current order

`SearchableDropdown` is the same component used by currency, with configurable choices and labels. Its currency defaults and API mappings are preserved. Classification uses the exact standardized position help from `TIER_HELP_TEXT`.

Create selects **Inserir na última posição (N)** first, with N equal to the validated total plus one. Its value is empty and serialization **omits tier**; the backend computes the actual append position in its transaction, so the browser's displayed N is never an authority. Other options are only ascending numeric positions, searchable by number, without classification names. Edit initially selects the persisted tier and offers existing 1..N moves. Membership/actor/list/record locks, deferred uniqueness, shifts and same-transaction audit evidence remain unchanged.

The existing complete-order loader still reads bounded API pages, sorts/verifies tier continuity and refuses incomplete or changing counts. Dropdown choices always cover that complete order. The approved order-item appearance is unchanged; a separate local view paginates the already validated order into **10 records**, with previous/next, page count and the existing total. Changing the order-list page cannot restrict the dropdown. Reload resets the view to page one. No public consultation paging behavior changed.

## Verification and operation

Focused frontend checks cover full Unicode conformance, counters, typing/paste/fallback/IME, historical text, create/edit validation, automatic append serialization, numeric search, edit preselection, all dropdown positions independent of order pagination, and first/last pages. Focused real API checks use only a UUID-owned disposable PostgreSQL cluster, exercising all three description resources, exact-limit composed emoji, overflow rejection, original-text preservation and unrelated historical edits. Normal records/credentials remain untouched.

Current result reports are `reports/description_tier_tests.txt`, `reports/description_contract_integration.txt`, `reports/description_tier_build.txt` and `reports/description_tier_full_checks.txt`. The full Python runner also covers transactional tier shifts/concurrency, existing API clients, authorization and audit rollback. Actual final totals and limitations are recorded in the delivery note in REGISTRATION_UI.md.

```powershell
cd C:\Dev\Ouroboros
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
$env:PATH="$PWD\.tools\node-v24.15.0-win-x64;$env:PATH"
npm.cmd --prefix frontend ci --no-fund --no-audit
npm.cmd --prefix frontend run build
.\.venv\Scripts\python.exe start.py
```

Use existing startup credentials privately. Main app/API: http://localhost:6969/; classification registration: /cadastros; Swagger: /docs. Normal PostgreSQL remains 6669, container 5432. QA uses approved 2469 HTTP, 2424 PostgreSQL and 4242 concurrent derived PostgreSQL; no additional listeners are selected.

Manual browser review remains separate: create/edit every existing description form, inspect lower-right counter and unchanged item appearance at desktop/mobile widths, compose with a real IME, paste combined accents/emoji at the boundary, search/select positions and navigate order pages. Verify automatic append while another disposable client inserts first. Use disposable data for writes. Physical keyboard/touch/IME, screen-reader output, live Swagger controls and normal-data inspection must not be inferred from DOM/schema tests.
