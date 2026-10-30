"""Synchronize the README's complete collection from the canonical JSON file."""
from pathlib import Path
import json
root=Path(__file__).resolve().parent.parent
collection=(root/"postman/Ouroboros.postman_collection.json").read_text(encoding="utf-8").strip()
json.loads(collection)
path=root/"README.md"
text=path.read_text(encoding="utf-8")
start=text.index("```json\n",text.index("<!-- postman-json:start -->"))+len("```json\n")
end=text.index("\n```",start)
path.write_text(text[:start]+collection+text[end:],encoding="utf-8")
print("README Postman JSON synchronized")
