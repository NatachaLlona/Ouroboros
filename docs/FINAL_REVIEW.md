# 🔎 **Foundation final review — 2026-10-19**

Foundation retains its name and reusable project structure. No commit or push was performed. The working tree already contained substantial earlier work; this review preserves it and does not alter private Postman files, normal configuration, secrets, logs or application data.

## 🛠️ **Changes delivered**

- Swagger explicitly describes GET `/test` id/value filters and shared pagination, with examples, defaults and bounds. GET `/users` supports **only pagination**; no account filters exist in its implementation or documented contract. Authorize once and reuse authentication for subsequent permitted calls.
- The canonical JSON already had one List all entries request. Historical local YAML copies are separate, personal artifacts and were left alone. Request **61** demonstrates page=2/page_size=10 with editable Params and unchecked id/value filters. Existing ID/pattern/AND requests remain. Requests **62–76** provide a separate disposable-account reset sequence. All versioned credential/token/ID variables remain empty.
- PUT `/users/{id}/password` resets another account using a strict SecretStr new_password and Argon2id. The transaction shares the administration advisory lock, revalidates actor role/state/version, locks the target and increments only its credential_version. Self-targeting is **400**, directing the caller to `/users/me/password` with current-password verification. Missing user **404**, invalid input **422**, missing/revoked authentication **401**, standard caller **403**, success empty **204**.
- Reset bodies are excluded entirely from logging, including malformed input. Committed/rejected transactional audit events identify actor, target and outcome under the generated interaction ID. Pre-endpoint authentication/schema failures retain generic safe rejection/final events rather than inventing a verified actor audit.
- The catalogue, generated manual plan, setup instructions, canonical collection, embedded README JSON and architecture/API/developer guides are synchronized. Existing self-service regression coverage remains.

## 🧪 **Checks actually executed**

| Check | Observed result |
| --- | --- |
| Focused endpoint unittest module | **19 passed** |
| Focused canonical Postman checks | **5 passed**; schema, uniqueness, pagination Params, encoding and embedded JSON |
| Full `scripts/run_checks.py` | **98 tests passed**, none failed/skipped/blocked; **36 automated scenarios passed**, **4 manual** |
| Real isolated PostgreSQL tests | Passed, including reset/token/password behavior, stale/demoted actor rejection, reset versus self-service race, existing role races, persistence, cleanup and project isolation |
| Generated QA plan `--check` | Passed |
| `compileall` for app/scripts/start.py | Passed |
| `pip check` | No broken requirements |
| `git diff --check` | Passed; Git printed existing line-ending normalization notices |
| SQL source inspection and AST check | Values parameterized; no f-string passed directly to execute in 26 application modules; dynamic database identifiers use Psycopg Identifier |
| Initial full-run attempt | Docker prerequisite temporarily failed; correctly returned nonzero/incomplete. Subsequent CLI diagnosis succeeded and the full rerun above passed |

The test runner provisions UUID-owned disposable infrastructure with random credentials and available ports. Cleanup is limited to exact resources created by each fixture. No normal database was queried to claim a before/after fingerprint; preservation here means the review did not target normal data, and isolation/persistence behavior was tested on disposable data.

## 🛡️ **Static analysis and security findings**

**SonarLint / SonarQube for IDE did not run.** `code --list-extensions` and the standard VS Code extension inventory showed no Sonar extension. The fallback scans below are not Sonar scans.

| Tool / scope | Result and disposition |
| --- | --- |
| Bandit **1.9.4**, `app` and `start.py` | No skipped files, **0 high**, **0 medium**, **6 low** findings |
| B105, auth token type `bearer` | False positive: a public protocol label, not a hardcoded credential |
| B404 ×2 and B603 ×2, credentials/database subprocesses | Reviewed: argument lists, shell=False, bounded timeouts, safe error translation; SQL/filter/password input is not interpolated into shell text. These review warnings remain visible, without blanket suppression |
| B607, `whoami.exe` partial executable path | Residual low-severity reliance on the local executable search path. Proposed absolute-system-path hardening was rejected by the editing tool and was **not applied**. No reason beyond rejection was provided; no bypass was attempted |
| pip-audit **2.10.1**, `-r requirements-dev.txt` | **32 resolved distributions**, no known vulnerabilities |
| pip-audit **2.10.1**, `--local` | **61 installed distributions**, no skipped distributions and no known vulnerabilities |

The fallback tools were installed into the project virtual environment for this review. Reproduce with `python -m pip install bandit==1.9.4 pip-audit==2.10.1`, then `python -m bandit -r app start.py` and `python -m pip_audit --local`. Requirement-file auditing resolves allowed transitive versions; the separate installed audit covers actual local versions. These database-backed advisory results are time-sensitive and do not prove the absence of security vulnerabilities.

Implementation review covered current database role enforcement, required JWT claims/version revocation, parameterized SQL, secret-safe schemas/errors/logging, transaction/row/advisory lock order, bounded connections and cleanup, protected initialization storage and explicit workspace/Compose ownership. The new reset path closes its authorization race by rechecking the actor version inside the locked transaction. Successful resets revoke all earlier target tokens without rotating the shared key or affecting peers. Requests authorized before commit may still finish; revocation does not cancel in-flight work.

The existing strict nonempty-string password policy is reused; this change does not establish a stronger length/complexity policy. The existing Starlette warning about HTTPX TestClient deprecation remains; tests pass, and migration to the recommended client remains future maintenance.

## 🧑‍🔬 **Remaining approval evidence**

The user previously confirmed Swagger authorization via **Authorize**. This review executed OpenAPI/HTTP checks and did **not** rerun that interface. Newly described filter/pagination controls still require visual verification under scenario **6.1**. Scenario **6.2** requires actual Postman import, checkbox rendering and JavaScript sandbox execution; HTTP collection replay does not establish those results. Scenario **6.3** requires the physical terminal; **6.4** requires an actual hosted workflow run URL and downloaded artifacts. No hosted workflow was dispatched.

**Concrete remaining items:** complete those four manual/interface checks, review the residual low-severity executable-path finding, and review the source ZIP before the separately authorized final commit. There is no remaining failing automated check.

## 📦 **Review package**

Run `python scripts/package_review.py` after the full checks to create ignored **reports/Foundation-final-review.zip**. It includes allowlisted public source, documentation, the canonical JSON and sanitized summary/results/JUnit evidence. It excludes local configuration, `.secrets`, logs, private Postman YAML/metadata, virtual environments and Git history. It is a source snapshot for a fresh isolated installation, not a data backup or a replacement for the current local configuration.
