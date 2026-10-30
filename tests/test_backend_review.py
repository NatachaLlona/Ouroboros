"""Backend review regressions; real mutations use UUID-owned disposable storage."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import os
import unittest
from unittest.mock import MagicMock, patch

from pydantic import ValidationError
from app.login_throttle import LoginThrottle
from app.schemas.users import UserCreate, PasswordChange, PasswordReset, UserQuery
from app.schemas.catalogue import RESOURCES
from app.datetimes import date_predicates
import test_api as api
import test_catalogue_api as legacy


class BackendReviewUnitTests(unittest.TestCase):
    def test_password_boundaries_and_unicode_without_normalization(self):
        for value in ('a' * 15, ' 🐍 ' * 30, 'a' * 1024):
            for model, field in ((UserCreate, 'password'), (PasswordChange, 'new_password'), (PasswordReset, 'new_password')):
                body = {'username': 'qa', 'current_password': 'x'}
                body = {key: item for key, item in body.items() if key in model.model_fields}
                result = model.model_validate({**body, field: value})
                self.assertEqual(getattr(result, field).get_secret_value(), value)
        for value in ('x', 'a' * 14, 'a' * 1025, 123, None):
            for model, field in ((UserCreate, 'password'), (PasswordChange, 'new_password'), (PasswordReset, 'new_password')):
                body = {'username': 'qa'} if model is UserCreate else {'current_password': 'old'} if model is PasswordChange else {}
                with self.assertRaises(ValidationError):
                    model.model_validate({**body, field: value})
        from app.api_credentials import configure_api_credentials
        from app.database import DatabaseError
        users = MagicMock()
        users.has_administrator.return_value = False
        users.count.return_value = 0
        users.get_by_username.return_value = None
        with patch('builtins.input', return_value='new-admin'), patch('app.api_credentials.read_password', return_value='short'), \
                patch('app.api_credentials.PASSWORD_HASHER') as hashing:
            with self.assertRaises(DatabaseError):
                configure_api_credentials({'auth': {}}, users)
            hashing.hash.assert_not_called()
            users.bootstrap_administrator.assert_not_called()

    def test_throttle_account_client_expiry_capacity_and_concurrency(self):
        now = [0]
        throttle = LoginThrottle(clock=lambda: now[0])
        with ThreadPoolExecutor(max_workers=20) as pool:
            results = list(pool.map(lambda index: throttle.admit('same', str(index)), range(20)))
        self.assertEqual(results.count(None), 10)
        self.assertEqual(throttle.admit('same', 'new'), 300)
        now[0] = 301
        self.assertIsNone(throttle.admit('same', 'new'))
        throttle = LoginThrottle(clock=lambda: now[0])
        for index in range(50):
            self.assertIsNone(throttle.admit(str(index), 'same-client'))
        self.assertEqual(throttle.admit('another', 'same-client'), 300)
        bounded = LoginThrottle(clock=lambda: now[0], capacity=2)
        self.assertIsNone(bounded.admit('a', 'b'))
        self.assertEqual(bounded.admit('c', 'd'), 300)
        self.assertEqual(len(bounded.entries), 2)
        now[0] += 301
        self.assertIsNone(bounded.admit('c', 'd'))

    def test_platform_validation_and_shared_predicates(self):
        from app.catalogue_repository import CatalogueRepository
        resource = RESOURCES['platforms']
        base = dict(platform_name='QA', platform_is_paid=False, platform_is_episodes=False, platform_is_duration_time=False)
        for values in ([], ['application', 'website', 'link']):
            self.assertEqual(resource.create.model_validate({**base, 'platform_access_types': values}).platform_access_types, values)
        for values in (None, ['website', 'website'], ['unknown'], 'website'):
            with self.assertRaises(ValidationError):
                resource.create.model_validate({**base, 'platform_access_types': values})
        for url in ('ftp://example.org', 'javascript:alert(1)', 'https://', ''):
            with self.assertRaises(ValidationError):
                resource.create.model_validate({**base, 'platform_url': url})
        repo = CatalogueRepository(None, resource)
        self.assertIn(('platform_access_types', '@>', ['website']), repo.filters({'platform_access_types': 'website'}))
        self.assertIn(('platform_url', 'ILIKE', '%example%'), repo.filters({'platform_url': '%example%'}))
        for mode in ('validation', 'serialization'):
            schema = resource.create.model_json_schema(mode=mode)['properties']['platform_access_types']
            self.assertTrue(schema['uniqueItems'])
            self.assertEqual(schema['items']['enum'], ['application', 'website', 'link'])


class BackendReviewHTTPTests(unittest.TestCase):
    setUpClass = classmethod(api.APITests.setUpClass.__func__)
    setUp = api.APITests.setUp
    bearer = api.APITests.bearer

    def test_token_throttle_safe_429_and_untrusted_proxy_headers(self):
        self.app.state.login_throttle = LoginThrottle()
        with patch.object(self.auth, 'verify_password', return_value=None) as verify:
            for index in range(10):
                response = self.client.post('/token', data={'username': 'same', 'password': 'private-value'},
                    headers={'X-Forwarded-For': str(index)})
                self.assertEqual(response.status_code, 401)
            response = self.client.post('/token', data={'username': 'same', 'password': 'private-value'})
            self.assertEqual(response.status_code, 429)
            self.assertEqual(response.json()['error']['code'], 'LOGIN_THROTTLED')
            self.assertGreater(int(response.headers['Retry-After']), 0)
            self.assertEqual(verify.call_count, 10)
        self.assertNotIn('private-value', self.output.getvalue())

    def test_user_filters_strict_public_schema_and_configured_day(self):
        self.users.users[self.user.id] = replace(self.user, role='administrator')
        headers = self.bearer()
        self.users.page = MagicMock(return_value={'count': 0, 'page': 1, 'page_size': 50, 'items': []})
        response = self.client.get('/users', headers=headers, params={'id': 1, 'username': 'Exact',
            'username_pattern': '%act', 'role': 'standard', 'is_active': 'false',
            'created_at_date': '2026-10-25', 'filter_timezone': 'Europe/Lisbon'})
        self.assertEqual(response.status_code, 200)
        values = self.users.page.call_args.kwargs
        self.assertIs(values['is_active'], False)
        self.assertEqual(values['username_pattern'], '%act')
        bounds = date_predicates(values, ['created_at'])
        self.assertEqual((bounds[1][2] - bounds[0][2]).total_seconds(), 25 * 3600)
        for params in ({'password_hash': 'x'}, {'order_by': 'password_hash'}, {'role': 'owner'},
                       {'page_size': 9}, {'created_at_date': '2026-10-25', 'created_at_to': '2026-10-25'},
                       {'created_at_from': '2026-10-25T00:00:00'}, {'filter_timezone': 'bad'}):
            self.assertEqual(self.client.get('/users', headers=headers, params=params).status_code, 422)
        self.assertEqual(self.client.get('/users', headers=headers, params={
            'created_at_from': '2026-10-25', 'created_at_to': '2026-10-25'}).status_code, 200)


@unittest.skipUnless(os.environ.get('FOUNDATION_RUN_INTEGRATION') == '1', 'Requires owned disposable Docker integration')
class BackendReviewIntegrationTests(unittest.TestCase):
    setUpClass = classmethod(legacy.CatalogueAPITests.setUpClass.__func__)
    cleanup = classmethod(legacy.CatalogueAPITests.cleanup.__func__)
    setUp = legacy.CatalogueAPITests.setUp
    call = legacy.CatalogueAPITests.call
    create = legacy.CatalogueAPITests.create

    def test_migration_preserves_historical_records_and_replay(self):
        import shutil
        import tempfile
        import uuid
        from pathlib import Path
        from app.database import connect, ensure_database
        from app.migrate import migrate
        database = {**self.db, 'name': 'upgrade_' + uuid.uuid4().hex}
        ensure_database(database, self.master)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'sql/migrations').mkdir(parents=True)
            for path in (self.root / 'sql/migrations').glob('*.sql'):
                if path.name < '011':
                    shutil.copy(path, root / 'sql/migrations' / path.name)
            with connect(database, self.master) as connection:
                migrate(connection, root)
                connection.execute("INSERT INTO public.platforms(platform_name,platform_is_paid,platform_is_episodes,platform_is_duration_time) VALUES ('Keep history',false,true,false)")
                connection.execute("INSERT INTO public.api_users(username,password_hash,scopes) VALUES (%s,%s,%s)",
                                   ('keep-credentials', self.hashed, ['test:read']))
                before = connection.execute('SELECT * FROM public.platforms').fetchone()
                credentials = connection.execute('SELECT * FROM public.api_users').fetchall()
                migrate(connection, self.root)
                after = connection.execute('SELECT * FROM public.platforms').fetchone()
                self.assertEqual(after[:-2], before)
                self.assertEqual(after[-2:], ([], None))
                self.assertEqual(connection.execute('SELECT * FROM public.api_users').fetchall(), credentials)
                versions = connection.execute('SELECT * FROM public.foundation_migrations ORDER BY version').fetchall()
                migrate(connection, self.root)
                self.assertEqual(connection.execute('SELECT * FROM public.foundation_migrations ORDER BY version').fetchall(), versions)

    def test_platform_roundtrips_batch_bulk_audits_and_constraints(self):
        base = dict(platform_name='Historical unknown', platform_is_paid=False, platform_is_episodes=False, platform_is_duration_time=False)
        first = self.create('platforms', **base)
        self.assertEqual(first['platform_access_types'], [])
        self.assertIsNone(first['platform_url'])
        second = self.call('POST', '/platforms', expected=201, json=[{**base, 'platform_access_types': ['website', 'application'],
            'platform_url': 'https://example.org/path'}, {**base, 'platform_access_types': ['link']}]).json()['items']
        path = '/platforms/' + second[0]['id_platforms']
        self.assertEqual(self.call('PUT', path, json=second[0]).json(), second[0])
        filtered = self.call('GET', '/platforms', params={'platform_access_types': 'website', 'platform_url': '%example.org%',
            'order_by': 'platform_access_types', 'order_direction': 'desc'}).json()
        self.assertEqual(filtered['items'], [second[0]])
        params = {'platform_access_types': 'website', 'dry_run': True}
        self.assertEqual(self.call('PUT', '/platforms', role='administrator', params=params,
            json={'platform_access_types': ['link'], 'platform_url': None}).json()['matched_count'], 1)
        self.assertEqual(self.call('GET', path).json(), second[0])
        updated = self.call('PUT', '/platforms', role='administrator', params={**params, 'dry_run': False, 'confirm': True},
            json={'platform_access_types': ['link'], 'platform_url': None})
        self.assertEqual(updated.json()['updated_count'], 1)
        self.assertEqual(self.call('GET', path).json()['platform_access_types'], ['link'])
        audit = self.call('GET', '/api_audit_logs', params={'interaction_id': updated.headers['X-Interaction-ID']}).json()['items'][0]
        self.assertEqual(audit['mutation_count'], 1)
        self.assertEqual(self.call('DELETE', '/platforms', role='administrator', params={
            'platform_access_types': 'link', 'dry_run': True}).json()['matched_count'], 2)
        for body in ({'platform_access_types': ['website', 'website']}, {'platform_access_types': ['bad']}, {'platform_url': 'ftp://example.org'}):
            self.call('PUT', path, json=body, expected=422)

    def test_users_combined_filters_calendar_days_and_secret_rejection(self):
        with self.provider.connection() as connection:
            connection.execute("UPDATE public.api_users SET created_at=%s WHERE role='standard'", ('2026-10-25T23:30:00Z',))
            connection.execute("UPDATE public.api_users SET is_active=false WHERE role='standard'")
        params = {'id': self.accounts['standard'].id, 'username': 'standard', 'username_pattern': '%AND%',
                  'role': 'standard', 'is_active': False, 'created_at_date': '2026-10-25', 'filter_timezone': 'Europe/Lisbon'}
        result = self.call('GET', '/users', role='administrator', params=params).json()
        self.assertEqual(result['count'], 1)
        self.assertEqual(set(result['items'][0]), {'id', 'username', 'role', 'is_active', 'created_at'})
        self.assertEqual(self.call('GET', '/users', role='administrator', params={**params, 'username_pattern': 'no%'}).json()['count'], 0)
        ranged = {key: value for key, value in params.items() if key != 'created_at_date'}
        ranged.update(created_at_from='2026-10-25', created_at_to='2026-10-25')
        self.assertEqual(self.call('GET', '/users', role='administrator', params=ranged).json()['count'], 1)
        self.call('GET', '/users', expected=403)
        self.call('GET', '/users', role='administrator', params={'password_hash': 'x'}, expected=422)
        from app.api_credentials import PASSWORD_HASHER
        legacy_user = self.users.create('legacy-short', PASSWORD_HASHER.hash('x'))
        original = self.users.get_by_id(legacy_user.id)
        token = self.client.post('/token', data={'username': 'legacy-short', 'password': 'x'})
        self.assertEqual(token.status_code, 200)
        headers = {'Authorization': 'Bearer ' + token.json()['access_token']}
        for path, body in (('/users', {'username': 'too-short', 'password': 'x'}),
                           ('/users/' + str(legacy_user.id) + '/password', {'new_password': 'x'})):
            self.call('POST' if path == '/users' else 'PUT', path, role='administrator', json=body, expected=422)
        self.assertEqual(self.client.put('/users/me/password', headers=headers,
            json={'current_password': 'x', 'new_password': 'short'}).status_code, 422)
        self.assertEqual(self.users.get_by_id(legacy_user.id).password_hash, original.password_hash)
        response = self.client.put('/users/me/password', headers=headers,
            json={'current_password': 'x', 'new_password': 'a Unicode passphrase 🐍 ' * 4})
        self.assertEqual(response.status_code, 204)
        self.assertEqual(self.client.get('/test', headers=headers).status_code, 401)
        self.assertEqual(self.users.get_by_id(legacy_user.id).credential_version, original.credential_version + 1)
