"""Ephemeral suggestions for the classification form; no business mutations."""
import anyio
from fastapi import APIRouter, Request, Security
from typing import Annotated
from pydantic import ValidationError
from starlette.requests import ClientDisconnect
from api.app.auth import require_scopes
from api.form_assistant_reads import FormReads
from api.form_assistant_flow import assist
from shared.errors import error_response
from shared.form_contracts import AssistantError, SuggestionRequest, SuggestionResult

router = APIRouter(tags=['form assistant'])
Actor = Annotated[dict, Security(require_scopes, scopes=['catalogue:access'])]


@router.post('/browser/assistant/work-classifications', response_model=SuggestionResult)
async def suggest(request: Request, actor: Actor):
    codes = request.app.state.error_codes
    body = bytearray()
    try:
        if request.headers.get('content-type', '').split(';')[0] != 'application/json':
            return error_response(codes, 'VALIDATION_ERROR')
        with anyio.fail_after(20):
            async for chunk in request.stream():
                if len(body)+len(chunk) > 131072:
                    return error_response(codes, 'VALIDATION_ERROR')
                body.extend(chunk)
        payload = SuggestionRequest.model_validate_json(body)
        if not payload.message.strip():
            return error_response(codes, 'VALIDATION_ERROR')
        with anyio.fail_after(80):
            return await assist(request.app, actor, payload, FormReads(request), request.app.state.form_assistant)
    except AssistantError as error:
        return error_response(codes, error.code)
    except TimeoutError:
        return error_response(codes, 'ASSISTANT_UNAVAILABLE')
    except (ValidationError, ValueError, ClientDisconnect):
        return error_response(codes, 'VALIDATION_ERROR')
    finally:
        body.clear()
