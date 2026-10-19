"""Verify aggregation, blocked dependencies and report secrecy without Docker."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import contextlib
import io

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"scripts"))
from run_checks import SafeResult, aggregate, write_reports, main


def scenario(identity, tests, **extra):
    return {"id": identity, "name": "Scenario "+identity, "type": "both", "tests": tests, **extra}


class QARunnerTests(unittest.TestCase):
    def test_all_mapped_checks_required_and_dependencies_block(self):
        catalog = {"scenarios": [scenario("1.1", ["one", "two"]), scenario("1.2", ["three"], depends_on=["1.1"])]}
        checks = {"python": True, "dependencies": True, "docker": True}
        records = {"one": {"status": "PASS"}, "two": {"status": "FAIL"}, "three": {"status": "PASS"}}
        rows = aggregate(catalog, records, {}, checks)
        self.assertEqual([row["status"] for row in rows], ["FAIL", "BLOCKED"])
        records["two"]["status"] = "PASS"
        self.assertTrue(all(row["status"] == "PASS" for row in aggregate(catalog, records, {}, checks)))
        del records["two"]
        self.assertEqual(aggregate(catalog, records, {}, checks)[0]["status"], "BLOCKED")

    def test_missing_prerequisite_partial_and_manual_are_not_pass(self):
        catalog = {"scenarios": [scenario("1.1", ["one"], integration=True), scenario("1.2", [], type="manual")]}
        checks = {"python": True, "dependencies": True, "docker": False}
        records = {"one": {"status": "PASS"}}
        self.assertEqual([row["status"] for row in aggregate(catalog, records, {}, checks)], ["BLOCKED", "MANUAL"])
        checks["docker"] = True
        self.assertEqual(aggregate(catalog, records, {}, checks, unit_only=True)[0]["status"], "SKIP")
        with tempfile.TemporaryDirectory() as directory, patch("run_checks.ROOT", Path(directory)), \
             patch("run_checks.prerequisites", return_value={"python":True,"dependencies":False,"docker":False}), \
             patch("run_checks.load_catalog", return_value={"scenarios":[scenario("1.1",["one"])]}), \
             patch("run_checks.validate_catalog", return_value=[]), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main([]), 1)
            report = json.loads((Path(directory)/"reports/results.json").read_text())
            self.assertFalse(report["automated_checks_passed"])
            self.assertEqual(report["scenarios"][0]["status"], "BLOCKED")

    def test_failure_output_and_reports_exclude_secrets(self):
        secret = "password-token-hash-must-not-reach-artifacts"
        class Dummy(unittest.TestCase):
            def runTest(self): raise RuntimeError(secret)
        result = SafeResult()
        Dummy().run(result)
        self.assertEqual(next(iter(result.records.values()))["status"], "FAIL")
        report = {"automated_checks_passed": False, "scenario_totals": {"FAIL": 1}, "test_totals": {"FAIL": 1},
                  "scenarios": [{"id": "1.1", "name": "Safe failure", "status": "FAIL", "reason": "Test execution failed", "manual_status": "NOT_RECORDED", "required": True}],
                  "tests": result.records}
        with tempfile.TemporaryDirectory() as directory:
            write_reports(report, Path(directory))
            for path in Path(directory).iterdir():
                self.assertNotIn(secret, path.read_text(encoding="utf-8"))
            self.assertEqual(json.loads((Path(directory)/"results.json").read_text())["test_totals"], {"FAIL": 1})

    def test_fixture_failures_and_lifecycle_skips_are_blocked(self):
        result = SafeResult()
        class Dummy(unittest.TestCase):
            def runTest(self): self.skipTest("BLOCKED: prior phase failed with private content")
        Dummy().run(result)
        self.assertEqual(next(iter(result.records.values()))["status"], "BLOCKED")
        self.assertNotIn("private content", str(result.records))
        class Broken(unittest.TestCase):
            @classmethod
            def setUpClass(cls): raise RuntimeError("private-fixture-password")
            def runTest(self): self.fail("Must not execute")
        fixture_result = SafeResult()
        unittest.TestSuite([Broken()]).run(fixture_result)
        self.assertTrue(fixture_result.fixture_failures)
        self.assertEqual(fixture_result.testsRun, 0)
        self.assertNotIn("private-fixture-password", str(fixture_result.fixture_failures))
        skipped = SafeResult()
        class OccupiedPort(unittest.TestCase):
            def runTest(self): self.skipTest("Port 6669 is occupied; private untrusted suffix")
        OccupiedPort().run(skipped)
        detail = next(iter(skipped.records.values()))
        self.assertIn("6669 is occupied", detail["reason"])
        self.assertNotIn("private untrusted suffix", detail["reason"])

    def test_class_and_module_fixture_aggregation(self):
        checks = {"python":True,"dependencies":True,"docker":True}
        selectors = ["example.A.test_one", "example.B.test_two", "other.C.test_three"]
        catalog = {"scenarios":[scenario(str(i+1)+".1", [selector]) for i, selector in enumerate(selectors)]}
        records = {selector:{"status":"PASS"} for selector in selectors}
        for phase in ("setUpClass", "tearDownClass", "setUpModule", "tearDownModule"):
            scope = "example" if phase.endswith("Module") else "example.A"
            failures = {scope:[{"phase":phase,"error_type":"RuntimeError"}]}
            rows = aggregate(catalog, records, failures, checks)
            expected = "FAIL" if phase.startswith("tearDown") else "BLOCKED"
            self.assertEqual(rows[0]["status"], expected)
            self.assertEqual(rows[1]["status"], expected if phase.endswith("Module") else "PASS")
            self.assertEqual(rows[2]["status"], "PASS")
            self.assertTrue(all(record["status"] == "PASS" for record in records.values()))

    def test_real_teardown_failure_cannot_leave_scenario_pass(self):
        class CleanupFailure(unittest.TestCase):
            def runTest(self): pass
            @classmethod
            def tearDownClass(cls): raise RuntimeError("private-cleanup-secret")
        test = CleanupFailure()
        result = SafeResult()
        unittest.TestSuite([test]).run(result)
        self.assertEqual(result.records[test.id()]["status"], "PASS")
        catalog = {"scenarios":[scenario("1.1", [test.id()])]}
        rows = aggregate(catalog, result.records, result.fixture_failures, {"python":True,"dependencies":True,"docker":True})
        self.assertEqual(rows[0]["status"], "FAIL")
        report = {"automated_checks_passed":False,"scenario_totals":{"FAIL":1},"test_totals":{"PASS":1},
                  "scenarios":rows,"tests":result.records,"fixture_failures":result.fixture_failures}
        with tempfile.TemporaryDirectory() as directory:
            write_reports(report, Path(directory))
            for file in Path(directory).iterdir(): self.assertNotIn("private-cleanup-secret",file.read_text(encoding="utf-8"))
        class SetupAndCleanupFailure(unittest.TestCase):
            @classmethod
            def setUpClass(cls):
                def cleanup(): raise ValueError("private-failed-setup-cleanup")
                cls.addClassCleanup(cleanup)
                raise RuntimeError("private-preparation-secret")
            def runTest(self): self.fail("Must not execute")
        test = SetupAndCleanupFailure()
        result = SafeResult()
        unittest.TestSuite([test]).run(result)
        events = next(iter(result.fixture_failures.values()))
        self.assertEqual({event["phase"] for event in events},{"setUpClass","tearDownClass"})
        rows = aggregate({"scenarios":[scenario("1.1",[test.id()])]},result.records,result.fixture_failures,
                         {"python":True,"dependencies":True,"docker":True})
        self.assertEqual(rows[0]["status"],"FAIL")
        self.assertNotIn("private-failed-setup-cleanup",str(result.fixture_failures))
