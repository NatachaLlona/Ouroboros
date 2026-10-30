"""Real HTTP/schema/authorization contracts in exclusively owned disposable storage."""
import io
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import tempfile
import threading
import time
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient
from app.api_credentials import PASSWORD_HASHER
from app.api_users import APIUserStore, UserManagementError
from app.auth import AuthService
from app.config import PROJECT_ROOT
from app.credentials import write_secret
from app.database import (Database, check_docker, compose_command, compose_environment,
                          connect, ensure_database, run_command, start_postgres)
from app.logger import ApplicationLogger
from app.main import create_app
from app.migrate import migrate
from app.schemas.catalogue import RESOURCES, PATTERN_HELP


@unittest.skipUnless(os.environ.get('FOUNDATION_RUN_INTEGRATION') == '1', 'Requires owned disposable Docker integration')
class CatalogueAPITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Allocate one UUID cluster; each test gets a fresh database inside it."""
        check_docker()
        cls.root = Path(tempfile.mkdtemp(prefix='ouroboros-crud-'))
        cls.project = 'ouroboros-crud-' + uuid.uuid4().hex
        shutil.copy(PROJECT_ROOT / 'compose.yaml', cls.root)
        shutil.copytree(PROJECT_ROOT / 'sql', cls.root / 'sql')
        cls.config = json.loads((PROJECT_ROOT / '.app.config.example').read_text(encoding='utf-8'))
        from support_ports import approved_port
        port = approved_port('database')
        cls.db = {**cls.config['database'], 'name': 'crud_base', 'user': 'crud_master', 'port': port, 'startup_timeout': 240}
        cls.master = secrets.token_urlsafe(32)
        cls.secret = write_secret(cls.master, cls.root)
        cls.command = compose_command(cls.root, cls.project)
        cls.env = compose_environment(cls.db, cls.secret)
        cls.addClassCleanup(cls.cleanup)
        start_postgres(cls.db, cls.secret, cls.root, cls.project)
        # Docker's local-socket healthcheck can observe the temporary init server
        # before the published TCP listener is ready. Bound QA readiness by an
        # authenticated connection to this run's own ephemeral endpoint.
        from app.database import DatabaseError
        deadline = time.monotonic() + 30
        while True:
            try:
                with connect({**cls.db, 'name': 'postgres'}, cls.master):
                    break
            except DatabaseError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(.25)
        cls.api_password = secrets.token_urlsafe(24)
        cls.hashed = PASSWORD_HASHER.hash(cls.api_password)

    @classmethod
    def cleanup(cls):
        """Remove only the exact cluster allocated above, never normal resources."""
        run_command(cls.command + ['down', '--volumes'], 60, cls.env)
        shutil.rmtree(cls.root)
        cls.master = cls.api_password = cls.hashed = None

    def setUp(self):
        self.database_config = {**self.db, 'name': 'crud_' + uuid.uuid4().hex}
        ensure_database(self.database_config, self.master)
        with connect(self.database_config, self.master) as connection:
            migrate(connection, self.root)
        self.provider = Database(self.database_config, self.master)
        self.users = APIUserStore(self.provider)
        self.accounts = {role: self.users.create(role, self.hashed, role=role)
                         for role in ('administrator', 'supervisor', 'standard')}
        self.output = io.StringIO()
        self.logger = ApplicationLogger(self.config['logging'], root=self.root, stream=self.output)
        self.addCleanup(self.logger.close)
        self.auth = AuthService(self.config['auth'], secrets.token_urlsafe(64), self.users)
        self.client = TestClient(create_app(self.config, self.provider, self.auth, self.logger))
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)
        self.headers = {}
        for role in self.accounts:
            token = self.client.post('/token', data={'username': role, 'password': self.api_password})
            self.assertEqual(token.status_code, 200)
            self.headers[role] = {'Authorization': 'Bearer ' + token.json()['access_token']}

    def call(self, method, path, role='supervisor', expected=200, **kwargs):
        """Send an authenticated request; failure output contains no credentials."""
        response = self.client.request(method, path, headers=self.headers[role], **kwargs)
        self.assertEqual(response.status_code, expected, method + ' ' + path + ': ' + str(response.status_code))
        from support_log_evidence import assert_response_logs
        assert_response_logs(self, response, self.output.getvalue, self.logger)
        return response

    def create(self, table, **fields):
        return self.call('POST', '/' + table, expected=201, json=fields).json()

    def graph(self):
        """Build valid independent resources using only the public CRUD APIs."""
        rows = {}
        rows['works'] = self.create('works', title='El dragón 🐉', title_language='es')
        work = rows['works']['id_works']
        rows['platforms'] = self.create('platforms', platform_name='Library', platform_is_paid=False,
            platform_is_episodes=True, platform_is_duration_time=True)
        rows['work_availabilities'] = self.create('work_availabilities', id_works=work,
            id_platforms=rows['platforms']['id_platforms'], duration_minutes='12.5', episode_quantity=3)
        rows['tags'] = self.create('tags', tag_name='support_without_dependence', display_name_tags='Ação 💕')
        self.target = self.create('tags', tag_name='romantic_partner', display_name_tags='Romance')
        rows['tag_categories'] = self.create('tag_categories', tag_category_name='relationships', display_name_tag_categories='Vínculos')
        rows['tag_category_relationships'] = self.create('tag_category_relationships',
            id_tags=rows['tags']['id_tags'], id_tag_categories=rows['tag_categories']['id_tag_categories'])
        rows['tag_relationships'] = self.create('tag_relationships',
            id_tags_source=rows['tags']['id_tags'], id_tags_target=self.target['id_tags'])
        rows['work_classifications'] = self.create('work_classifications',
            work_classification_name='favorite', display_name_work_classifications='🏆 PQP')
        rows['watchlist_entries'] = self.create('watchlist_entries', id_works=work,
            id_work_availabilities=rows['work_availabilities']['id_work_availabilities'])
        rows['watch_history'] = self.create('watch_history', id_works=work,
            id_work_availabilities=rows['work_availabilities']['id_work_availabilities'])
        rows['work_tags'] = self.create('work_tags', id_works=work, id_tags=rows['tags']['id_tags'],
            id_watchlist_entries=rows['watchlist_entries']['id_watchlist_entries'])
        return rows

    def test_01_all_resources_crud_record_round_trips_and_deletes(self):
        rows = self.graph()
        for table, row in rows.items():
            with self.subTest(table=table):
                path = '/' + table + '/' + row['id_' + table]
                self.assertEqual(self.call('GET', path).json(), row)
                self.assertEqual(self.call('PUT', path, json=row).json(), row)
                listed = self.call('GET', '/' + table, params={'id_' + table: row['id_' + table]}).json()
                self.assertEqual([{key: value for key, value in item.items() if key != 'references'} for item in listed['items']], [row])
                self.assertEqual(listed['count'], 1)
                for immutable in RESOURCES[table].immutable:
                    changed = dict(row)
                    changed[immutable] = row[immutable] + 1 if isinstance(row[immutable], int) else 'changed'
                    self.call('PUT', path, expected=422, json=changed)
                for payload in ({}, {'unknown': 'value'}):
                    self.call('PUT', path, expected=422, json=payload)
                self.call('GET', '/' + table + '/MISSING0000001', expected=404)
                field = next(iter(RESOURCES[table].fields))
                self.call('PUT', '/' + table + '/MISSING0000001', expected=404, json={field: row[field]})
                self.call('DELETE', '/' + table + '/MISSING0000001', expected=404)
                for params in ({}, {'confirm': 'false'}, {'confirm': 'true', 'page': 1}, {'confirm': 'true', 'unknown_filter': row['id_' + table]}):
                    self.call('DELETE', '/' + table, role='administrator', expected=422, params=params)
                self.call('DELETE', '/' + table, expected=403, params={'confirm': 'true'})
        # Explicit dependency order; deleting leaves does not cascade parents.
        for table in ('work_tags', 'watchlist_entries', 'watch_history', 'tag_category_relationships',
                      'tag_relationships', 'work_availabilities', 'work_classifications', 'tag_categories', 'tags', 'platforms', 'works'):
            row = rows[table]
            response = self.call('DELETE', '/' + table + '/' + row['id_' + table], expected=204)
            self.assertEqual(response.content, b'')
            self.call('GET', '/' + table + '/' + row['id_' + table], expected=404)
            expected_count = 1 if table == 'tags' else 0
            self.assertEqual(self.call('DELETE', '/' + table, role='administrator', params={'confirm': 'true'}).json()['deleted_count'], expected_count)
            self.assertEqual(self.call('DELETE', '/' + table, role='administrator', params={'confirm': 'true'}).json()['deleted_count'], 0)
        later = self.create('works', title='Later', title_language='en')
        self.assertGreater(later['sequence_works'], rows['works']['sequence_works'])

    def test_02_partial_null_validation_relationships_and_repetitions(self):
        rows = self.graph()
        work, tag, relation = rows['works']['id_works'], rows['tags']['id_tags'], rows['tag_relationships']['id_tag_relationships']
        long_text = 'English synopsis with Unicode 🐉. ' * 3000
        path = '/works/' + work
        updated = self.call('PUT', path, json={'synopsis': long_text}).json()
        self.assertEqual(updated['title'], rows['works']['title'])
        self.assertEqual(updated['synopsis'], long_text)
        self.assertIsNone(self.call('PUT', path, json={'synopsis': None}).json()['synopsis'])
        self.call('PUT', path, expected=422, json={'title': None})
        for table, resource in RESOURCES.items():
            self.call('POST', '/' + table, expected=422, json={})
            self.call('POST', '/' + table, expected=422, json={**{key: rows[table][key] for key in resource.fields}, 'unknown': 1})
        for table, changes in [('platforms', {'price_amount': -1}), ('platforms', {'platform_is_paid': 'false'}),
                               ('work_availabilities', {'episode_quantity': 0}), ('work_availabilities', {'duration_minutes': -1}),
                               ('tags', {'tag_name': 'Not snake case'}), ('watch_history', {'watched_at': '2020-01-01T00:00:00'})]:
            self.call('PUT', '/' + table + '/' + rows[table]['id_' + table], expected=422, json=changes)
        origin_path = '/work_tags/' + rows['work_tags']['id_work_tags']
        self.call('PUT', origin_path, expected=422, json={'id_tag_relationships': relation})
        switched = self.call('PUT', origin_path, json={'id_tags': None, 'id_tag_relationships': relation}).json()
        self.assertIsNone(switched['id_tags'])
        self.call('PUT', origin_path, expected=422, json={'id_watch_history': rows['watch_history']['id_watch_history']})
        other = self.create('works', title='Other', title_language='en')['id_works']
        self.call('PUT', origin_path, expected=409, json={'id_works': other})
        for table in ('watchlist_entries', 'watch_history'):
            self.call('POST', '/' + table, expected=409, json={'id_works': other,
                'id_work_availabilities': rows['work_availabilities']['id_work_availabilities']})
        self.call('POST', '/tag_category_relationships', expected=409, json={key: rows['tag_category_relationships'][key] for key in RESOURCES['tag_category_relationships'].fields})
        for table in ('work_availabilities', 'watchlist_entries', 'watch_history', 'work_tags'):
            payload = {key: rows[table][key] for key in RESOURCES[table].fields}
            # Existing row switched above, but original direct association is still valid.
            self.call('POST', '/' + table, expected=201, json=payload)
        for table in ('work_availabilities', 'tag_relationships', 'tag_category_relationships', 'work_tags'):
            payload = {key: rows[table][key] for key in RESOURCES[table].fields}
            foreign_key = next(key for key in payload if key.startswith('id_') and payload[key] is not None)
            payload[foreign_key] = 'MISSING0000001'
            self.call('POST', '/' + table, expected=409, json=payload)

    def test_03_filters_patterns_order_fields_and_pagination(self):
        rows = self.graph()
        # Exercise numeric and timestamp equality, nullable ordering, and distinct
        # rows so acceptance alone cannot stand in for actual sort behavior.
        self.call('PUT', '/platforms/' + rows['platforms']['id_platforms'], json={'price_amount': '12.34', 'price_currency': 'EUR'})
        self.call('PUT', '/watch_history/' + rows['watch_history']['id_watch_history'], json={'watched_at': '2020-01-01T12:00:00+01:00'})
        rows['platforms'] = self.call('GET', '/platforms/' + rows['platforms']['id_platforms']).json()
        rows['watch_history'] = self.call('GET', '/watch_history/' + rows['watch_history']['id_watch_history']).json()
        self.call('GET', '/platforms', expected=422, params={'price_amount': -1})
        self.call('GET', '/work_availabilities', expected=422, params={'duration_minutes': 0})
        self.call('GET', '/watch_history', expected=422, params={'watched_at': '2020-01-01T12:00:00'})
        self.graph()
        schema = self.client.get('/openapi.json').json()
        for table, resource in RESOURCES.items():
            path, row = '/' + table, rows[table]
            params = schema['paths'][path]['get']['parameters']
            self.assertEqual({p['name'] for p in params}, set(resource.query.model_fields))
            for field in resource.columns:
                for direction in ('asc', 'desc'):
                    page = self.call('GET', path, params={'order_by': field, 'order_direction': direction}).json()
                    self.assertGreaterEqual(page['count'], 1)
                    self.assertTrue(any(item[resource.key] == row[resource.key] for item in page['items']))
                    # Cross-check PostgreSQL ordering independently of application
                    # query composition, including its actual text collation.
                    from psycopg import sql
                    with self.provider.connection() as connection, connection.cursor() as cursor:
                        cursor.execute(sql.SQL('SELECT {} FROM public.{} ORDER BY {} {} NULLS LAST, {} ASC').format(
                            sql.Identifier(resource.key), sql.Identifier(table), sql.Identifier(field),
                            sql.SQL('ASC' if direction == 'asc' else 'DESC'), sql.Identifier(resource.key)))
                        expected_ids = [value[0] for value in cursor.fetchall()]
                    self.assertEqual([item[resource.key] for item in page['items']], expected_ids)
                if row[field] is not None:
                    filtered = self.call('GET', path, params={field: row[field]}).json()
                    self.assertTrue(any(item[resource.key] == row[resource.key] for item in filtered['items']))
            for invalid in ({'order_by': 'password_hash'}, {'order_by': 'id; DROP TABLE works'}, {'order_direction': 'DESC'},
                            {'page': '1.0'}, {'page': 0}, {'page_size': 9}, {'page_size': 51}):
                self.call('GET', path, expected=422, params=invalid)
            empty = self.call('GET', path, params={'page': 999999}).json()
            self.assertEqual(empty['items'], [])
            self.assertGreaterEqual(empty['count'], 1)
        values = ['Dragon', 'DRAGON', 'dragonfly', '100% pure', 'literal_under', '', "'; DROP TABLE works; --", 'tied']
        for title in values + ['tied'] * 12:
            self.create('works', title=title, title_language='en')
        for pattern, count in [('dragon', 2), ('dragon%', 3), (r'100\% pure', 1), (r'literal\_under', 1), ('', 1),
                               ("'; DROP TABLE works; --", 1), ('dr_gon', 2)]:
            self.assertEqual(self.call('GET', '/works', params={'title': pattern}).json()['count'], count)
        self.assertEqual(self.call('GET', '/works', params={'title': 'Dragon', 'title_language': 'es'}).json()['count'], 0)
        first = self.call('GET', '/works', params={'title': 'tied', 'order_by': 'title', 'page_size': 10}).json()
        second = self.call('GET', '/works', params={'title': 'tied', 'order_by': 'title', 'page_size': 10, 'page': 2}).json()
        ids = [row['id_works'] for row in first['items'] + second['items']]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(ids, sorted(ids))
        self.assertEqual(first['count'], 13)
        for direction in ('asc', 'desc'):
            self.call('PUT', '/works/' + rows['works']['id_works'], json={'synopsis': 'Not null'})
            page = self.call('GET', '/works', params={'order_by': 'synopsis', 'order_direction': direction}).json()['items']
            self.assertEqual(page[0]['synopsis'], 'Not null')
            self.assertIsNone(page[-1]['synopsis'])

    def test_04_roles_existing_tokens_administration_and_passwords(self):
        rows = self.graph()
        self.call('GET', '/test')
        self.call('POST', '/test', expected=201, json={'value': 'Supervisor test access'})
        for table, row in rows.items():
            path, item = '/' + table, '/' + table + '/' + row['id_' + table]
            for method, route, options in [('GET', path, {}), ('GET', item, {}), ('POST', path, {'json': {}}),
                ('PUT', item, {'json': {}}), ('DELETE', item, {}), ('DELETE', path, {'params': {'confirm': 'true'}})]:
                self.call(method, route, role='standard', expected=403, **options)
                self.assertEqual(self.client.request(method, route, **options).status_code, 401)
        for method, path, body in [('GET', '/users', None), ('POST', '/users', {}),
            ('PUT', '/users/1/role', {'role': 'standard'}), ('PUT', '/users/1/password', {'new_password': 'unit-only-new'})]:
            self.call(method, path, expected=403, **({'json': body} if body is not None else {}))
        standard = self.accounts['standard']
        self.call('PUT', '/users/' + str(standard.id) + '/role', role='administrator', json={'role': 'supervisor'})
        self.call('GET', '/works', role='standard')
        self.call('POST', '/works', role='standard', expected=201, json={'title': 'Promoted old token', 'title_language': 'en'})
        self.call('PUT', '/users/' + str(standard.id) + '/role', role='administrator', json={'role': 'standard'})
        self.call('GET', '/works', role='standard', expected=403)
        self.call('PUT', '/users/' + str(self.accounts['administrator'].id) + '/role', role='administrator', expected=409, json={'role': 'supervisor'})
        created = self.call('POST', '/users', role='administrator', expected=201,
            json={'username': 'new_supervisor', 'password': self.api_password, 'role': 'supervisor'}).json()
        self.assertEqual(created['role'], 'supervisor')
        self.call('PUT', '/users/me/password', expected=204,
            json={'current_password': self.api_password, 'new_password': self.api_password + '-updated'})
        self.call('GET', '/works', expected=401)

    def test_05_atomic_deletion_audit_secrecy_and_sequence_continuity(self):
        rows = self.graph()
        spare = self.create('works', title='Unreferenced', title_language='en')
        self.call('DELETE', '/works', role='administrator', expected=409, params={'confirm': 'true'})
        self.call('GET', '/works/' + spare['id_works'])
        self.call('GET', '/works/' + rows['works']['id_works'])
        self.call('DELETE', '/works/' + rows['works']['id_works'], expected=409)
        self.call('DELETE', '/works/' + spare['id_works'], expected=204)
        later = self.create('works', title='After deletion', title_language='en')
        self.assertGreater(later['sequence_works'], spare['sequence_works'])
        self.call('DELETE', '/works/' + later['id_works'], expected=204)
        self.create('works', title='After again', title_language='en')
        logs = self.output.getvalue()
        self.assertIn('Catalogue records deleted', logs)
        self.assertIn('Catalogue deletion rejected', logs)
        self.assertIn('"outcome": "committed"', logs)
        self.assertIn('"deleted_count": 1', logs)
        for secret in [self.api_password, self.master, self.hashed, self.auth.secret,
                       *[headers['Authorization'][7:] for headers in self.headers.values()]]:
            self.assertNotIn(secret, logs)
        for text in ('password_hash', 'psycopg', 'FOREIGN KEY', 'INSERT INTO', 'UPDATE public'):
            self.assertNotIn(text, self.call('DELETE', '/works', role='administrator', expected=409, params={'confirm': 'true'}).text)

    def test_06_concurrent_updates_and_transactional_privilege_rechecks(self):
        work = self.create('works', title='Before', title_language='en')
        barrier = threading.Barrier(2)
        def update(payload):
            barrier.wait(timeout=10)
            return self.client.put('/works/' + work['id_works'], headers=self.headers['supervisor'], json=payload)
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(update, [{'title': 'After'}, {'synopsis': 'Independent change'}]))
        self.assertEqual([r.status_code for r in results], [200, 200])
        final = self.call('GET', '/works/' + work['id_works']).json()
        self.assertEqual((final['title'], final['synopsis']), ('After', 'Independent change'))
        # Force demotion between initial request authentication and transaction lock.
        from unittest.mock import patch
        from app.catalogue_repository import CatalogueRepository
        original = CatalogueRepository.delete
        def demote_then_delete(repository, actor, record_id=None):
            self.users.change_role(self.accounts['administrator'].id, self.accounts['supervisor'].id, 'standard')
            return original(repository, actor, record_id)
        with patch.object(CatalogueRepository, 'delete', demote_then_delete):
            self.call('DELETE', '/works/' + work['id_works'], expected=403)
        self.call('GET', '/works/' + work['id_works'], role='administrator')
        # A second administrator allows the first to be demoted safely mid-request.
        peer = self.users.create('peer_admin', self.hashed, role='administrator')
        original_bulk = CatalogueRepository.bulk
        def demote_admin(repository, actor, selection, payload=None):
            self.users.change_role(peer.id, self.accounts['administrator'].id, 'supervisor')
            return original_bulk(repository, actor, selection, payload)
        with patch.object(CatalogueRepository, 'bulk', demote_admin):
            self.call('DELETE', '/works', role='administrator', expected=403, params={'confirm': 'true'})
        self.call('GET', '/works/' + work['id_works'], role='administrator')
        actor = self.accounts['administrator']
        with self.assertRaises(UserManagementError):
            self.users.create_managed(actor.id, 'denied_after_demotion', self.hashed, 'standard', credential_version=actor.credential_version)
        # Check credential-version revocation after initial authentication too.
        original_create = CatalogueRepository.create
        def revoke_then_create(repository, payload, claims):
            with self.provider.connection() as connection, connection.cursor() as cursor:
                cursor.execute('UPDATE public.api_users SET credential_version=credential_version+1 WHERE id=%s', (actor.id,))
            return original_create(repository, payload, claims)
        with patch.object(CatalogueRepository, 'create', revoke_then_create):
            self.call('POST', '/works', role='administrator', expected=401, json={'title': 'Must not persist', 'title_language': 'en'})

    def test_07_inherited_ordering_and_openapi_response_equivalence(self):
        schema = self.client.get('/openapi.json').json()
        for table, resource in RESOURCES.items():
            routes = schema['paths']
            refs = [routes['/' + table]['post']['responses']['201']['content']['application/json']['schema'],
                    routes['/' + table + '/{id}']['get']['responses']['200']['content']['application/json']['schema'],
                    routes['/' + table + '/{id}']['put']['responses']['200']['content']['application/json']['schema']]
            self.assertIn(refs[1], refs[0]['anyOf'])
            refs[0] = refs[1]
            self.assertEqual(refs[1], refs[2])
            page_ref = routes['/' + table]['get']['responses']['200']['content']['application/json']['schema']['$ref'].split('/')[-1]
            item_schema = schema['components']['schemas'][page_ref]['properties']['items']['items']
            self.assertEqual(item_schema['$ref'].split('/')[-1], resource.list_record.__name__)
            if resource.list_record is resource.record:
                self.assertEqual(item_schema, refs[0])
        for path, fields in [('/test', ['id', 'value','created_at','created_at_timezone']), ('/users', ['id', 'username', 'role', 'is_active', 'created_at'])]:
            parameters = {p['name']: p for p in schema['paths'][path]['get']['parameters']}
            self.assertEqual(parameters['order_by']['schema']['enum'], fields)
            self.assertEqual(parameters['order_direction']['schema']['enum'], ['asc', 'desc'])
            for field in fields:
                for direction in ('asc', 'desc'):
                    self.call('GET', path, role='administrator', params={'order_by': field, 'order_direction': direction})
            for params in ({'order_by': 'password_hash'}, {'order_direction': 'invalid'}):
                self.call('GET', path, role='administrator', expected=422, params=params)
        self.assertIn('supervisor', schema['components']['schemas']['RoleUpdate']['properties']['role']['enum'])
        collection = json.loads((PROJECT_ROOT / 'postman/Ouroboros.postman_collection.json').read_text(encoding='utf-8'))
        def visit(items):
            for item in items:
                if 'item' in item:
                    yield from visit(item['item'])
                else:
                    yield item
        for item in visit(collection['item']):
            spec = item['request']
            raw = spec['url']['raw'] if isinstance(spec['url'], dict) else spec['url']
            table = raw.split('{{base_url}}', 1)[-1].split('?', 1)[0].strip('/')
            if spec['method'] == 'GET' and table in RESOURCES:
                params = {p['key']: p for p in spec['url']['query']}
                if item['name'].startswith('REVIEW '):
                    # Focused enabled-filter examples intentionally select a
                    # subset; the general collection requests below retain all controls.
                    self.assertLessEqual(set(params), set(RESOURCES[table].query.model_fields))
                    enabled = {key: value['value'] for key, value in params.items() if not value.get('disabled', False)}
                    RESOURCES[table].query.model_validate(enabled)
                    self.assertEqual(enabled['platform_access_types'], 'website')
                    self.assertEqual(enabled['platform_url'], '%example.org%')
                    continue
                self.assertEqual(set(params), set(RESOURCES[table].query.model_fields))
                for field in RESOURCES[table].columns:
                    self.assertTrue(params[field]['disabled'])
                self.assertEqual(params['order_by']['value'], RESOURCES[table].query.model_fields['order_by'].default)
            if 'ADMIN DELETE ALL' in item['name']:
                self.assertEqual(spec['auth']['bearer'][0]['value'], '{{admin_token}}')
            if spec['method'] == 'DELETE' and table in RESOURCES and ('ADMIN DELETE ALL' in item['name'] or 'filtered actual' in item['name']):
                self.assertEqual(next(p['value'] for p in spec['url']['query'] if p['key']=='confirm'), 'false')
                guard = next(event for event in item['event'] if event['listen'] == 'prerequest')
                self.assertIn('pm.execution.skipRequest()', '\n'.join(guard['script']['exec']))
