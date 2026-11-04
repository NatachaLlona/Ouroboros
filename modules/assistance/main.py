"""Internal inference service: no accounts, database connection or business writes."""
import os
import threading
import anyio
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from app.ai_config import read_ai_document
from app.transcription import LocalTranscription, SpeechError
from app.form_assistant import FormAssistant, AssistantError, SuggestionRequest
from app.errors import load_error_codes, error_response
from modules.service_auth import DelegationVerifier, signing_key


class SuggestionEnvelope(BaseModel):
    model_config = ConfigDict(extra='forbid')
    payload: SuggestionRequest
    maximum_tier: int = Field(strict=True, ge=1, le=9223372036854775807)


def create_assistance(config=None, verifier=None, speech=None, assistant=None):
    config = config or read_ai_document(os.environ.get('OUROBOROS_AI_CONFIG', '/config/assistance.json'))
    speech = speech or LocalTranscription(config)
    assistant = assistant or FormAssistant(settings=config.get('form_assistant'))
    verifier = verifier or DelegationVerifier(signing_key(os.environ.get('OUROBOROS_SERVICE_KEY_FILE', '/run/secrets/service_key')), max_age=speech.settings['upload_timeout_seconds']+30)
    codes = load_error_codes()
    app = FastAPI(title='Ouroboros assistance', docs_url=None, redoc_url=None, openapi_url=None)

    @app.get('/health')
    def health():
        return {'status': 'ok'}

    @app.post('/internal/{operation}')
    async def invoke(operation: str, request: Request):
        if operation not in ('transcribe', 'suggest', 'options'):
            return JSONResponse({'error': {'code': 'NOT_FOUND'}}, 404)
        data = bytearray()
        acquired = False
        cancelled = threading.Event()
        try:
            maximum = speech.settings['max_audio_bytes'] if operation == 'transcribe' else 131072
            with anyio.fail_after(speech.settings['upload_timeout_seconds']):
                async for chunk in request.stream():
                    if len(data)+len(chunk) > maximum:
                        return error_response(codes, 'AUDIO_LIMIT_EXCEEDED' if operation == 'transcribe' else 'VALIDATION_ERROR')
                    data.extend(chunk)
            try:
                verifier.verify(request.headers.get('x-service-authorization'), operation, data)
            except (ValueError, KeyError, TypeError):
                return JSONResponse({'error': {'code': 'INVALID_TOKEN'}}, 401)
            if operation == 'options':
                return {key: speech.settings[key] for key in ('max_audio_bytes', 'max_duration_seconds',
                    'upload_timeout_seconds', 'processing_timeout_seconds', 'request_timeout_seconds',
                    'max_transcript_chars', 'recording_chunk_ms', 'audio_bits_per_second')}
            if operation == 'suggest':
                envelope = SuggestionEnvelope.model_validate_json(data)
                return await assistant.suggest(envelope.payload, envelope.maximum_tier)
            if not speech.acquire():
                return error_response(codes, 'TRANSCRIPTION_BUSY')
            acquired = True
            failure = None
            async def disconnect():
                while True:
                    if await request.is_disconnected():
                        cancelled.set()
                        return
                    await anyio.sleep(.25)
            async with anyio.create_task_group() as tasks:
                tasks.start_soon(disconnect)
                try:
                    result = await anyio.to_thread.run_sync(lambda: speech.transcribe(data, cancelled), abandon_on_cancel=False)
                except SpeechError as error:
                    failure = error
                finally:
                    tasks.cancel_scope.cancel()
            if failure:
                raise failure
            return result
        except (AssistantError, SpeechError) as error:
            return error_response(codes, error.code)
        except (ValidationError, TimeoutError, ValueError):
            return error_response(codes, 'VALIDATION_ERROR')
        except Exception:
            return error_response(codes, 'TRANSCRIPTION_UNAVAILABLE' if operation in ('transcribe', 'options') else 'ASSISTANT_UNAVAILABLE')
        finally:
            cancelled.set()
            data.clear()
            if acquired:
                speech.release()
    return app


def main():
    import uvicorn
    uvicorn.run(create_assistance(), host='0.0.0.0', port=8000, access_log=False)


if __name__ == '__main__':
    main()
