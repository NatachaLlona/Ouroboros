# Exact-byte migration recovery after branch changes

## Confirmed incident — 2026-10-30

The investigation began on branch `feat/base-frontend`, HEAD `48fff16c858b0971ab94b165ec8a8ab448feb2a4`, with a clean Git working tree. `app/migrate.py` hashes `path.read_bytes()` with SHA-256 and compares it with `public.foundation_migrations.checksum` before skipping an applied migration. This intentionally includes newline and BOM bytes.

The owner ran the privately authenticated, read-only registry diagnostic. Exactly **005_create_catalogue.sql** diverged; the other ten migrations matched.

| Representation | Bytes | Newlines | SHA-256 |
|---|---:|---|---|
| Git/current checkout before recovery | 12738 | 196 LF | `c6eae4a4c95769dbe7f5d223e3ffc45d3acdb88a121f50a5ea9a6c37548a78fb` |
| Applied original, present in both backups | 12934 | 196 CRLF | `ea1bc7ac811e1cea68b0b3ce60a122aea9e8c84fce2e7065223622b3c249c101` |

Neither version has a BOM. SQL text is identical after newline-only comparison. Git history has one functional version of migration 005 (commit `ca7d3bc`), stored with LF. Both `C:\Dev\Ouroboros.zip` and `reports/Ouroboros-final-review.zip` contain identical CRLF originals whose raw SHA-256 equals the **actual database registry value**. The checkout had all migrations in LF and `core.autocrlf=input`; normalization into the Git blob and a later branch checkout explain the byte-only mismatch. No functional SQL alteration was found. The investigation does not claim to reconstruct which individual checkout/merge command rewrote the working file.

Recovery restored migration 005 from those proven backup bytes. Before writing, it checked the report's HEAD, current file hash, both independent archive contents and the stored checksum. The previous LF file remains under `reports/migration_recovery/005_create_catalogue.before-c6eae4a4c95769dbe7f5d223e3ffc45d3acdb88a121f50a5ea9a6c37548a78fb.sql`. All **11** current migration files now match the registry snapshot supplied by the owner. `git diff --ignore-space-at-eol -- sql/migrations/005_create_catalogue.sql` is empty. No new migration is needed because SQL behavior did not change.

The integrity comparison, registry checksums and applied timestamps were not changed. The normal database, accounts, credentials, catalogue, container and volume were not modified, recreated or reset. The normal registry was accessed only by SELECT in a read-only transaction using the owner's interactive password. No saved secret was inspected.

## Prevention and diagnosis

`.gitattributes` marks `sql/migrations/*.sql -text`, preserving committed raw migration bytes across checkout platforms instead of applying newline conversion. Its whitespace attribute retains the usual whitespace checks while recognizing CRLF as line terminators. This is a source-file rule, not a normalization exception in the migrator. Do not renormalize applied migration files, run mass formatters over them or update registry hashes to match edited files. Review byte-only changes before any separately authorized Git publication.

`app/migrate.py` now identifies the modified migration in its exception message. The SHA-256 comparison remains strict. Startup's generic safe logs still omit arbitrary exception messages; use the dedicated diagnostic for public version/hash evidence.

```powershell
cd C:\Dev\Ouroboros
.\.venv\Scripts\python.exe scripts/diagnose_migrations.py
.\.venv\Scripts\python.exe scripts/diagnose_migrations.py --database
```

The first command compares public SQL files with Git history and the two known backups; it returns **2 / NOT_VERIFIED** until registry evidence is available. The second requests the existing PostgreSQL password only in the terminal, reads version/checksum rows in a repeatable-read **READ ONLY** transaction, and writes a public diagnostic report under reports/. It neither runs migrate() nor writes registry records, catalogue data, configuration or credentials. Exit 1 means divergence; exit 0 means the inspected files match; exit 3 means diagnosis could not complete. Raw driver exceptions and connection details are not printed. Do not put passwords in arguments or chat.

If no candidate matches the exact stored SHA-256, **stop recovery**. Obtain the original source or backup; never substitute a normalized hash, whitelist another hash, change the registry or disable the integrity check. If proven restoration removes a necessary functional change, reimplement that change as a new numbered migration after reviewing its transaction/data implications.

## Verification and remaining owner step

