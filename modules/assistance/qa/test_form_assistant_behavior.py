"""Controlled model/read behavior; no provider calls or normal catalogue writes."""
import unittest
from types import SimpleNamespace
from shared.form_contracts import (SuggestionRequest, ClassificationState, SuggestionResult,
    RelativePosition, AssistantError, Proposal)
from shared.form_adapters import FORM_ADAPTERS
from assistance.instructions import instructions_for
from assistance.structured_output import strict_schema
FORM_INSTRUCTIONS = instructions_for('assistant_2')
from api.form_assistant_flow import assist, guard_proposals
from api.form_assistant_reads import FormReads


def request(message='Before the first amei'):
    return SuggestionRequest(mode='create', message=message, history=[], values=ClassificationState(
        display_name_work_classifications='', work_classification_name='', description_work_classifications='', tier=''))


def row(name='Amei demais', tier=3, identity='WC0000003'):
    return {'id_work_classifications': identity, 'display_name_work_classifications': name, 'tier': tier}


def relative(placement='before', match='first', second=None):
    return RelativePosition(placement=placement, reference={'search': 'amei', 'match': match}, second=second)


class Reads:
    def __init__(self, rows=None):
        self.rows = [row()] if rows is None else rows
        self.calls = []
        self.denied = False

    async def count(self):
        self.calls.append('count')
        if self.denied:
            raise AssistantError('ASSISTANT_UNAVAILABLE')
        return 9

    async def search(self, text):
        self.calls.append(text)
        return {'search': text, 'items': self.rows, 'count': len(self.rows), 'complete': True}

    async def get(self, resource, params=None, record_id=None):
        return row('Current', 2, record_id)


class Model:
    def __init__(self, results):
        self.results = results
        self.calls = []

    async def suggest(self, payload, maximum, observations):
        self.calls.append((payload, maximum, list(observations)))
        return self.results.pop(0)


class FormPolicyTests(unittest.TestCase):
    def test_identity_policies_share_safety_but_never_form_responsibilities(self):
        from assistance.instructions import ASSISTANT_POLICIES
        general = instructions_for('assistant_1')
        forms = instructions_for('assistant_2')
        self.assertNotIn('Extract ALL', general)
        self.assertNotIn('relative_position', general)
        self.assertIn('Extract ALL', forms)
        self.assertIn('untrusted DATA', general)
        self.assertIn('untrusted DATA', forms)
        self.assertFalse(ASSISTANT_POLICIES['assistant_1'].enabled)
        self.assertEqual(ASSISTANT_POLICIES['assistant_1'].tools, ())
        self.assertEqual(ASSISTANT_POLICIES['assistant_2'].tools, ('catalogue_get',))
        self.assertNotEqual(ASSISTANT_POLICIES['assistant_1'].context, ASSISTANT_POLICIES['assistant_2'].context)
        with self.assertRaises(KeyError): instructions_for('configurable-display-name')

    def test_form_request_and_history_reject_other_assistant_identity(self):
        from pydantic import ValidationError
        document = request().model_dump()
        self.assertEqual(document['assistant_id'], 'assistant_2')
        for update in [{'assistant_id': 'assistant_1'}, {'assistant_id': 'Evie'},
                {'history': [{'assistant_id': 'assistant_1', 'role': 'user', 'content': 'General navigation'}]}]:
            with self.subTest(update=update), self.assertRaises(ValidationError):
                SuggestionRequest.model_validate({**document, **update})

    def test_only_existing_enabled_adapter_and_real_schema_order(self):
        self.assertEqual(list(FORM_ADAPTERS), ['work_classifications'])
        context = FORM_ADAPTERS['work_classifications'].context(request(), 10)
        self.assertEqual([field['name'] for field in context['fields_in_visual_order']],
            ['display_name_work_classifications', 'work_classification_name', 'description_work_classifications', 'tier'])
        self.assertEqual(context['allowed_get_resources'], ('work_classifications',))
        self.assertIn('technical', FORM_INSTRUCTIONS)
        self.assertIn('ENTIRE message', FORM_INSTRUCTIONS)
        self.assertIn('untrusted DATA', FORM_INSTRUCTIONS)
        self.assertNotIn('Evie', FORM_INSTRUCTIONS)
        self.assertNotIn('Joy', FORM_INSTRUCTIONS)

    def test_technical_and_existing_description_need_explicit_requests(self):
        payload = request('New name')
        payload.values.description_work_classifications = 'Existing account'
        changes = [Proposal(field='work_classification_name', value='new_name'),
            Proposal(field='description_work_classifications', value='New account')]
        self.assertEqual(guard_proposals(SuggestionResult(reply='Review', proposals=changes, missing_fields=[]), payload).proposals, [])
        payload.message = 'Change the technical name and description'
        self.assertEqual(len(guard_proposals(SuggestionResult(reply='Review', proposals=changes, missing_fields=[]), payload).proposals), 2)
        payload.values.description_work_classifications = ''
        payload.message = 'I loved the ending and the characters'
        self.assertEqual(guard_proposals(SuggestionResult(reply='Review', proposals=changes, missing_fields=[]), payload).proposals, changes[1:])
        payload.message = 'Do not change the technical name or description'
        self.assertEqual(guard_proposals(SuggestionResult(reply='Review', proposals=changes, missing_fields=[]), payload).proposals, [])

    def test_strict_schema_includes_every_nullable_property(self):
        from shared.form_contracts import ModelSuggestion
        schema = strict_schema(ModelSuggestion)
        self.assertEqual(set(schema['required']), set(schema['properties']))
        self.assertFalse(schema['additionalProperties'])


