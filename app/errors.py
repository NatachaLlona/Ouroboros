"""Versioned safe error catalogue and one public error envelope."""
import json
import re
from typing import Any
from pydantic import BaseModel
from starlette.responses import JSONResponse
from app.config import PROJECT_ROOT, ConfigurationError
from app.request_context import request_context


class AuditUnavailable(RuntimeError):
    """Mandatory transactional evidence could not be persisted."""


class ErrorBody(BaseModel):
    code: str
    message: str
    interaction_id: str
    details: list[dict[str, Any]] | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody


def load_error_codes(path=None):
    """Reject malformed/duplicate catalogue content without echoing its contents."""
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError
            result[key] = value
        return result
    try:
        document = json.loads((path or PROJECT_ROOT / 'app/error_codes.json').read_text(encoding='utf-8'), object_pairs_hook=unique_object)
        if set(document) != {'version', 'errors'} or type(document['version']) is not int or document['version'] != 1:
            raise ValueError
        result = {}
        for item in document['errors']:
            if (set(item) != {'code', 'status', 'message'} or not re.fullmatch(r'[A-Z][A-Z0-9_]+', item['code'])
                    or item['code'] in result or type(item['status']) is not int or not 400 <= item['status'] <= 599
                    or not isinstance(item['message'], str) or not item['message'].strip()
                    or any(ord(character) < 32 for character in item['message'])):
                raise ValueError
            result[item['code']] = item
        required = {'RESOURCE_NOT_FOUND', 'METHOD_NOT_ALLOWED', 'RELATIONSHIP_CONFLICT', 'VALIDATION_ERROR',
                    'AUTHENTICATION_REQUIRED', 'INVALID_TOKEN', 'INVALID_CREDENTIALS', 'INSUFFICIENT_PERMISSIONS',
                    'CONFIRMATION_REQUIRED', 'DATABASE_UNAVAILABLE', 'AUDIT_UNAVAILABLE', 'INTERNAL_ERROR',
                    'REQUEST_CANCELLED', 'TRANSPORT_FAILURE', 'USER_CONFLICT', 'PASSWORD_CHANGE_REJECTED'}
        if set(result) != required:
            raise ValueError
        return result
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        raise ConfigurationError('Invalid error catalogue; restore the versioned app/error_codes.json structure and unique codes') from None


def code_for(status, detail=None, path='', source=None):
    """Map known application conditions; raw exception messages are never returned."""
    if source == 'audit':
        return 'AUDIT_UNAVAILABLE'
    if status == 401:
        if detail == 'Bearer authentication required':
            return 'AUTHENTICATION_REQUIRED'
        return 'INVALID_CREDENTIALS' if path.rstrip('/') == '/token' else 'INVALID_TOKEN'
    return {400: 'PASSWORD_CHANGE_REJECTED', 403: 'INSUFFICIENT_PERMISSIONS', 404: 'RESOURCE_NOT_FOUND',
            405: 'METHOD_NOT_ALLOWED', 409: 'USER_CONFLICT' if source == 'users' else 'RELATIONSHIP_CONFLICT',
            422: 'VALIDATION_ERROR', 503: 'DATABASE_UNAVAILABLE'}.get(status, 'INTERNAL_ERROR')


def error_response(codes, code, details=None, headers=None, status=None):
    """Build one safe response and attach its code to the central request state."""
    from app.audit_context import audit_context
    context = request_context.get()
    audit = audit_context.get()
    if audit is not None:
        audit.error_code = code
    item = codes[code]
    body = dict(code=code, message=item['message'], interaction_id=context.interaction_id if context else '')
    if details:
        from app.audit_privacy import bounded_value
        safe_details, flags = bounded_value(details, 8192)
        if safe_details is not None:
            body['details'] = safe_details
    return JSONResponse({'error': body}, status_code=status or item['status'], headers=headers)


ERROR_RESPONSES = {status: {'model': ErrorResponse, 'description': 'Standardized safe error code, message and interaction ID.'}
                   for status in (400, 401, 403, 404, 405, 409, 422, 500, 503)}
