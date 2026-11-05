"""Container boundaries, delegated authority and controlled inference failures."""
from support_config import example_config, example_path, config_path, config_example_path
import asyncio
import json
import unittest
import contextlib
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch
import httpx
from fastapi.testclient import TestClient
from shared.service_auth import delegate, DelegationVerifier
from assistance.main import create_assistance
from api.assistance_client import AssistanceClient
from shared.speech import SpeechError, transcription_settings


KEY = b'disposable-service-key-for-unit-tests-only'
ACTOR = {'sub': '7', 'role': 'supervisor'}


class DelegationTests(unittest.TestCase):
    def test_signature_body_operation_expiration_and_replay_are_bound(self):
        now = [100]
        verifier = DelegationVerifier(KEY, clock=lambda: now[0])
        token = delegate(KEY, 'transcribe', b'owned audio', ACTOR, clock=lambda: now[0])
        for operation, body in [('suggest', b'owned audio'), ('transcribe', b'changed')]:
            with self.assertRaises(ValueError):
                verifier.verify(token, operation, body)
        self.assertEqual(verifier.verify(token, 'transcribe', b'owned audio')['subject'], '7')
        with self.assertRaises(ValueError):
            verifier.verify(token, 'transcribe', b'owned audio')
        token = delegate(KEY, 'options', b'', ACTOR, clock=lambda: now[0])
        now[0] += 31
        with self.assertRaises(ValueError):
            verifier.verify(token, 'options', b'')
        with self.assertRaises(ValueError):
            verifier.verify(token[:-1]+'x', 'options', b'')


class FakeSpeech:
    settings = transcription_settings({})
    acquired = False

    def acquire(self):
        self.acquired = True
        return True

    def release(self):
        self.acquired = False

    def transcribe(self, data, cancelled):
        return {'text': 'Disposable fixture.', 'language': 'en', 'complete': True, 'duration_seconds': 1}


class AssistanceBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.speech = FakeSpeech()
        self.client = TestClient(create_assistance(config={'transcription': {}}, speech=self.speech,
            verifier=DelegationVerifier(KEY), assistant=object()))

    def headers(self, operation, body):
        return {'X-Service-Authorization': delegate(KEY, operation, body, ACTOR)}

    def test_browser_cannot_supply_roles_instead_of_delegation(self):
        self.assertEqual(self.client.post('/internal/options', headers={'X-Role': 'administrator', 'X-User-ID': '7'}).status_code, 401)
        self.assertFalse(self.speech.acquired)

    def test_runtime_options_and_full_audio_response_require_signed_requests(self):
        result = self.client.post('/internal/options', content=b'', headers=self.headers('options', b''))
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()['max_duration_seconds'], 600)
        self.assertNotIn('cache_directory', result.json())
        body = b'disposable fixture'
        response = self.client.post('/internal/transcribe', content=body, headers=self.headers('transcribe', body))
        self.assertEqual(response.status_code, 200)
        self.assertIs(response.json()['complete'], True)
        self.assertFalse(self.speech.acquired)

    def test_failure_never_returns_partial_text_and_releases_capacity(self):
        body = b'disposable fixture'
        with patch.object(self.speech, 'transcribe', side_effect=SpeechError('TRANSCRIPTION_TIMEOUT')):
            response = self.client.post('/internal/transcribe', content=body, headers=self.headers('transcribe', body))
        self.assertEqual(response.status_code, 504)
        self.assertNotIn('text', response.json())
        self.assertFalse(self.speech.acquired)

    def test_api_client_fails_closed_without_running_local_inference(self):
        client = AssistanceClient({})
        with patch('assistance.transcription.LocalTranscription.model') as model:
            with self.assertRaises(SpeechError):
                asyncio.run(client.call('options', b'', ACTOR))
        model.assert_not_called()


class ModuleOrchestrationTests(unittest.TestCase):
    def test_launcher_help_does_not_import_host_site_packages(self):
        root=Path(__file__).resolve().parents[1]
        result=subprocess.run([sys.executable,'-S',str(root/'start.py'),'--help'],capture_output=True)
        self.assertEqual(result.returncode,0)
        self.assertIn(b'--api-only',result.stdout)

    def test_assistance_failure_does_not_prevent_frontend_startup(self):
        from orchestration import main, StartupError
        calls=[]
        def run(command,*args,**kwargs):
            calls.append(command)
            if ('up' in command or 'build' in command) and command[-1]=='assistance':raise StartupError('Owned inference unavailable')
            return SimpleNamespace(stdout=b'owned-container')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'.secrets').mkdir();(root/'.secrets/postgres_password').touch()
            settings={'project_name':'unit-module','startup_timeout_seconds':20,'public_host':'127.0.0.1','public_port':6969}
            with patch('orchestration.prepare',return_value=({'database':{}},{},settings)), patch('orchestration.environment',return_value={}), patch('orchestration.run',side_effect=run), patch('api.app.database.check_docker'), patch('api.app.database.start_postgres'), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(root,[]),0)
        self.assertTrue(any('up' in command and command[-1]=='frontend' for command in calls))
        self.assertFalse(any('down' in command or '--volumes' in command for command in calls))

    def test_five_configs_preserve_values_and_do_not_read_retired_paths(self):
        from orchestration import prepare
        source=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for module in ('','api','database','assistance','frontend'):
                folder=root/module;folder.mkdir(exist_ok=True)
                (folder/'config.example.json').write_bytes((source/module/'config.example.json').read_bytes())
            with patch('api.app.credentials.write_secret'):
                prepare(root)
                path=root/'frontend/config.json';custom=json.loads(path.read_text());custom['nome_assistente']='Customized assistant'
                path.write_text(json.dumps(custom),encoding='utf-8')
                (root/'.app.config').write_text('invalid retired configuration',encoding='utf-8')
                prepare(root)
            self.assertEqual(json.loads(path.read_text())['nome_assistente'],'Customized assistant')
            for module in ('','api','database','assistance','frontend'):
                self.assertTrue((root/module/'config.json').is_file())
            self.assertNotIn('infrastructure',json.loads((root/'api/config.json').read_text()))

    def test_forwarded_client_address_is_accepted_only_from_resolved_frontend(self):
        from api.app.proxy import FrontendProxyMiddleware
        observed=[]
        async def app(scope,receive,send):observed.append(scope)
        with patch.dict(os.environ,{'OUROBOROS_BROWSER_PROXY_HOST':'frontend'}), patch('api.app.proxy.socket.getaddrinfo',return_value=[(None,None,None,None,('172.20.0.2',0))]):
            middleware=FrontendProxyMiddleware(app)
            for source in ('172.20.0.2','172.20.0.9'):
                asyncio.run(middleware({'type':'http','client':(source,100),'headers':[(b'x-forwarded-for',b'127.0.0.1')]},None,None))
        self.assertTrue(observed[0]['verified_frontend_proxy'])
        self.assertEqual(observed[0]['client'][0],'127.0.0.1')
        self.assertNotIn('verified_frontend_proxy',observed[1])
        self.assertEqual(observed[1]['client'][0],'172.20.0.9')
