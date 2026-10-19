"""Offline schema, safe placeholders, and README synchronization checks."""
import json
import unittest
from pathlib import Path
import jsonschema
from app.config import PROJECT_ROOT


class PostmanTests(unittest.TestCase):
    def test_collection_schema_and_safe_defaults(self):
        collection=json.loads((PROJECT_ROOT/"postman/Foundation.postman_collection.json").read_text(encoding="utf-8"))
        schema=json.loads((PROJECT_ROOT/"tests/schemas/postman-v2.1.schema.json").read_text())
        jsonschema.validate(collection,schema)
        self.assertEqual(len(collection["item"]),12)
        variables={item["key"]:item["value"] for item in collection["variable"]}
        for key, value in variables.items():
            if key != "base_url": self.assertEqual(value,"",key)
        self.assertEqual(collection["item"][0]["request"]["auth"]["type"],"noauth")
        self.assertEqual(collection["item"][7]["request"]["auth"]["type"],"noauth")
        administrative = collection["item"][8]["item"]
        self.assertEqual(len(administrative),12)
        for item in administrative:
            self.assertTrue(item["event"][0]["script"]["exec"])

    def test_distinct_requests_and_visible_pagination(self):
        collection=json.loads((PROJECT_ROOT/"postman/Foundation.postman_collection.json").read_text(encoding="utf-8"))
        def visit(items):
            for item in items:
                if "item" in item: yield from visit(item["item"])
                else: yield item
        items=list(visit(collection["item"]))
        names=[item["name"] for item in items]
        self.assertEqual(len(names),len(set(names)))
        self.assertEqual(sum("List all entries" in name for name in names),1)
        page=next(item for item in items if item["name"].startswith("61 -"))
        params={item["key"]:item for item in page["request"]["url"]["query"]}
        self.assertEqual(params["page"]["value"],"2")
        self.assertEqual(params["page_size"]["value"],"10")
        self.assertTrue(params["id"]["disabled"])
        self.assertTrue(params["value"]["disabled"])

    def test_readme_json_matches_collection(self):
        readme=(PROJECT_ROOT/"README.md").read_text(encoding="utf-8")
        section=readme.split("<!-- postman-json:start -->",1)[1].split("<!-- postman-json:end -->",1)[0]
        embedded=section.split("```json\n",1)[1].split("\n```",1)[0]
        actual=(PROJECT_ROOT/"postman/Foundation.postman_collection.json").read_text(encoding="utf-8").strip()
        self.assertEqual(embedded,actual)


    def test_ouroboros_filters_and_scripts(self):
        collection=json.loads((PROJECT_ROOT/"postman/Foundation.postman_collection.json").read_text(encoding="utf-8"))
        items=collection["item"]
        self.assertEqual(items[5]["request"]["url"],"{{base_url}}/test?value=%25Ouroboros%25")
        self.assertEqual(items[6]["request"]["url"],"{{base_url}}/test?id={{test_id}}&value=%25Ouroboros%25")
        self.assertEqual(json.loads(items[2]["request"]["body"]["raw"])["value"],"Ouroboros est\u00e1 vivo! \U0001f40d\U0001f4bb")
        for index in (4,5,6):
            self.assertEqual(items[index]["request"]["auth"]["type"],"bearer")
            script="\n".join(items[index]["event"][0]["script"]["exec"])
            self.assertIn("status(200)",script)
            self.assertIn('an("array")',script)
            if index in (4,6):self.assertIn('String(rows[0].id)',script)
            if index in (5,6):self.assertIn('toLocaleLowerCase()',script)


    def test_optional_list_params_and_single_encoding(self):
        from itertools import product
        from urllib.parse import urlencode, parse_qs
        collection=json.loads((PROJECT_ROOT/"postman/Foundation.postman_collection.json").read_text(encoding="utf-8"))
        request=collection["item"][3]["request"]
        self.assertEqual(request["method"],"GET")
        self.assertEqual(request["auth"]["type"],"bearer")
        self.assertEqual(request["url"]["raw"],"{{base_url}}/test")
        query=request["url"]["query"]
        self.assertEqual([(item["key"],item["value"],item["disabled"]) for item in query],
                         [("id","{{test_id}}",True),("value","%Ouroboros%",True)])
        for flags in product((False,True),repeat=2):
            active={item["key"]:item["value"].replace("{{test_id}}","42") for item,enabled in zip(query,flags) if enabled}
            encoded=urlencode(active)
            self.assertEqual(parse_qs(encoded),{key:[value] for key,value in active.items()})
            self.assertNotIn("%2525",encoded)
            if flags[1]:self.assertIn("value=%25Ouroboros%25",encoded)
        self.assertIsInstance(collection["item"][2]["request"]["url"],str)
        self.assertNotIn("?",collection["item"][2]["request"]["url"])