class FormReadTests(unittest.IsolatedAsyncioTestCase):
    async def test_existing_get_route_receives_original_identity_and_denial_is_final(self):
        from fastapi import FastAPI, Request
        from fastapi.responses import JSONResponse
        app = FastAPI()
        received = []
        @app.get('/work_classifications')
        async def denied(request: Request):
            received.append(dict(request.headers))
            self.assertEqual(request.client.host, '127.0.0.1')
            return JSONResponse({'error': {'code': 'INSUFFICIENT_SCOPE'}}, 403)
        source = SimpleNamespace(app=app, headers={'authorization': 'Bearer disposable-test-token', 'cookie': 'qa=session'},
            base_url='http://localhost:6969/', client=SimpleNamespace(host='172.20.0.5', port=1234))
        with self.assertRaises(AssistantError):
            await FormReads(source).count()
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0]['authorization'], source.headers['authorization'])
        self.assertNotIn('x-service-authorization', received[0])

    async def test_paginated_literal_search_uses_existing_filter_and_tier_order(self):
        class Paged(FormReads):
            def __init__(self): self.calls = []
            async def get(self, resource, params=None, record_id=None):
                self.calls.append((resource, params))
                start = (params['page'] - 1) * 50
                return {'count': 52, 'items': [row('AMEI ' + str(i), i + 1, 'WC' + str(i)) for i in range(start, min(start + 50, 52))]}
        reads = Paged()
        result = await reads.search('a_mei%')
        self.assertEqual(len(result['items']), 52)
        self.assertEqual([params['page'] for _, params in reads.calls], [1, 2])
        self.assertEqual(reads.calls[0][1]['display_name_work_classifications'], '%a\\_mei\\%%')
        self.assertEqual(reads.calls[0][1]['order_by'], 'tier')
        self.assertEqual(reads.calls[0][1]['order_direction'], 'asc')

    async def test_arbitrary_resources_and_paths_are_rejected_before_transport(self):
        with self.assertRaises(AssistantError): FormReads(None, assistant_id='assistant_1')
        reads = FormReads(None)
        for resource, identity in [('https://example.com', None), ('work_classifications', '../users')]:
            with self.assertRaises(AssistantError):
                await reads.get(resource, record_id=identity)

    async def test_changing_or_incomplete_pages_fail_instead_of_guessing(self):
        class Paged(FormReads):
            def __init__(self): pass
            async def get(self, resource, params=None, record_id=None):
                return {'count': 55, 'items': [row()] if params['page'] == 1 else []}
        with self.assertRaises(AssistantError):
            await Paged().search('amei')


