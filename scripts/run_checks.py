"""Run mandatory automated QA checks with secret-free, catalogue-based reports."""
import argparse
from collections import Counter
import contextlib
from datetime import datetime, timezone
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
if str(ROOT/"scripts") not in sys.path: sys.path.insert(0, str(ROOT/"scripts"))
from qa_catalog import load_catalog, validate_catalog


class DiscardOutput(io.TextIOBase):
    """Discard arbitrary test output instead of risking credentials in artifacts."""
    def write(self, value): return len(value)
    def isatty(self): return False


class SafeResult(unittest.TestResult):
    """Track test/fixture states without formatting assertion text or locals."""
    def __init__(self):
        super().__init__()
        self.records = {}
        self.fixture_failures = {}

    def addSuccess(self, test):
        self.records.setdefault(test.id(), {"status": "PASS", "reason": "All assertions passed"})

    def addFailure(self, test, err):
        self.failures.append((test, "Assertion failure (details suppressed)"))
        self.records[test.id()] = {"status": "FAIL", "reason": "Assertion failed; reproduce the mapped test locally", "error_type": err[0].__name__}

    def addError(self, test, err):
        self.errors.append((test, "Execution error (details suppressed)"))
        identity = test.id()
        if identity.startswith(("setUpClass (", "tearDownClass (", "setUpModule (", "tearDownModule (")):
            phase = identity.split(" (", 1)[0]
            # unittest can label cleanup failures after a failed setup as setup
            # errors. Inspect function names only, never locals/source/error text.
            traceback = err[2]
            while traceback is not None:
                name = traceback.tb_frame.f_code.co_name
                if name == "doClassCleanups": phase = "tearDownClass"
                elif name == "doModuleCleanups": phase = "tearDownModule"
                traceback = traceback.tb_next
            fixture = identity.split("(", 1)[1].rstrip(")")
            self.fixture_failures.setdefault(fixture, []).append({"phase": phase, "error_type": err[0].__name__})
        else:
            self.records[identity] = {"status": "FAIL", "reason": "Test execution failed; raw exception text suppressed", "error_type": err[0].__name__}

    def addSkip(self, test, reason):
        # Even skip reasons can contain arbitrary test data; expose a fixed label.
        blocked = reason.startswith("BLOCKED:")
        safe_reason = "Earlier lifecycle preparation did not complete" if blocked else "Optional check unavailable or disabled"
        if reason.startswith("Port 6669 is occupied"):
            safe_reason = "Default database port 6669 is occupied; required integration used a temporary port"
        elif reason.startswith("Port 6969 is occupied"):
            safe_reason = "Default API port 6969 is occupied; existing service was left running"
        self.records[test.id()] = {"status": "BLOCKED" if blocked else "SKIP", "reason": safe_reason}

    def addSubTest(self, test, subtest, err):
        if err is not None:
            self.addFailure(test, err) if issubclass(err[0], AssertionError) else self.addError(test, err)

    def addExpectedFailure(self, test, err):
        self.records[test.id()] = {"status": "SKIP", "reason": "Expected failure does not establish a passing verification"}

    def addUnexpectedSuccess(self, test):
        self.unexpectedSuccesses.append(test)
        self.records[test.id()] = {"status": "FAIL", "reason": "Unexpected success requires test maintenance"}


def prerequisites():
    """Check tools without opening normal configuration or secret files."""
    checks = {"python": sys.version_info >= (3, 10)}
    modules = ("fastapi", "httpx", "uvicorn", "psycopg", "argon2", "jwt", "jsonschema", "yaml", "tzdata")
    checks["dependencies"] = all(importlib.util.find_spec(name) is not None for name in modules)
    checks["docker"] = False
    if shutil.which("docker"):
        try:
            checks["docker"] = all(subprocess.run(args, capture_output=True, timeout=30).returncode == 0
                                   for args in (["docker", "version"], ["docker", "compose", "version"]))
        except (OSError, subprocess.TimeoutExpired): pass
    return checks


