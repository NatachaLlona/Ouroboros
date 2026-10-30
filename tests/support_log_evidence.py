"""Assert catalogue-defined request evidence against actual sanitized log events."""
import json
import re
import time
from app.config import PROJECT_ROOT


def assert_response_logs(test, response, output, logger):
    """Check the same exact messages/fields shown in the generated QA plan.

    Args:
        test: TestCase whose selector is mapped by the catalogue.
        response: Completed HTTP response with a server-generated interaction ID.
        output: Callable returning the current in-memory test execution log.
        logger: Execution logger, used to account for INFO/DEBUG filtering.
    """
    catalog = json.loads((PROJECT_ROOT/"qa/scenarios.json").read_text(encoding="utf-8"))
    files = list((logger.root/logger.config["directory"]).glob("application_*.log"))
    test.assertTrue(files,"Missing execution log file")
    interaction = response.headers.get("X-Interaction-ID")
    test.assertIsNotNone(interaction)
    # HTTPX invokes response hooks after headers, before consuming the body.
    # Drain it so a streaming TestClient transport can finish ASGI send first.
    response.read()
    # A response hook can run after body delivery but before the ASGI middleware's
    # finally block finishes its offloaded log write. Wait for that exact request,
    # retaining the assertion below if completion never arrives.
    deadline = time.monotonic() + 2
    while True:
        captured = output()
        if any(interaction in line and " | HTTP request finished | " in line
               for line in captured.splitlines()) or time.monotonic() >= deadline:
            break
        time.sleep(0.01)
    events = []
    for line in captured.splitlines():
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
