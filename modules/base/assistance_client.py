"""Authorized, bounded API-to-assistance transport; no model dependencies."""
import json
import os
import threading
import httpx
import anyio
from modules.service_auth import delegate, signing_key
from app.form_assistant import AssistantError, SuggestionResult
from app.transcription import SpeechError, transcription_settings


class AssistanceClient:
    def __init__(self, config):
        self.settings = transcription_settings(config)
        self.url = os.environ.get('OUROBOROS_ASSISTANCE_URL', '').rstrip('/')
        self.key_path = os.environ.get('OUROBOROS_SERVICE_KEY_FILE', '/run/secrets/service_key')
        self.slots = threading.BoundedSemaphore(self.settings['max_concurrency'])

    def acquire(self):
        return self.slots.acquire(blocking=False)

    def release(self):
        self.slots.release()

    def close(self):
        pass

    async def call(self, operation, body, actor, content_type='application/json'):
        speech_operation = operation in ('transcribe', 'options')
        error = SpeechError if speech_operation else AssistantError
        unavailable = 'TRANSCRIPTION_UNAVAILABLE' if speech_operation else 'ASSISTANT_UNAVAILABLE'
        if not self.url:
            raise error(unavailable)
        try:
            token = delegate(signing_key(self.key_path), operation, body, actor)
            async with httpx.AsyncClient(trust_env=False, timeout=self.settings['request_timeout_seconds']) as client:
                async with client.stream('POST', self.url+'/internal/'+operation, content=body,
                        headers={'X-Service-Authorization': token, 'Content-Type': content_type}) as response:
                    raw = bytearray()
                    maximum = self.settings['max_transcript_chars'] * 6 + 65536
                    async for chunk in response.aiter_bytes():
                        if len(raw)+len(chunk) > maximum:
                            raise error(unavailable)
                        raw.extend(chunk)
                    document = json.loads(raw)
                    if response.status_code != 200:
                        code = document.get('error', {}).get('code')
                        allowed = {'TRANSCRIPTION_BUSY', 'TRANSCRIPTION_UNAVAILABLE', 'TRANSCRIPTION_TIMEOUT',
                            'TRANSCRIPTION_LANGUAGE_REJECTED', 'AUDIO_INVALID', 'AUDIO_LIMIT_EXCEEDED',
                            'ASSISTANT_BUSY', 'ASSISTANT_UNAVAILABLE', 'ASSISTANT_RATE_LIMITED',
                            'ASSISTANT_UPSTREAM_REJECTED', 'ASSISTANT_INVALID_OUTPUT'}
                        raise error(code if code in allowed else unavailable)
                    return document
        except (SpeechError, AssistantError):
            raise
        except (OSError, ValueError, TypeError, httpx.HTTPError):
            raise error(unavailable) from None

    async def suggest(self, payload, maximum_tier, actor):
        body = json.dumps({'payload': payload.model_dump(), 'maximum_tier': maximum_tier}).encode()
        result = await self.call('suggest', body, actor)
        return SuggestionResult.model_validate(result)

    async def options(self, actor):
        result = await self.call('options', b'', actor)
        self.settings = transcription_settings({'transcription': result})
        return self.settings

    async def transcribe_request(self, request, body, actor, media):
        disconnected = False
        result = None
        async with anyio.create_task_group() as tasks:
            async def watch():
                nonlocal disconnected
                while True:
                    if await request.is_disconnected():
                        disconnected = True
                        tasks.cancel_scope.cancel()
                        return
                    await anyio.sleep(.25)
            tasks.start_soon(watch)
            failure = None
            try:
                result = await self.call('transcribe', body, actor, media)
            except SpeechError as error:
                failure = error
            finally:
                tasks.cancel_scope.cancel()
        if disconnected:
            raise SpeechError('REQUEST_CANCELLED')
        if failure:
            raise failure
        return result
