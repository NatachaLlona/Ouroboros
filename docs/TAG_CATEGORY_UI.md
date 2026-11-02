# 🏷️ Tag submenu, category creation and card images

## Scope and architecture

The main registration choices remain **Plataforma | Tag | Classificação da Obra**. `RegistrationNavigation` in `frontend/src/app/shared/registration-navigation.ts` handles navigation only, composing the existing `ResourceTabs` and a smaller secondary group. Selecting main Tag immediately selects the Tag form. Its submenu shows Tag on the left and Categoria de Tag on the right, and is absent from other sections. Buttons expose their selected state and retain global keyboard/focus styles and comfortable targets.

The submenu now uses the reusable `equal-width-options` Grid class: two equal areas (50% each of the usable option space), with centered labels and the existing selected border spanning the respective area. Existing gap, padding, colors, typography and responsive behavior are retained. The main menu distribution is unchanged.

## Entity-specific registration headings

The typed `registrationTitles` configuration in `catalogue/resources.ts` is the single creation-heading source. `Registration.title` reacts to the actual selected form, so confirmed main/submenu switches update the heading immediately while cancelled dirty switches keep the original heading and form. Editing retains its existing Editar + entity label rule. `CatalogueLayout` continues to render the same h1 with existing typography/position; the subtitle is unchanged.

| Selection | Creation heading |
| --- | --- |
| Plataforma | Cadastrar Plataforma |
| Tag | Cadastrar Tag |
| Categoria de Tag | Cadastrar Categoria de Tag |
| Classificação da Obra | Cadastrar Classificação da Obra |

This presentation-only refinement was inspected in source. Tests, production build and browser navigation were intentionally not run, as requested; functional and visual validation will be performed manually by the owner. Prior verification below describes the earlier category/image delivery, not this refinement.

The existing `Registration.choose()` and `UnsavedChanges` guard handle every form switch. Cancelling discard keeps the form, selected submenu and draft. No separate form implementation or unsaved-state mechanism was introduced. Pre-existing Tag inputs and validations remain unchanged. The subsequent [multiple-category field](TAG_CATEGORIES_SELECTION.md) adds optional selection and staged associations during new Tag creation, preserving the original no-category flow.

`RegistrationResource` and `registrationDefinitions` add `tag_categories` only to registration. Existing `Resource`, `resourceDefinitions`, main resource options and generated consultation metadata retain their three resources. Category editing and lookup-to-edit are not exposed; its display-name field retains shared labels and technical-name completion with category lookup disabled. No relationship interfaces, category popup, work-tag association, Watchlist/Watched workflow or category consultation is added.

## Verified existing contract

The database model in migration 005, `app/schemas/catalogue.py`, `app/endpoints/catalogue.py` and the running server's `/openapi.json` agree. No backend contract or business rule was changed.

| UI | POST /tag_categories property | Existing contract |
| --- | --- | --- |
| Nome Fantasia | `display_name_tag_categories` | Required string |
| Nome Técnico | `tag_category_name` | Required; `^[a-z][a-z0-9]*(_[a-z0-9]+)*$` |
| Descrição | `description_tag_categories` | Optional string/null; centralized grapheme limit |

Automatic identity, sequence, prefix, fixed table name and UTC dates are not editable. The category form sends one object using shared `editorPayload` and `Api`. Subsequent Tag multi-selection additionally uses GET /tag_categories and the existing tag-category relationship read/create/individual-delete routes internally. Category editing and Tag Relationship endpoints remain unavailable. Authentication and transactional authority remain enforced by the existing backend.

Reuse `FieldLabel`, global fantasy-name wording, technical-name suggestion/manual preservation, `SharedFormField`, `DescriptionInput` and the generated limit from `app/text_limits.json` (currently 4000 Unicode 16 graphemes). Description has its shared counter and no tooltip. Existing validation, busy/duplicate prevention, API feedback and failed-draft retention apply. Confirmed success clears editable state immediately and uses the existing success notice and horizontally centered Cadastrar outro button.

## Image navigation

Home image links and existing buttons read the same shared destinations for Cadastrar and Consultar. Intermediate selection image links and buttons use the same `destination()` method. Route components continue to own session/permission/login behavior; images introduce no alternative handler or destination.

Active images are separate labelled RouterLink anchors with interaction cursor and global visible focus. They do not wrap another interactive control. Existing buttons, artwork dimensions and layout are retained. Watchlist and Watched images remain plain noninteractive containers, matching their disabled Em breve buttons.

Styles are external in `frontend/styles/shared-fields.css`; no injected styles or CSP exceptions are introduced.

## Verification — 2026-11-02

- **88 Angular tests across twenty files passed** using the temporary scoped configuration described below. Coverage includes automatic Tag entry, submenu placement/selection/hiding, guarded switches, exact category fields, labels and centralized description validation, duplicate prevention, draft retention, success/reset, real frontend HttpClient integration, narrow endpoint allowlisting, equivalent image/button routes and login invocation, and inert unavailable images. Existing functional registration/consultation/session/component suites passed.
- **Full npm test remains blocked by pre-existing untracked remnants**: `classification-quick-create.spec.ts`, `classification-order-confirmation.spec.ts` and `shared/pagination.spec.ts` refer to implementations removed by the owner's earlier reset. They were preserved. No unrelated feature was restored or tests deleted/skipped in tracked configuration. The scoped run used an ignored `frontend/.tmp/tag-ui-tests.tsconfig.json` extending `../tsconfig.spec.json` and excluding precisely these three files, together with matching CLI `--exclude` arguments.
- **One real PostgreSQL integration test passed in 10.298 seconds**: `test_frontend.BrowserCreationIntegrationTests.test_cookie_tag_category_creation_matches_openapi_and_audits`. It used only UUID-owned disposable infrastructure on approved QA port 2424, verified cookie/CSRF creation, persisted readback and one committed audit mutation, rejected invalid technical names/metadata/oversized descriptions, and completed fixture cleanup. Normal records were not used for writes.
- Nine Python frontend/session/asset checks passed; two opt-in integration methods were skipped in that separate nonintegration run. The new category integration method was executed successfully in the explicit disposable run above. Actual HTTP delivery matches the generated build-info and index build ID; the original migration-005 hash remains unchanged.
- Production build/provenance stamping passed: `949f414fe1107d03`. Initial assets total 374.89 kB, above the existing 350 kB warning and below the unchanged 450 kB error budget. Public query metadata still matches the three consultation contracts.
- **Browser/visual verification is pending.** Browser access reported an unavailable host; Computer Use could not connect its native pipe (`os error 2`). No rendered desktop/mobile, physical keyboard or login screenshot evidence is claimed. DOM routing tests and real HTTP integration are separate evidence.

Manual follow-up on owned disposable QA: use image and button routes from home and both intermediate pages; inspect login/permission behavior, keyboard focus and unavailable images; enter main Tag, switch both submenu directions, cancel/confirm dirty exits, verify submenu hiding and responsive appearance; create a category, exercise errors and repeat creation after success. Never seed normal data for these checks. QA scenario 19.4 records the sequence.
