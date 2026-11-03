# 🏷️ Multiple categories during Tag creation

## UI and shared components

Only **Cadastrar Tag** gains the optional **Categorias de Tag** field. Existing Tag inputs and validations remain unchanged; editing existing tags and other forms do not gain the field. Creation with no selected categories retains the original single POST /tags flow.

`TagCategoryField` loads existing categories using GET /tag_categories in deterministic display-name order and 50-record pages. It exposes choices only after the whole list has been verified for page/count consistency and unique identifiers. Loading/failure/retry messages are visible; outdated requests are discarded when the field is destroyed or a newer load supersedes them. Display names are shown; IDs remain internal option values. No category creation action or popup is included.

`MultiSelect` is a reusable, owner-controlled checkbox dropdown. It uses the existing searchable-dropdown trigger/panel styles, native labelled checkboxes and the global focus styles. `select-options.ts` centralizes case-insensitive literal label filtering and unique selection values; the existing single-select dropdown uses the same filter without changing its behavior. The shared `readCataloguePages` helper rejects partial/drifting/duplicate page sets.

- Search changes which checkboxes are visible, never the selected IDs.
- **Select All** selects all approved loaded options, including those hidden by the current search.
- **Clear All** clears all selections, including hidden selections. Individual checkboxes can also be unchecked.
- Each checkbox has an explicit id/label association, and its label fills the full option row, including its padding. Clicking the text, empty row area or checkbox uses the native checkbox activation and the single change handler. No row/label click toggle is added, avoiding duplicate selection changes. The same rule applies to every shared MultiSelect instance.
- The shared option container is a flex row with stretched children and zero padding; its label flexes to fill both the row width and height and owns all inner spacing. Scoped selectors override the generic single-select list-item layout without changing other dropdowns, preventing an inactive margin around the clickable label.
- The panel explains this global action scope. There is no X/reset icon. The search is a text input without a native search-clear control.
- Empty-category and no-search-results messages are distinct. The trigger retains its existing selection summary/count; closing/reopening does not clear choices.
- Below the dropdown, selected categories appear as removable chips instead of a comma-separated selection paragraph. Each chip uses the option label loaded from the real `display_name_tag_categories` field (through the resource display configuration), never an invented `fantasy_name` property. Chips wrap with uniform spacing and existing design tokens; no chips or selection paragraph appear when nothing is selected.
- Chip options are derived from the same owner-controlled selection model as the checkboxes, using unique option IDs. Checkbox changes, Select All, Clear All and existing selections loaded by a form therefore update chips without a parallel selection store. Search only filters dropdown options and does not hide selected chips.
- Each chip has a keyboard-accessible `type="button"` removal control labelled `Remover [display name]`. It removes only that ID from the model, immediately updating the checkbox and trigger summary/count while preserving all other selections. Focus moves to a remaining removal control or the dropdown trigger. Removal neither submits the form nor calls an API independently; persistence continues through the owning form's existing save/search flow.
- Reuse `MultiSelect` and its external `multi-select-chip` styles for this presentation. The existing decorative `.pill` used elsewhere is not a removable selection component; do not add per-form chip markup, styles or selection logic.
- Buttons are non-submit. Tab/Space operate the native checkboxes; ArrowDown opens/focuses search and Escape closes/restores focus. Enter in search/checkboxes does not submit the Tag form.

Styles remain in external `frontend/styles/shared-fields.css`, using existing tokens and dropdown classes. No inline styles, independent browser storage or persistent selection service was added.

## Existing API contract and staged saving

The existing backend supports multiple categories through `tag_category_relationships`. POST /tags still accepts only `tag_name`, `display_name_tags` and optional `description_tags`; it does not accept a category array. Each relationship POST accepts exactly `{id_tags, id_tag_categories}`. The database enforces UNIQUE(id_tags, id_tag_categories). Existing exact `id_tags` filtering and bounded collection pagination support reconciliation.

The frontend allowlist now permits GET /tag_categories, GET/POST /tag_category_relationships and DELETE /tag_category_relationships/{id}, in addition to its existing paths. These are used by the form's internal association flow, not by a new relationship page. Tag Relationship, work association and category editing remain outside scope. No endpoint, schema, migration or business authorization rule was changed.

`TagCategoryRegistration` is provided by each Registration component, not as a persistent root selection store. When categories are selected:

1. Validate the Tag through the existing form rules and POST it once.
2. Retain its confirmed record/ID in memory and read current relationships for that Tag.
3. POST only missing selected pairs, one existing object endpoint call per pair. No guessed batch-size limit or invented nested payload is used.
4. Show the existing success confirmation and clear the form only after all requested relationships complete.

The existing busy guard covers the entire sequence. On relationship error, preserve all form data and selections and show the existing safe API error. A visible notice states that the Tag already exists and will remain if the user leaves. A deliberate retry reconciles existing pairs before sending missing ones, reusing the confirmed Tag ID rather than creating another Tag. Corrections to its already-saved text use the existing changed-field PUT /tags/{id}. If categories are unchecked or Clear All is used before retry, only relationships attempted in this unfinished creation flow may be removed through their existing individual DELETE route. Unrelated existing links are not blanket-deleted. A duplicate-pair conflict is accepted only after a read confirms the pair; mutation requests are never automatically replayed.

**Limitation:** these existing endpoints are separate transactions, so Tag creation and all relationships are not atomic together. Partial committed data cannot be rolled back by simply closing the form. No backend change was needed for multiple associations. If the Tag-creation response itself is lost or otherwise uncertain, the category flow cannot safely infer its ID: it preserves the draft, blocks blind repeat creation and asks the user to check Consultar before starting another attempt. The backend has no composite creation/idempotency contract; none was invented here.

## Reset and navigation

Selected IDs participate in the same dirty check as the existing inputs. Cancelled discard preserves them; confirmed discard, switching forms, opening an existing record, successful creation and Cadastrar outro clear the appropriate page-local selection/receipt state. No selection survives into an independent new registration. Leaving a partially saved flow never silently deletes the already-created Tag. Existing success identity and the centered Cadastrar outro button are retained.

## Delivery and manual follow-up

As requested, **no tests, build or browser validation were executed for this change**. API-boundary expectations were updated in source only. Existing historical verification in other documents does not validate this implementation.

The full-row clickable-label refinement was also reviewed in source only; tests, build and browser checks remain intentionally unexecuted for owner validation.

Manual checks: empty/no-match lists, multiple pages of categories, duplicate-free choices, search with Select All/Clear All, checkbox keyboard use, close/reopen, dirty-navigation cancel/discard, no-category ordinary creation, multiple association creation, duplicate clicks, API failures before/after Tag creation, relationship retry without another Tag, corrections/Clear All after partial failure, success/reset and Cadastrar outro. Use owned disposable QA infrastructure for writes; preserve normal records. Full atomic Tag-plus-category creation would require a separately designed backend contract and is not implemented.
