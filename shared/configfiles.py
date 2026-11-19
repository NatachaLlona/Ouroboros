"""UTF-8 JSON objects and atomic non-secret preference persistence."""
import json
import os
from pathlib import Path
import tempfile
from shared.paths import ConfigurationError


def read_object(path):
    try:
        value = json.loads(Path(path).read_text(encoding='utf-8'))
        if not isinstance(value, dict):
            raise ValueError
        return value
    except (OSError, UnicodeError, ValueError):
        raise ConfigurationError('Invalid JSON configuration: '+str(path)) from None


def write_object(path, value):
    path = Path(path)
    temporary = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as output:
            temporary = Path(output.name)
            json.dump(value, output, ensure_ascii=False, indent=2)
            output.write('\n')
        os.replace(temporary, path)
    except OSError:
        raise ConfigurationError('Unable to save module configuration') from None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def ensure_object(path, example):
    if not Path(path).exists():
        write_object(path, read_object(example))
    return read_object(path)
