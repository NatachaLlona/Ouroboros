"""Assistant suggestions use fixed-model structured output and never mutate records."""
import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import httpx
from pydantic import ValidationError
from assistance.form_assistant import (AssistantError, ClassificationState, ConversationMessage, FormAssistant, ModelSuggestion,
    Proposal, SuggestionRequest, load_api_key, validate_suggestion)


def payload(message='Use the example name'):
    return SuggestionRequest(mode='create', message=message, history=[], values=ClassificationState(
        display_name_work_classifications='', work_classification_name='', description_work_classifications='', tier=''))


def document(proposals=None, reply='Review these suggestions.', model='gpt-5.4-2026-03-05'):
    return {'status':'completed','model':model,'output':[{'type':'message','content':[{'type':'output_text','text':json.dumps({
        'reply':reply,'proposals':proposals if proposals is not None else [{'field':'display_name_work_classifications','value':'Example'}]})}]}]}


class AssistantValidationTests(unittest.TestCase):
    def test_real_types_ranges_description_and_optional_clear(self):
        result=validate_suggestion(ModelSuggestion.model_validate({'reply':'Review','proposals':[
            {'field':'display_name_work_classifications','value':'Example'},
            {'field':'description_work_classifications','value':None}, {'field':'tier','value':None}]}),payload().values,'create',10)
        self.assertEqual(result.missing_fields,[])
        appended=validate_suggestion(ModelSuggestion(reply='Review',proposals=[Proposal(field='tier',value=10)]),payload().values,'create',10)
        self.assertIsNone(appended.proposals[0].value)
        for field,value in [('tier',11),('tier','2'),('work_classification_name','BAD NAME'),('display_name_work_classifications',' '),('description_work_classifications',42)]:
            with self.subTest(field=field),self.assertRaises(AssistantError):
                validate_suggestion(ModelSuggestion(reply='Review',proposals=[Proposal(field=field,value=value)]),payload().values,'create',10)
        with self.assertRaises(AssistantError):
            validate_suggestion(ModelSuggestion(reply='Review',proposals=[Proposal(field='tier',value=None)]),payload().values,'edit',10)

    def test_duplicate_extra_and_unknown_fields_are_rejected(self):
        with self.assertRaises(ValidationError):Proposal.model_validate({'field':'invented','value':'x'})
        with self.assertRaises(ValidationError):Proposal.model_validate({'field':'tier','value':True})
        with self.assertRaises(AssistantError):
            validate_suggestion(ModelSuggestion(reply='Review',proposals=[Proposal(field='tier',value=1)]*2),payload().values,'create',10)
        with self.assertRaises(ValidationError):SuggestionRequest.model_validate({**payload().model_dump(),'model':'gpt-5.4-mini'})

    def test_missing_required_information_produces_question(self):
        result=validate_suggestion(ModelSuggestion(reply='Tell me more.',proposals=[]),payload().values,'create',10)
        self.assertIn('display_name_work_classifications',result.missing_fields)
        self.assertIn('?',result.reply)

    def test_key_is_loaded_from_backend_env_without_export(self):
        with tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,{},clear=True),patch('assistance.form_assistant.ASSISTANCE_ROOT',Path(directory)):
            (Path(directory)/'.env').write_text('OPENAI_API_KEY=unit-test-placeholder\n',encoding='utf8')
            self.assertTrue(bool(load_api_key()))
            self.assertNotIn('OPENAI_API_KEY',os.environ)


class AssistantTransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_only_full_gpt54_responses_strict_schema_no_tools_no_storage(self):
        requests=[]
        def transport(request):
            body=json.loads(request.content);requests.append(body)
            return httpx.Response(200,json=document())
        service=FormAssistant(key_provider=lambda:'unit-test-placeholder',transport=httpx.MockTransport(transport))
        request=payload();request.history=[ConversationMessage(role='assistant',content='A previous reply')]
        result=await service.suggest(request,10)
        self.assertEqual(result.proposals[0].field,'display_name_work_classifications')
        body=requests[0]
        self.assertEqual(body['model'],'gpt-5.4');self.assertIs(body['store'],False)
        self.assertIs(body['text']['format']['strict'],True)
        self.assertNotIn('tools',body)
        self.assertEqual(body['input'][-1]['content'][0]['type'],'input_text')
        self.assertEqual(body['input'][-2]['content'][0]['type'],'output_text')

    async def test_invalid_output_other_models_and_secret_reflections_fail_closed(self):
        for response in [document(model='gpt-5.4-mini'),document(reply='unit-test-placeholder'),document([{'field':'tier','value':99}]),{'status':'incomplete'}]:
            service=FormAssistant(key_provider=lambda:'unit-test-placeholder',transport=httpx.MockTransport(lambda request:httpx.Response(200,json=response)))
            with self.assertRaises(AssistantError):await service.suggest(payload(),10)

    async def test_provider_errors_are_safe_and_slots_are_released(self):
        service=FormAssistant(key_provider=lambda:'unit-test-placeholder',transport=httpx.MockTransport(lambda request:httpx.Response(429,json={'private':'must not escape'})))
        with self.assertRaises(AssistantError) as result:await service.suggest(payload(),10)
        self.assertEqual(result.exception.code,'ASSISTANT_RATE_LIMITED');self.assertEqual(service._active,0)
        self.assertNotIn('private',str(result.exception))

    async def test_concurrency_limit_does_not_call_provider(self):
        service=FormAssistant(key_provider=lambda:self.fail('Key must not be read when busy'))
        service._active=2
        with self.assertRaises(AssistantError) as result:await service.suggest(payload(),10)
        self.assertEqual(result.exception.code,'ASSISTANT_BUSY')


class AssistantEndpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import test_api
        test_api.APITests.setUpClass.__func__(cls)

    def setUp(self):
        import test_api
        from test_frontend import BrowserSessionTests
        test_api.APITests.setUp(self)
        self.audit_patch=patch('api.app.audit_middleware.AuditStore')
        self.audit=self.audit_patch.start().return_value;self.audit.begin.return_value=1
        self.addCleanup(self.audit_patch.stop)
        self.count_patch=patch('api.app.endpoints.form_assistant.CatalogueRepository.page',return_value={'count':9,'items':[]})
        self.count=self.count_patch.start();self.addCleanup(self.count_patch.stop)
        self.writes=patch('api.app.catalogue_repository.CatalogueRepository.create')
        self.create_record=self.writes.start();self.addCleanup(self.writes.stop)
        self.app.state.form_assistant=FormAssistant(key_provider=lambda:'unit-test-placeholder',transport=httpx.MockTransport(lambda request:httpx.Response(200,json=document())))
        self.browser=BrowserSessionTests.browser.__get__(self)
        self.login=BrowserSessionTests.login.__get__(self)

    def test_authorized_suggestions_keep_messages_and_key_out_of_audit_and_logs(self):
        session=self.login().json()
        response=self.client.post('/browser/assistant/work-classifications',json=payload('synthetic-private-assistant-message').model_dump(),headers={'Origin':'http://localhost:6969','X-CSRF-Token':session['csrf_token']})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['proposals'][0]['field'],'display_name_work_classifications')
        self.assertNotIn('synthetic-private-assistant-message',self.output.getvalue())
        self.assertNotIn('unit-test-placeholder',self.output.getvalue())
        completion=self.audit.finish.call_args.kwargs
        self.assertIsNone(completion['request_body']);self.assertIsNone(completion['response_body'])
        self.count.assert_called_once();self.create_record.assert_not_called()

    def test_authentication_csrf_and_current_role_are_required(self):
        from dataclasses import replace
        self.browser()
        self.assertEqual(self.client.post('/browser/assistant/work-classifications',json=payload().model_dump()).status_code,401)
        session=self.login().json()
        self.assertEqual(self.client.post('/browser/assistant/work-classifications',json=payload().model_dump(),headers={'Origin':'http://localhost:6969'}).status_code,403)
        self.users.users[self.user.id]=replace(self.users.users[self.user.id],role='standard')
        self.assertEqual(self.client.post('/browser/assistant/work-classifications',json=payload().model_dump(),headers={'Origin':'http://localhost:6969','X-CSRF-Token':session['csrf_token']}).status_code,403)
        self.count.assert_not_called();self.create_record.assert_not_called()

    def test_unrecognized_fields_are_rejected_without_echoing_input(self):
        session=self.login().json()
        response=self.client.post('/browser/assistant/work-classifications',json={**payload().model_dump(),'unexpected':'private-invalid-input'},headers={'Origin':'http://localhost:6969','X-CSRF-Token':session['csrf_token']})
        self.assertEqual(response.status_code,422);self.assertNotIn('private-invalid-input',response.text)
        self.count.assert_not_called();self.create_record.assert_not_called()
