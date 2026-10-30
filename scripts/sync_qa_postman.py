"""Synchronize Postman scenario labels from the authoritative QA catalogue."""
import json
import re
from qa_catalog import ROOT, load_catalog


def main():
    """Update only public request descriptions/assertion labels, never secrets."""
    catalog = load_catalog()
    path = ROOT/"postman/Ouroboros.postman_collection.json"
    collection = json.loads(path.read_text(encoding="utf-8"))
    def visit(items):
        for item in items:
            if "item" in item: yield from visit(item["item"])
            else: yield item
    for item in visit(collection["item"]):
        matches = [row for row in catalog["scenarios"] if item["name"] in row.get("postman_requests", [])]
        if len(matches) != 1:
            raise ValueError("Each canonical request needs exactly one catalogue owner")
        row = matches[0]
        label = row["id"]+" - "+row["name"]
        base = item["request"].get("description", "").split("QA scenario: ", 1)[0].strip()
        item["request"]["description"] = (base+"\n\nQA scenario: "+label+". See docs/QA_TEST_PLAN.md. Use private local credentials only.").strip()
        for event in item["event"]:
            if event["listen"] == "test":
                event["script"]["exec"] = [re.sub(r'pm\.test\("(?:\d+\.\d+ - [^"|]+ \| )?', 'pm.test("'+label+' | ', line) for line in event["script"]["exec"]]
    path.write_text(json.dumps(collection, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")


if __name__ == "__main__":
    main()