def aggregate(catalog, records, fixture_failures, checks, unit_only=False):
    """Require every mapped test to pass; block dependent scenarios explicitly.

    Args:
        catalog: Public authoritative scenario definitions.
        records: Safe per-test results, with no credential values.
        fixture_failures: Fixture scopes with safe phase/category records.
        checks: Prerequisite availability flags.
        unit_only: Whether mandatory integration was intentionally omitted.

    Returns:
        Catalogue-ordered scenario results with independent manual status.
    """
    scenarios, by_id = [], {}
    for item in catalog["scenarios"]:
        result = {"id": item["id"], "name": item["name"], "type": item["type"],
                  "required": item.get("required", True), "tests": item["tests"],
                  "manual_status": "NOT_RECORDED" if item["type"] in ("manual", "both") else "NOT_APPLICABLE"}
        blocked_dependency = any(by_id.get(dep, {}).get("status") != "PASS" for dep in item.get("depends_on", []))
        affected = [event for scope, events in fixture_failures.items()
                    if scope == "runner" or any(selector.startswith(scope+".") for selector in item["tests"])
                    for event in events]
        if item["type"] == "manual":
            status, reason = "MANUAL", "Requires recorded human/interface evidence"
        elif any(event["phase"].startswith("tearDown") for event in affected):
            status, reason = "FAIL", "Mapped fixture teardown/cleanup failed; individual test results are retained"
        elif affected:
            status, reason = "BLOCKED", "Mapped fixture preparation did not complete"
        elif blocked_dependency:
            status, reason = "BLOCKED", "A prerequisite scenario did not pass"
        elif not checks.get("python") or not checks.get("dependencies"):
            status, reason = "BLOCKED", "Required Python/dependencies are unavailable"
        elif item.get("integration") and (unit_only or not checks.get("docker")):
            status, reason = ("SKIP", "Integration intentionally omitted (partial run)") if unit_only else ("BLOCKED", "Docker/Compose/Engine prerequisite is unavailable")
        else:
            states = []
            for selector in item["tests"]:
                record = records.get(selector)
                if record is None:
                    record = {"status": "BLOCKED", "reason": "Test not executed or its preparation failed"}
                states.append(record)
            if any(row["status"] == "FAIL" for row in states): status, reason = "FAIL", "At least one required mapped test failed"
            elif any(row["status"] == "BLOCKED" for row in states): status, reason = "BLOCKED", "Mapped test preparation/dependency did not complete"
            elif any(row["status"] == "SKIP" for row in states):
                status, reason = "SKIP", next(row["reason"] for row in states if row["status"] == "SKIP")
            else: status, reason = "PASS", "Every mapped automated verification passed"
        result.update(status=status, reason=reason)
        scenarios.append(result)
        by_id[item["id"]] = result
    return scenarios


