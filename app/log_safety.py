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
                            ("password", "passwd", "secret", "token", "authorization", "apikey", "credential", "privatekey", "signingkey", "encryptionkey", "jwtkey", "connectionstring", "cookie", "hash")) or normalized in ("pwd", "dsn")
            safe_key = redact(str(key))
            result[safe_key] = "[REDACTED]" if sensitive else redact(item)
        return result
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        # Serialized JSON inside a free-text field still receives structured redaction.
        if value.lstrip().startswith(('{', '[')):
            try:
                parsed = json.loads(value)
                return json.dumps(redact(parsed), ensure_ascii=False, allow_nan=False)
            except (ValueError, RecursionError):
                pass
        value = re.sub(r'(?i)\bBearer\s+[^\s"<>]+', '[REDACTED]', value)
        value = re.sub(r'\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+', '[REDACTED]', value)
        value = re.sub(r'(?i)\bpostgres(?:ql)?://[^\s"<>]+', '[REDACTED]', value)
        if len(re.findall(r'(?i)\b(?:host|hostaddr|dbname|user|port|password)\s*=', value)) >= 2:
            return '[REDACTED CONNECTION STRING]'
        value = re.sub(r'\$argon2(?:id|i|d)\$[^\s"<>]+', '[REDACTED]', value)
        value = re.sub(r'(?i)\b(password|passwd|pwd|token|secret)\s*[=:]\s*[^\s,;"<>]+', r'\1=[REDACTED]', value)
        return value
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