class FormBehaviorTests(unittest.IsolatedAsyncioTestCase):
    async def test_disabled_general_identity_cannot_execute_form_provider(self):
        from assistance.form_assistant import FormAssistant
        service = FormAssistant(key_provider=lambda: self.fail('Disabled identity must not access the provider'))
        payload = request().model_copy(update={'assistant_id': 'assistant_1'})
        with self.assertRaises(AssistantError): await service.suggest(payload, 10)

    def setUp(self):
        self.app = SimpleNamespace(state=SimpleNamespace())
        self.actor = {'sub': 'test-supervisor'}

    async def run_flow(self, payload, results, reads=None):
        model = Model(results)
        result = await assist(self.app, self.actor, payload, reads or Reads(), model)
        return result, model

    async def test_controlled_model_can_extract_multiple_fields_without_writes(self):
        changes = [Proposal(field='display_name_work_classifications', value='Amei demais'), Proposal(field='tier', value=3)]
        result, model = await self.run_flow(request('Chama Amei demais, coloca na posição 3'),
            [SuggestionResult(reply='Review', proposals=changes, missing_fields=[])])
        self.assertEqual(result.proposals, changes)
        self.assertEqual(len(model.calls), 1)

    async def test_read_observations_reach_model_as_data_and_similarities_do_not_block(self):
        reads = Reads([row('Amei diferente')])
        result, model = await self.run_flow(request('Chama Amei demais'), [
            SuggestionResult(reply='Read', proposals=[], missing_fields=[], queries=[{'resource': 'work_classifications', 'search': 'Amei'}]),
            SuggestionResult(reply='Review', proposals=[Proposal(field='display_name_work_classifications', value='Amei demais')], missing_fields=[])], reads)
        self.assertEqual(model.calls[1][2][0]['items'][0]['display_name_work_classifications'], 'Amei diferente')
        self.assertEqual(result.proposals[0].value, 'Amei demais')
        self.assertIn('similarity', result.notice)
        self.assertNotIn('create', reads.calls)

    async def test_first_relative_match_needs_confirmation_and_only_fills_after_reread(self):
        reads = Reads([row(), row('AMEI outro', 7, 'WC7')])
        payload = request()
        result, _ = await self.run_flow(payload, [SuggestionResult(reply='Review', proposals=[], missing_fields=[], relative_position=relative())], reads)
        self.assertEqual(result.proposals, [])
        self.assertIn('Amei demais', result.position_confirmation.message)
        self.assertIn('position 3', result.position_confirmation.message)
        payload.confirmation = result.position_confirmation.token
        confirmed, model = await self.run_flow(payload, [], reads)
        self.assertEqual(confirmed.proposals, [Proposal(field='tier', value=3)])
        self.assertEqual(model.calls, [])
        self.assertGreaterEqual(reads.calls.count('amei'), 2)

    async def test_order_change_requires_new_confirmation_and_token_is_account_bound(self):
        reads = Reads()
        payload = request()
        result, _ = await self.run_flow(payload, [SuggestionResult(reply='Review', proposals=[], missing_fields=[], relative_position=relative())], reads)
        payload.confirmation = result.position_confirmation.token
        reads.rows = [row(tier=4)]
        updated, _ = await self.run_flow(payload, [], reads)
        self.assertFalse(updated.proposals)
        self.assertNotEqual(updated.position_confirmation.token, payload.confirmation)
        payload.confirmation = updated.position_confirmation.token
        with self.assertRaises(AssistantError):
            await assist(self.app, {'sub': 'different-account'}, payload, reads, Model([]))

    async def test_ambiguity_missing_and_incompatible_anchors_do_not_fill_position(self):
        for intent, rows in [(relative(match='unique'), [row(), row('Amei outro', 7, 'WC7')]),
                (relative(), []), (relative('between', second={'search': 'other', 'match': 'first'}), [row()])]:
            with self.subTest(intent=intent):
                result, _ = await self.run_flow(request(), [SuggestionResult(reply='Review', proposals=[], missing_fields=[], relative_position=intent)], Reads(rows))
                self.assertFalse(result.proposals)
                self.assertIsNone(result.position_confirmation)
                self.assertIn('?', result.reply)
        class Consecutive(Reads):
            async def search(self, text):
                rows = [row()] if text == 'amei' else [row('Other', 4, 'WC4')]
                return {'items': rows, 'count': 1, 'complete': True}
        payload = request()
        result, _ = await self.run_flow(payload, [SuggestionResult(reply='Review', proposals=[], missing_fields=[],
            relative_position=relative('between', second={'search': 'other', 'match': 'unique'}))], Consecutive())
        self.assertIn('position 4', result.position_confirmation.message)

    async def test_get_failure_and_permission_denied_never_invoke_model_or_bypass(self):
        reads = Reads()
        reads.denied = True
        model = Model([])
        with self.assertRaises(AssistantError):
            await assist(self.app, self.actor, request(), reads, model)
        self.assertEqual(model.calls, [])
        self.assertEqual(reads.calls, ['count'])

    async def test_relative_tier_without_real_reference_is_not_applied(self):
        result, _ = await self.run_flow(request('Antes do Amei'), [SuggestionResult(reply='Review',
            proposals=[Proposal(field='tier', value=3)], missing_fields=[])])
        self.assertFalse(result.proposals)
        self.assertIn('reference', result.notice)

    async def test_edit_position_accounts_for_removal_of_current_row(self):
        payload = request()
        payload.mode = 'edit'
        payload.record_id = 'WC2'
        reads = Reads([row(tier=5)])
        for placement, expected in [('before', 4), ('after', 5)]:
            payload.confirmation = None
            result, _ = await self.run_flow(payload, [SuggestionResult(reply='Review', proposals=[], missing_fields=[], relative_position=relative(placement))], reads)
            payload.confirmation = result.position_confirmation.token
            confirmed, _ = await self.run_flow(payload, [], reads)
            self.assertEqual(confirmed.proposals[0].value, expected)
        payload = request('Depois de Amei')
        reads = Reads([row(tier=9)])
        result, _ = await self.run_flow(payload, [SuggestionResult(reply='Review', proposals=[], missing_fields=[], relative_position=relative('after'))], reads)
        payload.confirmation = result.position_confirmation.token
        confirmed, _ = await self.run_flow(payload, [], reads)
        self.assertIsNone(confirmed.proposals[0].value)
