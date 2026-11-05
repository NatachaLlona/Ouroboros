"""Speech limits and complete ordered assembly, without normal data or personal audio."""
import array
import io
import math
import json
import tempfile
import threading
import unittest
import wave
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch
from assistance.transcription import LocalTranscription, SpeechError


def test_wave(seconds=1):
    samples=array.array('h',(int(1800*math.sin(index*2*math.pi*220/16000)) if index%48000<16000 else 0 for index in range(seconds*16000)))
    output=io.BytesIO()
    with wave.open(output,'wb') as target:
        target.setparams((1,2,16000,0,'NONE','not compressed'));target.writeframes(samples.tobytes())
    return output.getvalue()


class SpeechAssemblyTests(unittest.TestCase):
    def test_module_configuration_preserves_limits_without_rewriting_other_files(self):
        from shared.assistance_settings import read_ai_config
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            path=root/'assistance/config.json';path.parent.mkdir()
            document={'transcription':{'max_duration_seconds':600}}
            path.write_text(json.dumps(document),encoding='utf-8')
            unrelated=root/'api/config.json';unrelated.parent.mkdir();unrelated.write_text('{"preserved":true}',encoding='utf-8')
            original=unrelated.read_bytes()
            self.assertEqual(read_ai_config(path)['max_duration_seconds'],600)
            self.assertEqual(unrelated.read_bytes(),original)
            self.assertEqual(json.loads(path.read_text(encoding='utf-8')),document)

    def service(self,segments,**limits):
        service=LocalTranscription({'transcription':limits})
        class Model:
            def transcribe(inner,audio,**kwargs):
                inner.samples=len(audio);inner.options=kwargs
                return iter(segments),SimpleNamespace(language='en')
        service._model=Model()
        return service

    def test_ten_minute_defaults_and_no_silence_removed_before_native_windows(self):
        service=self.service([SimpleNamespace(text=' first',start=0),SimpleNamespace(text=' last',start=2)])
        result=service.transcribe(test_wave(3))
        self.assertEqual(service.settings['max_duration_seconds'],600)
        self.assertEqual(service._model.samples,48000)
        self.assertIs(service._model.options['vad_filter'],False)
        self.assertEqual(service._model.options['chunk_length'],service.settings['segment_seconds'])
        self.assertEqual(result['text'],'first last');self.assertIs(result['complete'],True)
        self.assertEqual(result['duration_seconds'],3)

    def test_transcript_longer_than_old_character_limit_is_returned_in_full(self):
        text=' word'*4000
        service=self.service([SimpleNamespace(text=text,start=0)])
        self.assertEqual(service.transcribe(test_wave())['text'],text.strip())

    def test_limits_and_failures_never_return_partial_text(self):
        for limits in ({'max_duration_seconds':1,'duration_tolerance_ms':1},{'max_transcript_chars':3}):
            service=self.service([SimpleNamespace(text=' complete',start=0)],**limits)
            with self.assertRaises(SpeechError) as error:service.transcribe(test_wave(2))
            self.assertEqual(error.exception.code,'AUDIO_LIMIT_EXCEEDED')
        def broken():
            yield SimpleNamespace(text=' partial',start=0)
            raise RuntimeError('decoder unavailable')
        with self.assertRaises(SpeechError) as error:self.service(broken()).transcribe(test_wave())
        self.assertEqual(error.exception.code,'TRANSCRIPTION_UNAVAILABLE')

    def test_cancellation_and_processing_timeout_are_checked_between_segments(self):
        cancelled=threading.Event();cancelled.set()
        with self.assertRaises(SpeechError) as error:self.service([]).transcribe(test_wave(),cancelled)
        self.assertEqual(error.exception.code,'REQUEST_CANCELLED')
        clock=[0]
        def slow():
            yield SimpleNamespace(text=' first',start=0)
            clock[0]=2000
            yield SimpleNamespace(text=' last',start=1)
        with patch('shared.speech.time.monotonic',side_effect=lambda:clock[0]):
            with self.assertRaises(SpeechError) as error:self.service(slow()).transcribe(test_wave())
        self.assertEqual(error.exception.code,'TRANSCRIPTION_TIMEOUT')


class SpeechEndpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import test_api
        test_api.APITests.setUpClass.__func__(cls)

    def setUp(self):
        import test_api
        from test_frontend import BrowserSessionTests
        test_api.APITests.setUp(self)
        auditing=patch('api.app.audit_middleware.AuditStore');self.audit=auditing.start().return_value
        self.audit.begin.return_value=1;self.addCleanup(auditing.stop)
        self.browser=BrowserSessionTests.browser.__get__(self);self.login=BrowserSessionTests.login.__get__(self)
        session=self.login().json()
        self.headers={'Origin':'http://localhost:6969','X-CSRF-Token':session['csrf_token'],'Content-Type':'audio/wav'}

    def test_runtime_options_and_complete_response_omit_contents_from_audits(self):
        service=SpeechAssemblyTests().service([SimpleNamespace(text=' synthetic private transcript',start=0)])
        self.app.state.transcription=service
        options=self.client.get('/browser/transcription/options').json()
        self.assertEqual(options['max_duration_seconds'],600)
        self.assertGreater(options['request_timeout_seconds'],service.settings['processing_timeout_seconds'])
        response=self.client.post('/browser/transcription',content=test_wave(),headers=self.headers)
        self.assertEqual(response.status_code,200);self.assertTrue(response.json()['complete'])
        self.assertNotIn('synthetic private transcript',self.output.getvalue())
        self.assertIsNone(self.audit.finish.call_args.kwargs['request_body']);self.assertIsNone(self.audit.finish.call_args.kwargs['response_body'])

    def test_worker_failure_returns_standard_error_without_partial_output(self):
        service=LocalTranscription({})
        service.transcribe=lambda *args,**kwargs:(_ for _ in ()).throw(SpeechError('TRANSCRIPTION_TIMEOUT'))
        self.app.state.transcription=service
        response=self.client.post('/browser/transcription',content=test_wave(),headers=self.headers)
        self.assertEqual(response.status_code,504);self.assertEqual(response.json()['error']['code'],'TRANSCRIPTION_TIMEOUT')
        self.assertNotIn('text',response.json());self.assertTrue(service.acquire());service.release()
