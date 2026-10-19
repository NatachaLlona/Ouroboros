"""Keep catalogue, generated plan, Postman identities and CI runner aligned."""
import json
from pathlib import Path
import sys
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/"scripts"))
from qa_catalog import load_catalog, render_plan, validate_catalog


class QATraceabilityTests(unittest.TestCase):
    def test_catalogue_and_generated_plan(self):
        catalog = load_catalog()
        self.assertEqual(validate_catalog(catalog), [])
        self.assertEqual((ROOT/"docs/QA_TEST_PLAN.md").read_text(encoding="utf-8"), render_plan(catalog))
        import ast
        literals = {node.value for path in [ROOT/"start.py",*(ROOT/"app").rglob("*.py")]
                    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
                    if isinstance(node,ast.Constant) and isinstance(node.value,str)}
        for scenario in catalog["scenarios"]:
            self.assertTrue(scenario["log_evidence"]["locate"])
            self.assertTrue(scenario["log_evidence"]["forbidden_data"])
            for rule in scenario["log_evidence"]["events"]:
                self.assertIn(rule["message"],literals)

    def test_collection_traceability_and_empty_credentials(self):
        catalog = load_catalog()
        collection = json.loads((ROOT/"postman/Foundation.postman_collection.json").read_text(encoding="utf-8"))
        def visit(items):
            for item in items:
                if "item" in item: yield from visit(item["item"])
                else: yield item
        requests = list(visit(collection["item"]))
        for item in requests:
            ids = [scenario for scenario in catalog["scenarios"] if item["name"] in scenario.get("postman_requests", [])]
            self.assertTrue(ids, item["name"])
            for scenario in ids:
                identity = scenario["id"]+" - "+scenario["name"]
                self.assertIn(identity, item["request"]["description"])
                script = next(event["script"]["exec"] for event in item["event"] if event["listen"] == "test")
                self.assertIn(identity, "\n".join(script))
        for variable in collection["variable"]:
            if variable["key"] != "base_url": self.assertEqual(variable["value"], "")

    def test_pipeline_uses_same_runner_and_sanitized_artifacts(self):
        path = ROOT/".github/workflows/qa-checks.yml"
        workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
        # PyYAML's YAML 1.1 parser treats unquoted 'on' as a boolean; the workflow
        # quotes that key so the verified structure matches GitHub's YAML parser.
        self.assertIn("workflow_dispatch", workflow["on"])
        self.assertEqual(workflow["permissions"], {"contents": "read"})
        job = workflow["jobs"]["qa"]
        self.assertTrue(job["timeout-minutes"])
        steps = job["steps"]
        self.assertTrue(any("scripts/run_checks.py" in step.get("run", "") and "--preflight-only" not in step["run"] for step in steps))
        uploads = [step for step in steps if "upload-artifact" in step.get("uses", "")]
        self.assertEqual(len(uploads), 1)
        self.assertEqual(uploads[0]["if"], "always()")
        self.assertEqual(set(uploads[0]["with"]["path"].splitlines()), {"reports/summary.md", "reports/results.json", "reports/junit.xml"})
        self.assertNotIn("secrets.", path.read_text(encoding="utf-8"))
