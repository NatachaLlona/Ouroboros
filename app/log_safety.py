"""Recursive redaction and bounded previews; never pass token forms here."""
import json
import re
import traceback
from pathlib import Path
from app.config import PROJECT_ROOT


def redact(value):
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            normalized = re.sub(r"[^a-z0-9]", "", str(key).lower())
            sensitive = any(word in normalized for word in
                            ("password", "passwd", "secret", "token", "authorization", "apikey", "credential", "privatekey", "signingkey", "encryptionkey", "jwtkey")) or normalized in ("pwd", "hash")
            result[key] = "[REDACTED]" if sensitive else redact(item)
        return result
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def body_preview(raw, limit):
    try:
        body = redact(json.loads(raw))
        safe = json.dumps(body, ensure_ascii=False, allow_nan=False)
    except (ValueError, UnicodeError, RecursionError):
        return {"body_preview": "[omitted: invalid JSON]", "truncated": False}
    if len(safe) <= limit:
        return {"body": body, "truncated": False}
    # A truncated JSON document cannot remain a valid object. Mark the text fallback.
    return {"body_preview": safe[:limit], "truncated": True}


def error_details(error):
    frames = []
    for frame in traceback.extract_tb(error.__traceback__)[-6:]:
        try:
            source = Path(frame.filename).resolve().relative_to(PROJECT_ROOT).as_posix()
        except ValueError:
            source = Path(frame.filename).name
        frames.append({"source": source, "line": frame.lineno, "function": frame.name})
    return {"error_type": type(error).__name__, "frames": frames}