Unit checks cover byte-distinct LF/CRLF, BOM detection, strict rejection before migration SQL/registry insertion, filename diagnostics and the SELECT-only credential-prompting path. Disposable PostgreSQL integration applies the complete migration sequence, changes migration 005's line endings, verifies rejection and unchanged existing data/version/checksum/applied_at rows, restores exact bytes and verifies repeatability/persistence. Tests use only approved disposable 2424 PostgreSQL / 2469 HTTP; no existing normal infrastructure is recreated.

Evidence: `reports/migration_integrity_diagnosis.json` (before recovery), `reports/migration_integrity_after.json` (all eleven match the owner's registry snapshot), `reports/migration_integrity_unit.txt` and `reports/migration_integrity_integration.txt`. These reports contain public migration metadata, not credentials or descriptions.

Actual final checks: **8 unit tests passed**; **1 real PostgreSQL integration test passed** in 69.253 seconds after restoring the final CRLF source. This integration includes complete initial application, byte-change rejection, exact restoration, repeat application, persistence and existing API checks in owned disposable infrastructure. QA catalogue/generated plan, canonical/embedded Postman synchronization, attributes and whitespace checks passed. The public review-package allowlist now includes .gitattributes so the byte-preservation rule is not lost from source packages. No frontend build was required for this migration-only repair.

Normal startup still requires the owner's interactive credentials and was deliberately left to the owner:

```powershell
cd C:\Dev\Ouroboros
.\.venv\Scripts\python.exe start.py
```

Confirm that the migrations stage completes and existing records remain available. The source mismatch is repaired; successful normal authenticated startup is not claimed until this step is executed. No staging, commit, push or merge was performed.

## Recurrence after hard reset ? 2026-11-02

The owner restored feat/base-frontend with fetch/reset --hard. Current HEAD remains 48fff16c858b0971ab94b165ec8a8ab448feb2a4. The working tree had no tracked modifications; prior untracked recovery/UI files were left intact. No stash was applied and no unrelated frontend work was restored.

Migration 005 was again the only mismatch against the previously authenticated registry export reports/migration_registry_checksums.json. HEAD contains 12738 bytes/196 LF with hash c6eae4a4c95769dbe7f5d223e3ffc45d3acdb88a121f50a5ea9a6c37548a78fb. Stash 41f0e4a contains 12934 bytes/196 CRLF with hash ea1bc7ac811e1cea68b0b3ce60a122aea9e8c84fce2e7065223622b3c249c101, identical to both original archive copies and the prior registry export. SQL text after newline comparison is identical. This establishes that resetting to HEAD replaced the earlier exact-byte local restoration; no functional migration edit was found.

The original archive bytes were restored after checking HEAD, pre-repair hash, both archive contents and the known registry checksum. The LF file was retained at reports/migration_recovery_20261102/005_create_catalogue.before.sql. All eleven files then matched the prior export. No SQL was executed by this source repair; no registry checksum/applied_at, catalogue data or volume was rewritten. Filename diagnostics in app/migrate.py were restored without weakening its strict raw SHA-256 comparison.

Nine database unit tests and ten startup-safety tests passed. One real PostgreSQL integration test passed in 68.456 seconds, including complete migration application, private-copy newline alteration/rejection, original-byte recovery, unchanged registry checksums/applied_at and preserved records across restart in disposable storage on approved ports 2424/2469. The owner then completed the authenticated SELECT-only diagnostic: reports/migration_live_20261102.json confirms MATCH for all eleven current files against the live public.foundation_migrations registry. Normal authenticated startup remains separate evidence until the owner completes its private prompts. The visible verification terminal runs the diagnostic first and executes start.py only on a match; no saved credentials are extracted.

The .gitattributes rule protects future committed byte representations from newline conversion; it does not prevent a later hard reset from replacing uncommitted recovery bytes with the LF version still stored in HEAD. No staging, commit, push, merge or branch switching was performed.

### Normal authenticated startup verified ? 2026-11-02

The owner completed the existing private terminal prompts. The normal startup log application_2026-11-02_202212_fdf2a73f.log records Database connection validated, Database migrations completed and Ouroboros preparation completed, without the migration-integrity error. A subsequent GET http://127.0.0.1:6969/health returned HTTP 200 with {"status":"ok"}. The normal server was left running. This completes the startup check that was pending above. No credentials were extracted or included in this evidence; no registry checksums were changed.
