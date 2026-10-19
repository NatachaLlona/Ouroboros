"""Bounded, recursively sanitized audit values; never persist raw capture bytes."""
import json
import re
from datetime import datetime
from decimal import Decimal
from app.log_safety import redact


def sensitive_operation(path):
    parts = path.rstrip('/').split('/')
    return (len(parts) > 1 and parts[1] == 'token') or (len(parts) > 2 and parts[1] == 'users' and 'password' in parts[2:])


def safe_path(path):
    """Keep useful routing context while escaping controls and recognizable secrets."""
    value = redact(path)
    return re.sub(r'[\x00-\x1f\x7f-\x9f\u2028\u2029\ud800-\udfff]', lambda match: '\\u' + f'{ord(match[0]):04x}', value)[:2048]


def json_default(value):
    if isinstance(value, datetime):
        from app.datetimes import utc
        return utc(value).isoformat().replace('+00:00', 'Z')
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError('Unsupported audit value')


def bounded_value(value, limit):
    """Redact before applying a UTF-8 byte bound to structured persisted data."""
    try:
        safe = redact(value)
        encoded = json.dumps(safe, ensure_ascii=False, allow_nan=False, default=json_default).encode('utf-8')
    except (ValueError, TypeError, RecursionError, UnicodeError):
        return None, dict(omitted=True, truncated=False, reason='invalid_or_unsupported_data')
    if len(encoded) > limit:
        return None, dict(omitted=True, truncated=True, reason='sanitized_capture_limit')
    return json.loads(encoded), dict(omitted=False, truncated=False, reason=None)


class BodyCapture:
    """Observe a stream once without altering delivery or buffering beyond its cap."""
    def __init__(self, limit, omission=None):
        self.limit, self.omission = limit, omission
        self.data = bytearray()
        self.overflow = False
        self.complete = False
        self.content_type = ''

    def feed(self, body, complete):
        if not self.omission and not self.overflow:
            if len(self.data) + len(body) > self.limit:
                self.data.clear()
                self.overflow = True
            else:
                self.data.extend(body)
        self.complete = complete

    def result(self):
        reason = self.omission or ('capture_limit' if self.overflow else None)
        if reason:
            return None, dict(omitted=True, truncated=self.overflow, reason=reason)
        if not self.data:
            return None, dict(omitted=True, truncated=False, reason='empty_or_unconsumed')
        if not self.complete:
            return None, dict(omitted=True, truncated=False, reason='incomplete_stream')
        if self.content_type.split(';')[0].strip().lower() not in ('application/json', 'application/problem+json'):
            return None, dict(omitted=True, truncated=False, reason='non_json')
        try:
            value = json.loads(self.data)
        except (ValueError, UnicodeError, RecursionError):
            return None, dict(omitted=True, truncated=False, reason='invalid_json')
        return bounded_value(value, self.limit)

    def clear(self):
        self.data.clear()
