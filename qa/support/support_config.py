"""Compose explicit disposable test inputs from the canonical public module examples."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def example_config():
    api = json.loads((ROOT/'qa/support/legacy/api.fixture.jsonc').read_text(encoding='utf-8'))
    database = json.loads((ROOT/'qa/support/legacy/database.fixture.jsonc').read_text(encoding='utf-8'))
    orchestration = json.loads((ROOT/'config.example.json').read_text(encoding='utf-8'))
    # These unit fixtures deliberately start without a selected database/master.
    database.update(name='', user='')
    api['database'] = {**api['database'], **database}
    api.update(host='localhost', port=orchestration['public_port'],
        infrastructure={'project_name':orchestration['project_name'],'workspace':''})
    return api


def example_path():
    path = ROOT/'.tmp/unit-fixtures/api-example.json'
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(example_config()),encoding='utf-8')
    return path


def config_path(root):
    path = Path(root)/'modules/api/config.json'
    path.parent.mkdir(parents=True,exist_ok=True)
    return path


def config_example_path(root):
    path = Path(root)/'qa/support/legacy/api.fixture.jsonc'
    path.parent.mkdir(parents=True,exist_ok=True)
    return path


def basic_api_configuration(directory):
    """Prepare public API JSONC fixtures without private configuration or secrets."""
    root = Path(directory)
    (root/"modules/api").mkdir(parents=True)
    (root/"modules/api/config.example.jsonc").write_bytes((ROOT/"modules/api/config.example.jsonc").read_bytes())
    return root
