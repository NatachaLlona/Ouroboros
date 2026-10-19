# Development instructions

Read and follow `NEXTGENERATION.md` in the repository root before developing Ouroboros or suggesting or executing Git commands.

- Keep `README.md` as the project introduction and `NEXTGENERATION.md` as the developer guide.
- Update `NEXTGENERATION.md` whenever new development rules are established or existing rules change.
- Write code identifiers (including variables and classes), comments, log messages, and documentation in English.
- Use `git add --all` for staging. Before every commit, run `git status` and review `git diff --cached`.
- Write commit messages in English using `type(scope): description`, following the types, scopes, and writing rules in `NEXTGENERATION.md`.
- Only commit or push when the user requests it.

## Permanent security conventions

Read [the audit/datetime/bulk contracts](docs/AUDIT_DATETIME_BULK.md). Consult official [OWASP ASVS](https://owasp.org/projects/asvs) and [Cheat Sheet Series](https://cheatsheetseries.owasp.org/) Authentication, Authorization, Password Storage, Logging, Input Validation and Error Handling sources when making security decisions. Concrete checks: deny by default/current account authorization; transaction-time mutation authority; parameterized SQL/whitelisted identifiers; Argon2id; current-password self change; administrator reset of another user; credential-version revocation; bounded recursive redaction; whole token/password body omission; read-only protected audits; standardized safe errors; atomic audit/business rollback. Never expose passwords, hashes, tokens, keys or connection strings. No GET password endpoint: future recovery resets passwords rather than retrieving/emailing them. No blanket OWASP-compliance claim.

Use shared UTC datetime code, preserve unknown historical dates/context, and keep friendly presentation read-only. Do not bypass central auditing or its mandatory mutation triggers. Keep bulk filters strict, actual mutations confirmed, previews nonmutating, and administrator authority rechecked in the transaction. Test destructive flows only in owned disposable infrastructure; never seed or mutate normal data for QA.

## 🪜 Classification tiers and complete test CRUD

- Keep classification tiers independent of identity sequences after migration009; never bulk assign one tier. Reorder under membership, actor, list and record locks with deferred uniqueness and same-transaction audit evidence for every shift.
- Preserve current test:read/test:write scope checks and repeat mutation authority checks inside the transaction. Bulk test changes require administrator, strict filters and confirmation; previews remain nonmutating.
- Normal migration/read validation must use the user's existing interactive credentials; never extract secrets or replace the nine normal classifications. Identify a listener's executable/launch ownership before any restart; leave unconfirmed processes alone.

Migrations009–010 add independent classification tier positions and complete integer-ID test CRUD with shared creation dates, UTC presentation, strict filters and confirmed administrator bulk operations. See [the authoritative contracts](docs/TIERS_AND_TEST_CRUD.md) for the one-time inspected backfill, atomic append/insert/move/delete behavior, bulk tier exception, scope matrix and restart instructions. Never reseed or replace the existing nine normal classifications. Destructive QA remains isolated; review measurements and findings are documented separately.
