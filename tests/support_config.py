"""Compose explicit disposable test inputs from the canonical public module examples."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def example_config():
    api = json.loads((ROOT/'api/config.example.json').read_text(encoding='utf-8'))
    database = json.loads((ROOT/'database/config.example.json').read_text(encoding='utf-8'))
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
    path = Path(root)/'api/config.json'
    path.parent.mkdir(parents=True,exist_ok=True)
    return path


def config_example_path(root):
    path = Path(root)/'api/config.example.json'
    path.parent.mkdir(parents=True,exist_ok=True)
    return path
