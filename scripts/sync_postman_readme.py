"""Synchronize the README's complete collection from the canonical JSON file."""

import sys as _sys
from pathlib import Path as _Path
_repository = _Path(__file__).resolve().parents[1]
_sys.path.insert(0, str(_repository))
_sys.path.insert(0, str(_repository / "modules"))
from pathlib import Path
import json
root=Path(__file__).resolve().parent.parent
collection=(root/"modules/api/postman/Ouroboros.postman_collection.json").read_text(encoding="utf-8").strip()
json.loads(collection)
path=root/"README.md"
text=path.read_text(encoding="utf-8")
start=text.index("```json\n",text.index("<!-- postman-json:start -->"))+len("```json\n")
end=text.index("\n```",start)
path.write_text(text[:start]+collection+text[end:],encoding="utf-8")
print("README Postman JSON synchronized")
