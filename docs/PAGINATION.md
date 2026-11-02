# 🔢 Shared Angular numerical pagination

`Pagination` in `frontend/src/app/shared/pagination.ts` is the **mandatory component for every current and future paginated frontend list and CRUD**. Autocomplete and searchable dropdowns are excluded. Do not duplicate numerical-window calculations or styles per screen.

## Contract

| Binding | Meaning |
| --- | --- |
| `[page]` | Current UI page, starting at 1 |
| `[totalPages]` | Page count calculated by the existing owner |
| `[busy]` | Optional loading/mutation state; disables navigation |
| `(changed)` | Valid requested one-based page |

```html
<app-pagination [page]="page()" [totalPages]="pages()"
  [busy]="loading()" (changed)="load($event)" />
```

The component never requests data or changes filters, ordering or page size. Current API numbering also starts at 1; no conversion is needed. Convert at the integration boundary if a future API differs. Keep item totals and summaries in the owning screen, including when navigation is hidden for zero or one page.

## Calculation and navigation

The exported pure `paginationItems(page,totalPages)` builds only the first two pages, the current page with up to two neighbors on each side, and the last two pages. Invalid positions are discarded, duplicates removed and numbers sorted. Insert a single missing page directly; use `…` only for two or more hidden pages. Time, memory and output are bounded independently of the total; never generate all pages and slice afterward. `clampPaginationPage` centralizes valid-page normalization. Invalid/noninteger/unsafe totals produce no items.

```text
‹ Anterior  1 2 … 13 14 [15] 16 17 … 99 100  Seguinte ›
```

Invalid, current-page and busy navigation emits nothing. Buttons use `type="button"`; the current page is disabled and marked `aria-current="page"`. Previous/next disable at their boundaries. Ellipses are noninteractive spans. A labelled navigation landmark and Portuguese button names identify controls. Existing focus-visible outlines apply. Shared external CSS supplies subtle current-page emphasis, at least 44-pixel targets and wrapping on narrow containers. No component style injection or CSP change is needed.

## Integrations and future rules

- `TierPosition` retains ten tier-sorted current-order rows, their appearance and the complete-order count. It reuses the complete verified order **already required by the position dropdown**, without adding reads. A shrinking total clamps to the last available page, or 1 when empty.
- `Consultation` covers Platform, Tag and Work Classification. It still requests one API page of ten records with applied filters/order. Existing request-generation/session guards reject stale responses; existing last-page correction refetches the last available page after deletion/total changes. Recent searches and edit-return resource/page/filter/order/scroll restoration remain unchanged.

Future owners must reset to page 1 on new criteria, retain applied filters/order/page size for navigation, reject older overlapping responses, correct invalid pages after total changes and restore edit-return context. Never download all records merely to simulate pagination. Keep API/database contracts unchanged.

## Verification — 2026-10-30

**119 Angular tests across twenty files passed.** Coverage includes zero/one/few pages, start/middle/end, 15/100, single-page gaps, huge safe totals, sorted unique valid output, bounded calculation, accessibility, boundaries, busy state and non-submit buttons. Integration coverage includes direct current-order navigation without new reads, shrinking totals, direct consultation numbers with filters/order and ten-record requests, stale responses, deletion recovery and routed edit-return restoration. Existing autocomplete/dropdown suites pass.

Production build/provenance stamping passed: `15d0200837445f9d`. Initial assets are 375.07 kB, above the unchanged 350 kB warning and below the 450 kB error budget.

**Visual verification remains pending.** A separate preview with the actual Angular components and synthetic read-only in-memory data compiled. Computer Use then stopped before navigation because it could not confidently determine the current Chrome URL to enforce policy. No browser input followed that stop; the owned preview server was ended. Desktop/mobile rendering, keyboard behavior and screenshot review are not verified by DOM tests.

Manual follow-up in owned disposable infrastructure: inspect 15/100 on desktop/mobile; verify Tab/Shift+Tab, Enter/Space, focus, current-page indication, comfortable wrapping and no horizontal overflow; navigate current order and all consultations; apply filters/order, return from edits and remove a last-page record. Preserve normal records/credentials. See QA scenario 19.4.
