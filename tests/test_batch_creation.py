"""Atomic array creation contracts in memory and exclusively owned QA databases."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import test_api as api
import test_catalogue_api as legacy
from app.audit_context import bounded_mutation_details
from app.catalogue_repository import CatalogueRepository
from app.config import ConfigurationError, PROJECT_ROOT, load_config
from app.creation_limits import CreationBodyLimitMiddleware
from app.database_test import TestRepository
from app.errors import AuditUnavailable, load_error_codes
from app.schemas.catalogue import RESOURCES


class BatchCreationUnitTests(unittest.TestCase):
    setUpClass = classmethod(api.APITests.setUpClass.__func__)
    setUp = api.APITests.setUp
    bearer = api.APITests.bearer

    def test_invalid_shapes_item_indexes_and_configured_limit(self):
        headers = self.bearer('test:write')
        for body in ([], [[{'value': 'nested'}]], [None], [1], ['secret-input'],
                     [{'value': 'valid'}, {'value': None}], [{'value': 'valid'}, {'id': 42}],
                     [True], None, 'secret-input'):
            response = self.client.post('/test', headers=headers, json=body)
            self.assertEqual(response.status_code, 422)
            self.assertEqual(response.json()['error']['code'], 'VALIDATION_ERROR')
            self.assertNotIn('secret-input', response.text)
            if isinstance(body, list) and body:
                self.assertTrue(any(isinstance(part, int) for d in response.json()['error']['details'] for part in d['loc']))
        with patch.dict(self.config['api'], max_batch_size=2), patch.object(TestRepository, 'create_many') as create:
            response = self.client.post('/test', headers=headers, json=[{'value': str(i)} for i in range(3)])
            self.assertEqual(response.status_code, 422)
            self.assertEqual(response.json()['error']['details'][0]['type'], 'batch_too_large')
            create.assert_not_called()
        response = self.client.post('/test', headers=headers, json=[{'value': 'x'}] * 301)
        self.assertEqual(response.status_code, 422)
        with patch.object(TestRepository, 'create_many') as create:
            response = self.client.post('/test', headers=self.bearer('test:read'), json=[{'value': 'denied'}])
            self.assertEqual(response.status_code, 403)
            create.assert_not_called()

    def test_openapi_shapes_examples_and_scope_exclusions(self):
        schema = self.app.openapi()
        for path in ['/test', *('/' + name for name in RESOURCES)]:
            operation = schema['paths'][path]['post']
            content = operation['requestBody']['content']['application/json']
            self.assertEqual(len(content['schema']['anyOf']), 2)
            self.assertIsInstance(content['examples']['single']['value'], dict)
            self.assertIsInstance(content['examples']['batch']['value'], list)
            array = next(branch for branch in content['schema']['anyOf'] if branch.get('type') == 'array')
            self.assertEqual(array['minItems'], 1)
            response = operation['responses']['201']['content']['application/json']['schema']['anyOf']
            record = schema['paths'][path + '/{id}']['get']['responses']['200']['content']['application/json']['schema']
            self.assertIn(record, response)
            batch = next(branch for branch in response if branch != record)
            result = schema['components']['schemas'][batch['$ref'].split('/')[-1]]
            self.assertEqual(result['properties']['items']['items'], record)
            self.assertNotIn('page', result['properties'])
        for path in ('/token', '/users'):
            body = schema['paths'][path]['post']['requestBody']['content']
            self.assertNotIn('anyOf', next(iter(body.values()))['schema'])
        self.assertNotIn('post', schema['paths']['/api_audit_logs'])

    def test_streamed_body_limit_before_parsing_and_capture_separation(self):
        async def exercise(chunks, limit):
            forwarded, sent = [], []
            async def app(scope, receive, send):
                forwarded.append(await receive())
                await send({'type': 'http.response.start', 'status': 201, 'headers': []})
                await send({'type': 'http.response.body', 'body': b'{}'})
            iterator = iter(chunks)
            async def receive():
                return next(iterator)
            async def send(message):
                sent.append(message)
            middleware = CreationBodyLimitMiddleware(app, {'api': {'max_creation_body_bytes': limit}}, load_error_codes())
            await middleware({'type': 'http', 'method': 'POST', 'path': '/test', 'headers': []}, receive, send)
            return forwarded, sent
        chunks = [{'type': 'http.request', 'body': b'[{"value":', 'more_body': True},
                  {'type': 'http.request', 'body': b'"valid"}]', 'more_body': False}]
        forwarded, sent = asyncio.run(exercise(chunks, 10))
        self.assertFalse(forwarded)
        self.assertEqual(sent[0]['status'], 422)
        self.assertIn(b'creation_body_too_large', sent[1]['body'])
        forwarded, sent = asyncio.run(exercise(chunks, 100))
        self.assertEqual(forwarded[0]['body'], b'[{"value":"valid"}]')
        headers = self.bearer()
        with patch.dict(self.config['api'], max_creation_body_bytes=1024), patch.object(TestRepository, 'create_many') as create:
            response = self.client.post('/test', headers=headers, json=[{'value': 'x' * 1024}])
            self.assertEqual(response.status_code, 422)
            self.assertTrue(response.headers['X-Interaction-ID'])
            create.assert_not_called()

    def test_configuration_bounds_defaults_and_bounded_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base = json.loads((PROJECT_ROOT / '.app.config.example').read_text(encoding='utf-8'))
            base.pop('api')
            (root / '.app.config').write_text(json.dumps(base), encoding='utf-8')
            self.assertEqual(load_config(root)['api'], {'max_batch_size': 300, 'max_creation_body_bytes': 4194304})
            for settings in ([], {'max_batch_size': True}, {'max_batch_size': 0}, {'max_batch_size': 10001},
                             {'max_creation_body_bytes': 0}, {'max_creation_body_bytes': '4194304'}):
                (root / '.app.config').write_text(json.dumps({**base, 'api': settings}), encoding='utf-8')
                with self.assertRaises(ConfigurationError):
                    load_config(root)
        value = bounded_mutation_details({'operation': 'batch_create', 'created_count': 300,
            'requested_count': 300, 'created_ids': ['WK' + '1' * 40] * 20, 'shifted_count': 0}, 256)
        self.assertEqual(value['created_count'], 300)
        self.assertTrue(value['created_ids_omitted'])
        self.assertLessEqual(len(json.dumps(value).encode()), 256)
        value = bounded_mutation_details({'operation': 'batch_create', 'created_count': 300,
            'requested_count': 300, 'created_ids': ['WC' + '1' * 40] * 20, 'shifted_count': 45000,
            'reordering': {'action': 'batch_insert', 'affected_count': 45300, 'shifted_count': 45000,
                          'shifted_records': [{'id': 'WC0000001'}] * 20}}, 256)
        self.assertEqual(value['created_count'], 300)
        self.assertEqual(value['shifted_count'], 45000)
        self.assertLessEqual(len(json.dumps(value).encode()), 256)


@unittest.skipUnless(os.environ.get('FOUNDATION_RUN_INTEGRATION') == '1', 'Requires owned disposable Docker integration')
class BatchCreationIntegrationTests(unittest.TestCase):
    setUpClass = classmethod(legacy.CatalogueAPITests.setUpClass.__func__)
    cleanup = classmethod(legacy.CatalogueAPITests.cleanup.__func__)
    setUp = legacy.CatalogueAPITests.setUp
    call = legacy.CatalogueAPITests.call
    create = legacy.CatalogueAPITests.create
    graph = legacy.CatalogueAPITests.graph

    def audit(self, response):
        return self.call('GET', '/api_audit_logs', params={'interaction_id': response.headers['X-Interaction-ID']}).json()['items'][0]

    def count(self, table):
        return self.call('GET', '/' + table).json()['count']

    def test_all_resources_single_one_several_and_300_ordered_records(self):
        baseline = self.graph()
        # Distinct existing tags permit 304 category relationships without weakening uniqueness.
        tags = []
        for size in (300, 4):
            tags += self.call('POST', '/tags', expected=201, json=[{'tag_name': 'prerequisite', 'display_name_tags': 'Prerequisite'}] * size).json()['items']
        for table, resource in RESOURCES.items():
            before = self.count(table)
            offset = 0
            for size in (1, 3, 300):
                payload = [{key: baseline[table][key] for key in resource.fields} for _ in range(size)]
                for index, item in enumerate(payload):
                    if table == 'tag_category_relationships':
                        item['id_tags'] = tags[offset + index]['id_tags']
                    if table == 'work_classifications':
                        item.pop('tier')
                    for key in ('title', 'platform_name', 'display_name_tags', 'display_name_tag_categories', 'observations'):
                        if key in item:
                            item[key] = 'Ordered ' + str(index)
                response = self.call('POST', '/' + table, expected=201, json=payload)
                result = response.json()
                self.assertEqual(set(result), {'created_count', 'items'})
                self.assertEqual(result['created_count'], size)
                ids = [row[resource.key] for row in result['items']]
                self.assertEqual(len(ids), len(set(ids)))
                for index, row in enumerate(result['items']):
                    for key, value in payload[index].items():
                        if key not in ('watched_at',):
                            self.assertEqual(row[key], value)
                    self.assertIsNotNone(row['created_at'])
                for row in (result['items'][0], result['items'][-1]):
                    self.assertEqual(self.call('GET', '/' + table + '/' + row[resource.key]).json(), row)
                evidence = self.audit(response)
                self.assertEqual(evidence['mutation_count'], size)
                self.assertEqual(evidence['mutation_details']['created_count'], size)
                self.assertIsNone(evidence['target_id'])
                self.assertIsNone(evidence['differences'])
                offset += size
            self.assertEqual(self.count(table), before + 304)
            self.assertEqual(self.call('GET', '/' + table + '/' + baseline[table][resource.key]).json(), baseline[table])
        for size in (1, 3, 300):
            payload = [{'value': 'Test ordered ' + str(index)} for index in range(size)]
            response = self.call('POST', '/test', role='standard', expected=201, json=payload)
            self.assertEqual([row['value'] for row in response.json()['items']], [item['value'] for item in payload])
            self.assertEqual(response.json()['created_count'], size)
            for row in (response.json()['items'][0], response.json()['items'][-1]):
                self.assertEqual(self.call('GET', '/test/' + str(row['id'])).json(), row)

    def test_validation_and_database_failures_roll_back_with_indexes(self):
        for table, body in [('works', [{'title': 'Valid', 'title_language': 'en'}, {'title': 'Missing language'}]),
                            ('test', [{'value': 'Valid'}, {'value': None}])]:
            before = self.count(table)
            response = self.call('POST', '/' + table, expected=422, json=body)
            self.assertTrue(any(d['loc'][:2] == ['body', 1] for d in response.json()['error']['details']))
            self.assertEqual(self.count(table), before)
            self.assertEqual(self.audit(response)['mutation_count'], 0)
        rows = self.graph()
        failures = [
            ('watchlist_entries', [{'id_works': rows['works']['id_works']}, {'id_works': 'WK999999999'}], 409),
            ('watch_history', [{'id_works': rows['works']['id_works']}, {'id_works': rows['works']['id_works'], 'watched_at': '2026-10-25T01:30:00Z', 'watched_at_timezone': 'Asia/Tokyo'}], 422),
            ('tag_category_relationships', [{'id_tags': self.target['id_tags'], 'id_tag_categories': rows['tag_categories']['id_tag_categories']}] * 2, 409),
            ('work_tags', [{'id_works': rows['works']['id_works'], 'id_tags': rows['tags']['id_tags']}, {'id_works': rows['works']['id_works']}], 422),
        ]
        other = self.create('works', title='Other', title_language='en')
        failures.append(('watch_history', [{'id_works': rows['works']['id_works']},
            {'id_works': other['id_works'], 'id_work_availabilities': rows['work_availabilities']['id_work_availabilities']}], 409))
        for table, body, status in failures:
            before = self.count(table)
            response = self.call('POST', '/' + table, expected=status, json=body)
            self.assertTrue(any(d['loc'][:2] == ['body', 1] for d in response.json()['error']['details']))
            self.assertNotIn('SQL', response.text)
            self.assertEqual(self.count(table), before)
            evidence = self.audit(response)
            self.assertEqual(evidence['mutation_count'], 0)
            self.assertEqual(evidence['business_outcome'], 'rolled_back')

    def test_classification_sequential_tiers_final_records_rollback_and_concurrency(self):
        original = self.create('work_classifications', work_classification_name='original', display_name_work_classifications='Keep')
        body = [{'work_classification_name': name, 'display_name_work_classifications': name, **tier}
                for name, tier in [('first', {}), ('second', {'tier': 1}), ('third', {'tier': 2})]]
        response = self.call('POST', '/work_classifications', expected=201, json=body)
        self.assertEqual([row['work_classification_name'] for row in response.json()['items']], ['first', 'second', 'third'])
        self.assertEqual([row['tier'] for row in response.json()['items']], [4, 1, 2])
        for row in response.json()['items']:
            self.assertEqual(self.call('GET', '/work_classifications/' + row['id_work_classifications']).json(), row)
        evidence = self.audit(response)
        self.assertEqual(evidence['mutation_count'], 7)
        self.assertEqual(evidence['mutation_details']['shifted_count'], 4)
        self.assertEqual(evidence['mutation_details']['reordering']['affected_count'], 7)
        before = self.call('GET', '/work_classifications').json()['items']
        failed = self.call('POST', '/work_classifications', expected=422, json=[body[1], {**body[2], 'tier': 999}])
        self.assertEqual(failed.json()['error']['details'][0]['loc'], ['body', 1, 'tier'])
        self.assertEqual(self.call('GET', '/work_classifications').json()['items'], before)
        self.assertEqual(self.audit(failed)['mutation_count'], 0)
        def create_batch(index):
            return self.client.post('/work_classifications', headers=self.headers['supervisor'], json=[
                {'work_classification_name': 'concurrent_' + str(index), 'display_name_work_classifications': 'Concurrent', 'tier': 1}] * 3)
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(create_batch, range(2)))
        self.assertEqual([r.status_code for r in responses], [201, 201])
        rows = self.call('GET', '/work_classifications').json()['items']
        self.assertEqual([row['tier'] for row in rows], list(range(1, 11)))
        kept = next(row for row in rows if row['id_work_classifications'] == original['id_work_classifications'])
        self.assertEqual(kept['display_name_work_classifications'], 'Keep')

    def test_roles_revalidation_and_one_business_connection(self):
        body = [{'title': 'Batch', 'title_language': 'en'}] * 3
        self.call('POST', '/works', role='standard', expected=403, json=body)
        self.call('POST', '/works', role='administrator', expected=201, json=body)
        original = CatalogueRepository.create_many
        def measured(repository, payloads, actor):
            with patch.object(self.provider, 'connection', wraps=self.provider.connection) as acquire:
                result = original(repository, payloads, actor)
                self.assertEqual(acquire.call_count, 1)
                return result
        with patch.object(CatalogueRepository, 'create_many', measured):
            self.call('POST', '/works', expected=201, json=body)
        for role in ('standard', 'supervisor', 'administrator'):
            self.call('POST', '/test', role=role, expected=201, json=[{'value': role}])
        def demote(repository, payloads, actor):
            with self.provider.connection() as connection:
                connection.execute("UPDATE api_users SET role='standard' WHERE id=%s", (self.accounts['supervisor'].id,))
            return original(repository, payloads, actor)
        before = self.count('works')
        with patch.object(CatalogueRepository, 'create_many', demote):
            self.call('POST', '/works', expected=403, json=body)
        self.assertEqual(self.call('GET', '/works', role='administrator').json()['count'], before)
        test_create = TestRepository.create_many
        def revoke(repository, payloads, actor):
            with self.provider.connection() as connection:
                connection.execute('UPDATE api_users SET credential_version=credential_version+1 WHERE id=%s', (self.accounts['standard'].id,))
            return test_create(repository, payloads, actor)
        with patch.object(TestRepository, 'create_many', revoke):
            self.call('POST', '/test', role='standard', expected=401, json=[{'value': 'Revoked'}])

    def test_audit_failure_atomicity_and_300_item_capture_limits(self):
        for table, target, body in [('works', 'app.catalogue_repository.batch_evidence', [{'title': 'No commit', 'title_language': 'en'}] * 3),
                                    ('test', 'app.database_test.batch_evidence', [{'value': 'No commit'}] * 3)]:
            before = self.count(table)
            with patch(target, side_effect=AuditUnavailable('Mandatory audit unavailable')):
                response = self.call('POST', '/' + table, expected=503, json=body)
            self.assertEqual(response.json()['error']['code'], 'AUDIT_UNAVAILABLE')
            self.assertEqual(self.count(table), before)
            evidence = self.audit(response)
            self.assertEqual(evidence['mutation_count'], 0)
            self.assertEqual(evidence['business_outcome'], 'rolled_back')
        with patch.dict(self.config['audit'], mutation_max_bytes=256):
            response = self.call('POST', '/test', role='standard', expected=201, json=[{'value': 'Batch payload ' + 'x' * 4000}] * 300)
        evidence = self.audit(response)
        self.assertEqual(evidence['mutation_count'], 300)
        self.assertEqual(evidence['mutation_details']['created_count'], 300)
        self.assertTrue(evidence['mutation_details']['created_ids_omitted'])
        self.assertLessEqual(len(json.dumps(evidence['mutation_details']).encode()), 256)
        self.assertIsNone(evidence['request_body'])
        self.assertIsNone(evidence['response_body'])
        self.assertTrue(evidence['capture']['request']['truncated'])
        self.assertTrue(evidence['capture']['response']['truncated'])
        self.assertIsNone(evidence['differences'])
        with patch.dict(self.config['api'], max_batch_size=301):
            self.call('POST', '/test', role='standard', expected=201, json=[{'value': 'Configured larger'}] * 301)
