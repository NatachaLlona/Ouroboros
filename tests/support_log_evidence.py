"""Assert catalogue-defined request evidence against actual sanitized log events."""
import json
import re
from app.config import PROJECT_ROOT


def assert_response_logs(test, response, output, logger):
    """Check the same exact messages/fields shown in the generated QA plan.

    Args:
        test: TestCase whose selector is mapped by the catalogue.
        response: Completed HTTP response with a server-generated interaction ID.
        output: In-memory captured execution log, never a normal/private log.
        logger: Execution logger, used to account for INFO/DEBUG filtering.
    """
    catalog = json.loads((PROJECT_ROOT/"qa/scenarios.json").read_text(encoding="utf-8"))
    files = list((logger.root/logger.config["directory"]).glob("application_*.log"))
    test.assertTrue(files,"Missing execution log file")
    interaction = response.headers.get("X-Interaction-ID")
    test.assertIsNotNone(interaction)
    events = []
    for line in output.splitlines():
        columns = line.split(" | ",9)
        if len(columns) != 10 or columns[1].strip() != interaction: continue
        events.append({"level":columns[0].strip(),"category":columns[3].strip(),
                       "method_path":columns[4].strip(),"message":columns[8],"context":json.loads(columns[9])})
    method, path = response.request.method, response.request.url.path
    for scenario in catalog["scenarios"]:
        if test.id() not in scenario["tests"]: continue
        for file in files:
            test.assertRegex(file.name,scenario["log_evidence"]["file_regex"])
        for rule in scenario["log_evidence"]["events"]:
            if rule["category"] != "request": continue
            endpoint = rule["endpoint"]
            path_matches = endpoint == "*" or re.fullmatch(
                re.escape(endpoint).replace(r"\{id\}", r"[1-9][0-9]*"), path)
            if rule["method"] not in ("*",method) or not path_matches: continue
            if rule.get("statuses") and response.status_code not in rule["statuses"]: continue
            matches = [event for event in events if event["message"] == rule["message"]]
            if rule["presence"] == "absent":
                test.assertFalse(matches,"Forbidden catalogue log event was emitted")
                continue
            if rule["level"] == "DEBUG" and not logger.logger.isEnabledFor(10): continue
            if rule["presence"] == "optional" and not matches: continue
            test.assertTrue(matches,"Missing catalogue log evidence: "+scenario["id"]+" / "+rule["message"])
            for event in matches:
                test.assertEqual(event["level"],rule["level"])
                test.assertEqual(event["category"],"request")
                test.assertEqual(event["method_path"],method+" "+path)
                for field in rule["context_fields"]:
                    test.assertIn(field,event["context"])
                for key,value in rule.get("context_values",{}).items():
                    test.assertEqual(event["context"][key],value)
                if rule["message"] == "HTTP request finished":
                    test.assertEqual(event["context"]["status"],response.status_code)
