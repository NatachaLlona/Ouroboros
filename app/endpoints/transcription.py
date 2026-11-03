"""Authenticated ephemeral audio processing through the existing browser/API boundary."""
from typing import Annotated
import anyio
from fastapi import APIRouter, Request, Security
from pydantic import BaseModel
from starlette.requests import ClientDisconnect
from app.auth import require_scopes
from app.errors import ErrorResponse, error_response
from app.transcription import SpeechError

router = APIRouter(tags=['transcription'])
Actor = Annotated[dict, Security(require_scopes, scopes=['catalogue:access'])]


class TranscriptionResult(BaseModel):
    text: str
    language: str


@router.get('/browser/transcription/options')
def transcription_options(request: Request, actor: Actor):
    settings = request.app.state.transcription.settings
    return {'max_audio_bytes': settings['max_audio_bytes'], 'max_duration_seconds': settings['max_duration_seconds']}


@router.post('/browser/transcription', response_model=TranscriptionResult,
             responses={413: {'model': ErrorResponse}, 429: {'model': ErrorResponse}})
async def transcribe(request: Request, actor: Actor):
    service = request.app.state.transcription
    codes = request.app.state.error_codes
    media = request.headers.get('content-type', '').split(';')[0].strip().lower()
    if media not in ('audio/webm', 'audio/ogg', 'audio/mp4', 'audio/wav'):
        return error_response(codes, 'AUDIO_INVALID')
    if not service.acquire():
        return error_response(codes, 'TRANSCRIPTION_BUSY', headers={'Retry-After': '5'})
    data = bytearray()
    try:
        with anyio.fail_after(30):
            async for chunk in request.stream():
                if len(data) + len(chunk) > service.settings['max_audio_bytes']:
                    return error_response(codes, 'AUDIO_LIMIT_EXCEEDED')
                data.extend(chunk)
        if not data:
            return error_response(codes, 'AUDIO_INVALID')
        # Await completion on cancellation before releasing the slot; native inference cannot
        # be abandoned safely. All request audio stays in memory; no temporary files exist.
        result = await anyio.to_thread.run_sync(service.transcribe, data, abandon_on_cancel=False)
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
        data.clear()
        service.release()
