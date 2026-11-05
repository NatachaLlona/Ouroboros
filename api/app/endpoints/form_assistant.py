"""Ephemeral suggestions for the classification form; no business mutations."""
import anyio
from fastapi import APIRouter, Request, Security
from typing import Annotated
from pydantic import ValidationError
from starlette.requests import ClientDisconnect
from api.app.auth import require_scopes
from api.app.catalogue_repository import CatalogueRepository
from shared.errors import error_response
from shared.form_contracts import AssistantError, RESOURCE, SuggestionRequest, SuggestionResult

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
        def read_count():
            selection = RESOURCE.query.model_validate({'page': 1, 'page_size': 10, 'order_by': 'tier', 'order_direction': 'asc'})
            selection.bind_filter_timezone(request.app.state.config)
            return CatalogueRepository(request.app.state.database, RESOURCE).page(selection)['count']
        count = await anyio.to_thread.run_sync(read_count)
        service = request.app.state.form_assistant
        maximum = count+int(payload.mode == 'create')
        if hasattr(service, 'call'):
            return await service.suggest(payload, maximum, actor)
        return await service.suggest(payload, maximum)
    except AssistantError as error:
        return error_response(codes, error.code)
    except (ValidationError, ValueError, ClientDisconnect, TimeoutError):
        return error_response(codes, 'VALIDATION_ERROR')
    finally:
        body.clear()
