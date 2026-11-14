# Database delivery one: verification record

Execution date: 2026-11-12. No staging, commit, push or merge was performed.
Existing unrelated working-tree changes were retained. README.md was not edited
by this delivery. Historical migration files 001-011 were not edited; the final
`git diff --exit-code -- modules/database/sql/migrations` passed.

## Executed checks

- `python start.py --check`: passed, strict commented examples copied to ignored
  local files; no PostgreSQL changes.
- `python -S start.py --help`: passed without host site packages; startup defers
  Psycopg/Argon2 imports until real database startup.
- `python -m unittest discover -s modules/database/qa -p test_settings.py -v`:
  **7 passed**. Includes nested duplicate-key rejection, strict types/unknown
  fields, naming collisions, alternate vocabulary, human-password policy,
  comment-insensitive identity, interactive prefix correction preserving comments,
  and noninteractive/already-allocated refusal to repair prefixes.
- `python -m unittest discover -s modules/database/qa -p test_postgres.py -v`:
  **16 passed**, using real PostgreSQL 17.11 Docker containers and new UUID-owned
  volumes, independently on explicit disposable ports **2424** and **4242**.
  Every startup used the real database launcher/Compose file, with QA-only
  injection of isolated project names and the explicitly approved QA port.
  Input names/password prompting were simulated with random per-run secrets;
  no normal credentials or secret files were read.
- `python -m unittest discover -s tests -p test_module_architecture.py -v`:
  **9 passed**, including the updated database-only launcher help assertion.
- Scoped `git diff --check`: passed.

Both real database installations checked:

1. First schema creation; interruption during Argon2 hashing after person/API
   inserts; complete transactional enrollment rollback; successful resumed start.
2. Second start with no reenrollment, migration reapplication or extra audit
   writes; one registry version and one reserved holder.
3. Plan 1 with Database + API Integration, plus separate optional module records.
4. Singleton enforcement and prohibition of ordinary reserved role/permission.
5. All 43 tables' textual IDs, sequence and prefix columns; seven-digit padding,
   growth to eight digits without truncation and immutable identity sources.
6. Administrative TCP authentication, including wrong-password rejection in the
   default-vocabulary installation; migration/runtime privilege separation.
7. Work-platform uniqueness; same-work availability; multiple history sessions;
   rejection of cross-owner tag/personal-session references and ownership changes.
8. Same-transaction audit/version evidence and rollback when actor evidence fails.
9. Structural prefix/schema/vocabulary/width changes rejected; startup checks a
   changed structure before any Compose `up` operation.
10. Ordinary actor cannot change the plan; the active reserved holder can.
11. Membership history protected against deletion/start-date rewrite; effective
    Docker health interval, timeout and retry values match configuration.
12. The same model under work=`book`, activity=`read` (including derived IDs and FKs).

The initial alternate-vocabulary test incorrectly attempted to change `book` to
itself; its expected rejection failed. The test was corrected to change to
`magazine` and the complete integration suite passed afterward.

## Existing general suite and limitations

`python scripts/run_checks.py` was attempted. Its existing catalogue consistency
gate refused execution because three speech tests in the pre-existing worktree
are not mapped in qa/scenarios.json. No full QA approval is claimed.

`python -m unittest discover -s tests -v` ran **220 tests**, with **67 skipped**,
**5 failures** and **6 errors** in that run. One failure expected the retired
`--api-only` launcher option; the assertion was updated to `--database-only` and
the entire nine-test architecture module passed on a targeted repeat. The other
failures/errors concern existing speech tests missing `av`/`ctranslate2` in the
host environment and the three unmapped speech tests. Those unrelated workflows
were not changed. The full historical suite was not subsequently claimed green.

Real terminal echo suppression, physical Ctrl+C interaction, and DBeaver/pgAdmin
GUI connection were not manually exercised. Automated SQL TCP authentication
does not prove SQL-client GUI behavior. The normal new installation was not
enrolled on the operator's behalf: real personal identity and passwords must be
entered privately at the documented first-start prompts.

## Resource preservation

Inspection identified the previous `ouroboros` project as belonging to
C:\Dev\Ouroboros, with PostgreSQL volume `ouroboros_postgres_data`; Foundation
uses its separate `foundation_postgres_data`. Neither volume was removed,
replaced, mounted into a test or mutated for QA. Startup contains no resource
stop/remove/prune behavior. Final inspection confirmed both historical volumes
remain and no UUID QA container or volume remains. Cleanup removed only the exact
UUID projects/volumes allocated by the integration test. Protected temporary
test secrets remain under ignored .tmp test fixture directories.

Use the commands and administrative connection fields in [DATABASE.md](DATABASE.md)
for the real installation. If 6669 is occupied at that time, inspect ownership
again and deliberately retire the previous service; no automatic alternate port
or process termination is provided.