def write_reports(report, directory):
    """Write only allowlisted result metadata, never captured output/tracebacks."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory/"results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    lines = ["# 🧪 **Ouroboros QA checks**", "", "**Automated mandatory checks:** "+("passed" if report["automated_checks_passed"] else "not passed"),
             "", "**Full QA approval: pending manual/interface evidence.**", "",
             "Scenario totals: `"+json.dumps(report["scenario_totals"])+"`", "",
             "Test totals: `"+json.dumps(report["test_totals"])+"`", "",
             "| ID | Scenario | Result | Reason | Manual evidence |", "| --- | --- | --- | --- | --- |"]
    for item in report["scenarios"]:
        lines.append(f'| {item["id"]} | {item["name"]} | **{item["status"]}** | {item["reason"]} | {item["manual_status"]} |')
    lines += ["", "Raw test output, exception messages, request bodies, configuration and credentials are deliberately excluded.",
              "Reproduce failures with the catalogue's mapped selectors in an isolated environment."]
    (directory/"summary.md").write_text("\n".join(lines)+"\n", encoding="utf-8")
    suite = ET.Element("testsuite", name="Ouroboros QA scenarios", tests=str(len(report["scenarios"])))
    for item in report["scenarios"]:
        case = ET.SubElement(suite, "testcase", classname="scenario."+item["id"], name=item["id"]+" - "+item["name"])
        if item["status"] == "FAIL": ET.SubElement(case, "failure", message=item["reason"])
        elif item["status"] == "BLOCKED" and item["required"]: ET.SubElement(case, "error", message=item["reason"])
        elif item["status"] in ("SKIP", "MANUAL", "BLOCKED"): ET.SubElement(case, "skipped", message=item["status"]+": "+item["reason"])
    suite.set("failures", str(len(suite.findall("testcase/failure"))))
    suite.set("errors", str(len(suite.findall("testcase/error"))))
    suite.set("skipped", str(len(suite.findall("testcase/skipped"))))
    ET.ElementTree(suite).write(directory/"junit.xml", encoding="utf-8", xml_declaration=True)


def main(argv=None):
    """Run isolated checks and return failure for incomplete mandatory automation."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preflight-only", action="store_true", help="Check tools only; this is not QA approval")
    parser.add_argument("--unit-only", action="store_true", help="Partial diagnostic run; mandatory integration remains incomplete")
    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"): stream.reconfigure(encoding="utf-8", line_buffering=True)
    checks = prerequisites()
    for name, available in checks.items(): print(f'[PREP] {name}: '+("available" if available else "unavailable"))
    if args.preflight_only: return 0 if all(checks.values()) else 1
    catalog = load_catalog()
    consistency = validate_catalog(catalog)
    result = SafeResult()
    start = time.monotonic()
    os.environ["FOUNDATION_RUN_INTEGRATION"] = "1" if checks["docker"] and not args.unit_only else "0"
    if checks["python"] and checks["dependencies"] and not consistency:
        with contextlib.redirect_stdout(DiscardOutput()), contextlib.redirect_stderr(DiscardOutput()):
            try:
                suite = unittest.defaultTestLoader.discover(str(ROOT/"tests"))
                suite.run(result)
            except (Exception, KeyboardInterrupt):
                # Still emit artifacts on loader/runner cancellation without raw data.
                result.fixture_failures["runner"] = [{"phase": "runner", "error_type": "RunnerInterrupted"}]
    records = result.records
    for selector in {test for item in catalog["scenarios"] for test in item["tests"]}:
        if selector not in records:
            records[selector] = {"status": "BLOCKED", "reason": "Preparation did not complete; test was not executed"}
            for fixture, events in result.fixture_failures.items():
                if selector.startswith(fixture+"."):
                    records[selector].update(reason="Mapped fixture preparation failed", error_type=events[0]["error_type"])
    scenarios = aggregate(catalog, records, result.fixture_failures, checks, args.unit_only)
    good = (not consistency and not result.fixture_failures and not result.failures and not result.errors
            and not result.unexpectedSuccesses and all(checks.values()) and not args.unit_only
            and all(row["status"] == "PASS" for row in scenarios if row["required"] and row["type"] != "manual"))
    def totals(rows):
        counts = Counter(row["status"] for row in rows)
        return {key: counts[key] for key in ("PASS", "FAIL", "SKIP", "BLOCKED", "MANUAL")}
    report = {"schema_version": 1, "created_at": datetime.now(timezone.utc).isoformat(),
              "duration_seconds": round(time.monotonic()-start, 3), "prerequisites": checks,
              "automated_checks_passed": good, "qa_approval": "PENDING_MANUAL_VALIDATION" if good else "NOT_APPROVED",
              "partial": args.unit_only, "consistency_errors": consistency,
              "scenario_totals": totals(scenarios),
              "test_totals": totals(records.values()),
              "tests_executed": result.testsRun, "fixture_failures": result.fixture_failures,
              "scenarios": scenarios, "tests": records}
    write_reports(report, ROOT/"reports")
    for row in scenarios: print(f'[{row["status"]}] {row["id"]} - {row["name"]}')
    print("Scenario totals: "+json.dumps(report["scenario_totals"]))
    print("Test totals: "+json.dumps(report["test_totals"]))
    print("Reports: reports/summary.md, reports/results.json, reports/junit.xml")
    print("Mandatory automated checks passed; manual QA remains pending." if good else "Mandatory automated checks are incomplete or failed; this is not full approval.")
    return 0 if good else 1


if __name__ == "__main__":
    raise SystemExit(main())
