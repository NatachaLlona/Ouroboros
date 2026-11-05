"""Authenticated ephemeral audio processing through the existing browser/API boundary."""
from typing import Annotated
from functools import partial
import threading
import anyio
from fastapi import APIRouter, Request, Security
from pydantic import BaseModel
from starlette.requests import ClientDisconnect
from api.app.auth import require_scopes
from shared.errors import ErrorResponse, error_response
from shared.speech import SpeechError

router = APIRouter(tags=['transcription'])
Actor = Annotated[dict, Security(require_scopes, scopes=['catalogue:access'])]


class TranscriptionResult(BaseModel):
    text: str
    language: str
    complete: bool
    duration_seconds: float


@router.get('/browser/transcription/options')
async def transcription_options(request: Request, actor: Actor):
    service = request.app.state.transcription
    try:
        settings = await service.options(actor) if hasattr(service, 'call') else service.settings
    except SpeechError as error:
        return error_response(request.app.state.error_codes, error.code)
    return {key: settings[key] for key in ('max_audio_bytes', 'max_duration_seconds', 'request_timeout_seconds', 'recording_chunk_ms', 'audio_bits_per_second')}


@router.post('/browser/transcription', response_model=TranscriptionResult,
             responses={413: {'model': ErrorResponse}, 429: {'model': ErrorResponse}})
async def transcribe(request: Request, actor: Actor):
    service = request.app.state.transcription
    codes = request.app.state.error_codes
    if hasattr(service, 'call'):
        try:
            await service.options(actor)
        except SpeechError as error:
            return error_response(codes, error.code)
    media = request.headers.get('content-type', '').split(';')[0].strip().lower()
    if media not in ('audio/webm', 'audio/ogg', 'audio/mp4', 'audio/wav'):
        return error_response(codes, 'AUDIO_INVALID')
    if not service.acquire():
        return error_response(codes, 'TRANSCRIPTION_BUSY', headers={'Retry-After': '5'})
    data = bytearray()
    cancelled = threading.Event()
    try:
        with anyio.fail_after(service.settings['upload_timeout_seconds']):
            async for chunk in request.stream():
                if len(data) + len(chunk) > service.settings['max_audio_bytes']:
                    return error_response(codes, 'AUDIO_LIMIT_EXCEEDED')
                data.extend(chunk)
        if not data:
            return error_response(codes, 'AUDIO_INVALID')
        if hasattr(service, 'call'):
            result = await service.transcribe_request(request, bytes(data), actor, media)
            return TranscriptionResult.model_validate(result)
        # Await completion on cancellation before releasing the slot; native inference cannot
        # be abandoned safely. All request audio stays in memory; no temporary files exist.
        async def watch_disconnect():
            while True:
                if await request.is_disconnected():
                    cancelled.set()
                    return
                await anyio.sleep(0.25)
        failure = None
        async with anyio.create_task_group() as tasks:
            tasks.start_soon(watch_disconnect)
            try:
                result = await anyio.to_thread.run_sync(partial(service.transcribe, data, cancelled=cancelled), abandon_on_cancel=False)
            except SpeechError as error:
                failure = error
            finally:
                tasks.cancel_scope.cancel()
        if failure is not None:
            raise failure
        return result
    except SpeechError as error:
        if error.code == 'TRANSCRIPTION_UNAVAILABLE':
            diagnostic = error.diagnostic()
            await anyio.to_thread.run_sync(lambda: request.app.state.logger.log({
                'level': 'WARNING', 'message': 'Local transcription unavailable', 'context': diagnostic}))
        return error_response(codes, error.code)
    except (ClientDisconnect, TimeoutError):
        return error_response(codes, 'AUDIO_INVALID')
    finally:
        cancelled.set()
        data.clear()
        service.release()
