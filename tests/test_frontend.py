"""Browser session security and shared API writes in owned disposable resources."""
from dataclasses import replace
import json
import os
import unittest
import re
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.browser_sessions import BrowserSessions, browser_settings
from app.config import ConfigurationError, PROJECT_ROOT
from app.audit_privacy import sensitive_operation
import test_api as api
import test_catalogue_api as legacy

ORIGIN = 'http://localhost:6969'
HEADERS = {'Origin': ORIGIN}


class FrontendAssetTests(unittest.TestCase):
    def test_palette_contrast_and_no_persistent_browser_secrets(self):
        css = (PROJECT_ROOT / 'frontend/styles/main.css').read_text(encoding='utf-8')
        colors = dict(re.findall(r'--([\w-]+):\s*(#[A-Fa-f0-9]{6})', css))
        self.assertEqual({name: colors[name] for name in ('dark-grayish-green', 'grayish-yellow', 'brown', 'orange-sand', 'mauve', 'dark-mauve', 'dark-magenta-pink')},
            dict(zip(('dark-grayish-green', 'grayish-yellow', 'brown', 'orange-sand', 'mauve', 'dark-mauve', 'dark-magenta-pink'),
                ('#424A40', '#6C6B5B', '#99886E', '#CAB089', '#976571', '#4E3944', '#3A2833'))))
        def luminance(value):
            components = [int(value[index:index + 2], 16) / 255 for index in (1, 3, 5)]
            linear = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in components]
            return sum(v * weight for v, weight in zip(linear, (.2126, .7152, .0722)))
        def ratio(first, second):
            low, high = sorted((luminance(colors[first]), luminance(colors[second])))
            return (high + .05) / (low + .05)
        for name in ('dark-grayish-green', 'grayish-yellow', 'dark-mauve', 'muted'):
            self.assertGreaterEqual(ratio(name, 'cream'), 4.5)
        self.assertGreaterEqual(ratio('dark-mauve', 'paper'), 4.5)
        self.assertGreaterEqual(ratio('brown', 'paper'), 3)
        self.assertGreaterEqual(ratio('mauve', 'cream'), 3)  # Large display headings only.
        self.assertEqual(colors['accent'], '#E6BD68')
        self.assertEqual(colors['soft-amber'], '#D99A45')
        self.assertRegex(css, r'\.platform-registration \.required-star\{color:#DC3545;font-weight:800\}')
        # Gold is decorative; readable labels/legend and required semantics
        # must carry meaning because this exact accent is not text contrast.
        self.assertLess(ratio('accent', 'paper'), 3)
        # The only navigation enlargement is explicitly scoped to the home link.
        home_rules = re.findall(r'([^{}]+)\{([^{}]*min-height:52px[^{}]*)\}', css)
        self.assertEqual(len(home_rules), 1)
        self.assertEqual(home_rules[0][0].strip(), '.home-return')
        self.assertIn('font-size:16px', home_rules[0][1])
        source = '\n'.join(path.read_text(encoding='utf-8') for path in (PROJECT_ROOT / 'frontend/src').rglob('*.ts') if not path.name.endswith('.spec.ts'))
        for forbidden in ('localStorage', 'sessionStorage', 'document.cookie', 'console.log', 'console.error'):
            self.assertNotIn(forbidden, source)


class BrowserSessionTests(unittest.TestCase):
    setUpClass = classmethod(api.APITests.setUpClass.__func__)
    setUp = api.APITests.setUp

    def browser(self):
        self.client = TestClient(self.app, base_url=ORIGIN, client=('127.0.0.1', 43210))
        self.addCleanup(self.client.close)

    def login(self, role='supervisor'):
        self.users.users[self.user.id] = replace(self.user, role=role)
        self.browser()
        response = self.client.post('/browser/login', headers=HEADERS,
            json={'username': self.user.username, 'password': self.password})
        self.assertEqual(response.status_code, 200)
        return response

    def test_public_home_assets_and_protected_form(self):
        self.browser()
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('<app-root>', response.text)
        self.assertIn('main-', response.text)
        home_source = (PROJECT_ROOT / 'frontend/src/app/home/home.ts').read_text(encoding='utf-8')
        self.assertIn('routerLink="/cadastrar"', home_source)
        self.assertIn('routerLink="/consultar"', home_source)
        cards = (PROJECT_ROOT / 'frontend/src/app/shared/selection-cards.ts').read_text(encoding='utf-8')
        self.assertIn("name:'Watched'", cards)
        self.assertIn("name:'Watchlist'", cards)
        self.assertIn(' disabled ', cards)
        for path in ('/cadastrar', '/consultar'):
            self.assertEqual(self.client.get(path).status_code, 200)
        self.assertEqual(self.client.get('/consultas', follow_redirects=False).headers['location'], '/?entrar=1&destino=consultas')
        self.assertIn("frame-ancestors 'none'", response.headers['Content-Security-Policy'])
        self.assertEqual(self.client.get('/frontend/assets/snake.svg').status_code, 200)
        self.assertEqual(self.client.get('/frontend/entries.html').status_code, 404)
        self.assertEqual(self.client.get('/frontend/index.html').status_code, 404)
        self.assertEqual(self.client.get('/frontend/missing.js').status_code, 404)
        self.assertEqual(self.client.get('/not-a-client-route').status_code, 404)
        self.assertEqual(self.client.get('/openapi.json').status_code, 200)
        self.assertEqual(self.client.get('/docs').status_code, 200)
        self.assertEqual(response.headers['cache-control'], 'no-store')
        import re
        bundle = re.search(r'src="(/frontend/main-[^"]+\.js)"', response.text).group(1)
        self.assertIn('immutable', self.client.get(bundle).headers['cache-control'])
        # Prove that the loaded shell and its complete graph belong to the stamp.
        import hashlib
        manifest_response = self.client.get('/frontend/build-info.json')
        self.assertEqual(manifest_response.headers['cache-control'], 'no-cache')
        manifest = manifest_response.json()
        self.assertIn(f'content="{manifest["build_id"]}"', response.text)
        self.assertEqual(manifest['index_sha256'], hashlib.sha256(response.content).hexdigest())
        # The production policy rejects Angular-injected component <style> tags.
        # These controls must obtain their scoped appearance from the served CSS.
        self.assertIn("style-src 'self';", response.headers['Content-Security-Policy'])
        self.assertNotIn("'unsafe-inline'", response.headers['Content-Security-Policy'])
        self.assertNotIn('<style', response.text)
        css_assets = [asset for asset in manifest['assets'] if asset['url'].endswith('.css')]
        self.assertTrue(css_assets)
        css_text = '\n'.join(self.client.get(asset['url']).text for asset in css_assets)
        for selector in ('app-field-label .help-button', 'app-field-label .field-tooltip',
                         '.searchable-dropdown .currency-trigger', '.searchable-dropdown li'):
            self.assertIn(selector, css_text)
        self.assertIn('list-style-type:none', css_text)
        for component in ('field-label', 'currency-select'):
            source = (PROJECT_ROOT / f'frontend/src/app/shared/{component}.ts').read_text(encoding='utf-8')
            self.assertNotIn('styles:', source)
        for asset in manifest['assets']:
            delivered = self.client.get(asset['url'])
            self.assertEqual(delivered.status_code, 200)
            self.assertEqual(asset['sha256'], hashlib.sha256(delivered.content).hexdigest())
        direct = self.client.get('/cadastros', follow_redirects=False)
        self.assertEqual(direct.status_code, 303)
        self.assertEqual(direct.headers['location'], '/?entrar=1&destino=cadastros')
        self.database.connection.side_effect = RuntimeError('Private database failure')
        self.assertEqual(self.client.get('/').status_code, 200)

    def test_missing_browser_configuration_is_not_an_account_permission_error(self):
        self.browser()
        self.app.state.browser_sessions = BrowserSessions({'port': 6969})
        with patch.object(self.auth, 'verify_password') as verifier:
            for method, path, options in (
                ('GET', '/browser/session', {}),
                ('POST', '/browser/login', {'json': {'username': 'ouro', 'password': 'private-test-value'}})):
                response = self.client.request(method, path, headers=HEADERS, **options)
                self.assertEqual(response.status_code, 403)
                self.assertEqual(response.json()['error']['code'], 'BROWSER_ORIGIN_REJECTED')
            verifier.assert_not_called()
        self.assertNotIn('private-test-value', self.output.getvalue())

    def test_cookie_and_bearer_catalogue_permission_parity(self):
        from app.catalogue_repository import CatalogueRepository
        self.browser()
        with patch.object(CatalogueRepository, 'page', return_value={'count': 0, 'page': 1, 'page_size': 50, 'items': []}):
            for role in ('administrator', 'supervisor', 'standard'):
                self.users.users[self.user.id] = replace(self.user, role=role)
                signed_in = self.client.post('/browser/login', headers=HEADERS,
                    json={'username': self.user.username, 'password': self.password})
                self.assertEqual(signed_in.status_code, 200)
                self.assertEqual(signed_in.json()['role'], role)
                self.assertIs(signed_in.json()['is_active'], True)
                self.assertEqual(signed_in.json()['can_create'], role != 'standard')
                token = self.client.post('/token', data={'username': self.user.username, 'password': self.password})
                expected = 403 if role == 'standard' else 200
                self.assertEqual(self.client.get('/platforms').status_code, expected)
                self.assertEqual(self.client.get('/platforms', headers={'Authorization': 'Bearer ' + token.json()['access_token']}).status_code, expected)

    def test_cookie_reload_rotation_expiry_logout_and_revocation(self):
        response = self.login()
        cookie = response.headers['set-cookie']
        self.assertIn('HttpOnly', cookie)
        self.assertIn('SameSite=strict', cookie)
        self.assertNotIn('Secure;', cookie)
        self.assertNotIn('access_token', response.json())
        self.assertTrue(self.client.get('/browser/session').json()['authenticated'])
        self.assertEqual(self.client.get('/cadastros').status_code, 200)
        old = self.client.cookies.get('ouroboros_dev_session')
        csrf = response.json()['csrf_token']
        self.assertEqual(self.client.post('/browser/logout', headers=HEADERS).status_code, 403)
        self.assertEqual(self.client.post('/browser/logout', headers={**HEADERS, 'X-CSRF-Token': csrf}).status_code, 204)
        self.assertFalse(self.client.get('/browser/session').json()['authenticated'])
        self.client.cookies.set('ouroboros_dev_session', old)
        self.assertFalse(self.client.get('/browser/session').json()['authenticated'])
        self.client.cookies.clear()
        self.client.post('/browser/login', headers=HEADERS, json={'username': self.user.username, 'password': self.password})
        self.users.users[self.user.id] = replace(self.users.users[self.user.id], credential_version=2)
        self.assertFalse(self.client.get('/browser/session').json()['authenticated'])
        self.users.users[self.user.id] = replace(self.user, role='supervisor')
        self.client.post('/browser/login', headers=HEADERS, json={'username': self.user.username, 'password': self.password})
        self.app.state.browser_sessions.clock = lambda: 10**12
        self.assertFalse(self.client.get('/browser/session').json()['authenticated'])
        for value in (self.password, old, csrf):
            self.assertNotIn(value, self.output.getvalue())

    def test_current_roles_inactivity_csrf_and_bearer_precedence(self):
        response = self.login()
        csrf = response.json()['csrf_token']
        self.assertEqual(self.client.post('/platforms', headers=HEADERS, json={}).json()['error']['code'], 'CSRF_REJECTED')
        self.assertEqual(self.client.post('/platforms', headers={'Origin': 'https://foreign.example', 'X-CSRF-Token': csrf}, json={}).status_code, 403)
        self.users.users[self.user.id] = replace(self.user, role='standard')
        self.assertFalse(self.client.get('/browser/session').json()['can_create'])
        self.assertEqual(self.client.get('/cadastros').status_code, 403)
        self.assertEqual(self.client.post('/platforms', headers={**HEADERS, 'X-CSRF-Token': csrf}, json={}).status_code, 403)
        self.users.users[self.user.id] = replace(self.user, role='supervisor', is_active=False)
        self.assertFalse(self.client.get('/browser/session').json()['authenticated'])
        self.users.users[self.user.id] = replace(self.user, role='supervisor')
        token = self.client.post('/token', data={'username': self.user.username, 'password': self.password})
        self.assertEqual(token.status_code, 200)
        # Bearer clients retain their existing schema validation and need no cookie CSRF token.
        self.assertEqual(self.client.post('/platforms', headers={'Authorization': 'Bearer ' + token.json()['access_token']}, json={}).status_code, 422)
        self.assertEqual(self.client.post('/platforms', headers={'Authorization': 'Bearer invalid'}, json={}).status_code, 401)

    def test_login_generic_errors_origin_checks_shared_throttle_and_body_omission(self):
        self.browser()
        for path in ('/browser/login', '/browser/session', '/browser/logout'):
            self.assertTrue(sensitive_operation(path))
        self.assertEqual(self.client.post('/browser/login', json={'username': self.user.username, 'password': self.password}).status_code, 403)
        with patch.object(self.auth, 'verify_password', return_value=None):
            first = self.client.post('/browser/login', headers=HEADERS, json={'username': 'missing', 'password': 'private-browser-password'})
            self.assertEqual(first.status_code, 401)
            self.assertEqual(first.json()['error']['code'], 'INVALID_CREDENTIALS')
            for _ in range(9):
                self.client.post('/token', data={'username': 'missing', 'password': 'private-browser-password'})
            limited = self.client.post('/browser/login', headers=HEADERS, json={'username': 'missing', 'password': 'private-browser-password'})
            self.assertEqual(limited.status_code, 429)
            self.assertGreater(int(limited.headers['Retry-After']), 0)
        self.assertNotIn('private-browser-password', self.output.getvalue())
        self.assertFalse(any('Request JSON body received' in line and '/browser/' in line for line in self.output.getvalue().splitlines()))

    def test_secure_defaults_capacity_and_settings_validation(self):
        self.assertEqual(browser_settings({'port': 6969}), ('https://localhost:6969', True))
        for settings in ({'origin': 'http://example.org', 'allow_loopback_http': True}, {'origin': 'https://example.org/path'},
                         {'origin': 'https://user:private@example.org'}, {'origin': 'http://localhost:6969'}, {'allow_loopback_http': 'true'}):
            with self.assertRaises(ConfigurationError):
                browser_settings({'browser': settings})
        self.users.users[self.user.id] = replace(self.user, role='supervisor')
        self.app.state.browser_sessions = BrowserSessions({'browser': {'origin': 'https://catalogue.example'}})
        with TestClient(self.app, base_url='https://catalogue.example') as client:
            response = client.post('/browser/login', headers={'Origin': 'https://catalogue.example'}, json={'username': self.user.username, 'password': self.password})
            self.assertEqual(response.status_code, 200)
            self.assertIn('__Host-ouroboros_session=', response.headers['set-cookie'])
            self.assertIn('Secure', response.headers['set-cookie'])
            self.app.state.browser_sessions.capacity = 1
            with TestClient(self.app, base_url='https://catalogue.example') as other:
                self.assertEqual(other.post('/browser/login', headers={'Origin': 'https://catalogue.example'}, json={'username': self.user.username, 'password': self.password}).status_code, 503)

    def test_idle_renewal_absolute_expiry_and_passive_reads(self):
        self.login()
        sessions = self.app.state.browser_sessions
        self.assertEqual((sessions.idle_timeout, sessions.ttl), (7200, 43200))
        now = [0.0]
        sessions.clock = lambda: now[0]
        # Rotate into the controlled clock without retaining a real-time deadline.
        self.client.post('/browser/login', headers=HEADERS, json={'username': self.user.username, 'password': self.password})
        key = sessions.digest(self.client.cookies.get(sessions.cookie_name))
        absolute = sessions.entries[key].absolute_expires
        now[0] = 7100
        self.assertEqual(self.client.get('/browser/session').json()['expires_in'], 100)
        self.assertEqual(sessions.entries[key].expires, 7200)
        self.assertEqual(self.client.get('/consultas').status_code, 200)
        self.assertEqual(sessions.entries[key].expires, 14300)
        self.assertEqual(sessions.entries[key].absolute_expires, absolute)
        from app.catalogue_repository import CatalogueRepository
        with patch.object(CatalogueRepository, 'page', return_value={'count': 0, 'page': 1, 'page_size': 10, 'items': []}):
            now[0] = 7200
            self.assertEqual(self.client.get('/platforms').status_code, 200)
            self.assertEqual(sessions.entries[key].expires, 14300)
            self.assertEqual(self.client.get('/platforms', headers={'X-Ouroboros-Activity': 'user'}).status_code, 200)
            self.assertEqual(sessions.entries[key].expires, 14400)
        for instant in (14000, 21000, 28000, 35000, 42000):
            now[0] = instant
            self.assertEqual(self.client.get('/cadastros').status_code, 200)
        self.assertEqual(sessions.entries[key].expires, 43200)
        now[0] = 43200
        self.assertFalse(self.client.get('/browser/session').json()['authenticated'])
        for settings in ({'idle_timeout_seconds': True}, {'idle_timeout_seconds': 59},
                         {'absolute_lifetime_seconds': 86401}, {'idle_timeout_seconds': 800, 'absolute_lifetime_seconds': 700}):
            with self.assertRaises(ConfigurationError):
                browser_settings({'browser': settings})


@unittest.skipUnless(os.environ.get('FOUNDATION_RUN_INTEGRATION') == '1', 'Requires owned disposable Docker integration')
class BrowserCreationIntegrationTests(unittest.TestCase):
    setUpClass = classmethod(legacy.CatalogueAPITests.setUpClass.__func__)
    cleanup = classmethod(legacy.CatalogueAPITests.cleanup.__func__)
    setUp = legacy.CatalogueAPITests.setUp

    def test_cookie_platform_tag_creation_audit_and_transaction_authority(self):
        from app.catalogue_repository import CatalogueRepository
        # The provider and accounts are allocated by the UUID-owned legacy harness.
        with TestClient(self.client.app, base_url=ORIGIN, client=('127.0.0.1', 43211)) as browser:
            for role in ('administrator', 'supervisor', 'standard'):
                login = browser.post('/browser/login', headers=HEADERS, json={'username': role, 'password': self.api_password})
                self.assertEqual(login.status_code, 200)
                headers = {**HEADERS, 'X-CSRF-Token': login.json()['csrf_token']}
                platform = {'platform_name': 'Biblioteca 🐍', 'platform_is_paid': False, 'platform_is_episodes': True,
                    'platform_is_duration_time': False, 'platform_access_types': ['application', 'website', 'link'],
                    'platform_url': 'https://example.org/catalogue', 'price_amount': None, 'price_currency': None}
                response = browser.post('/platforms', headers=headers, json=platform)
                self.assertEqual(response.status_code, 403 if role == 'standard' else 201)
                if role == 'standard':
                    continue
                self.assertEqual(response.json()['platform_access_types'], platform['platform_access_types'])
                self.assertIsNone(response.json()['price_amount'])
                interaction = response.headers['X-Interaction-ID']
                evidence = self.client.get('/api_audit_logs', headers=self.headers['administrator'], params={'interaction_id': interaction}).json()['items'][0]
                self.assertEqual(evidence['mutation_count'], 1)
                self.assertEqual(evidence['business_outcome'], 'committed')
                # Exact focused registration payload: untouched booleans and blank price.
                focused = browser.post('/platforms', headers=headers, json={
                    'platform_name': 'Disposable focused registration',
                    'platform_is_paid': False, 'platform_is_episodes': False,
                    'platform_is_duration_time': False,
                    'platform_access_types': ['application'], 'price_currency': None})
                self.assertEqual(focused.status_code, 201)
                for key in ('platform_is_paid', 'platform_is_episodes', 'platform_is_duration_time'):
                    self.assertIs(focused.json()[key], False)
                self.assertIsNone(focused.json()['price_amount'])
                self.assertIsNone(focused.json()['platform_url'])
                self.assertEqual(browser.post('/tags', headers=headers, json={'tag_name': 'fantasia_epica', 'display_name_tags': 'Fantasia épica 🐉', 'description_tags': 'Histórias em outros mundos.'}).status_code, 201)
                appended = browser.post('/work_classifications', headers=headers, json={
                    'work_classification_name': 'favorite', 'display_name_work_classifications': 'Favorito 🐍',
                    'description_work_classifications': 'A disposable work-rating category.'})
                self.assertEqual(appended.status_code, 201)
                self.assertEqual(browser.post('/work_classifications', headers=headers, json={
                    'work_classification_name': 'first', 'display_name_work_classifications': 'Primeiro ✨', 'tier': 1}).status_code, 201)
                persisted = browser.get('/work_classifications/' + appended.json()['id_work_classifications'])
                self.assertEqual(persisted.json()['tier'], appended.json()['tier'] + 1)
                self.assertEqual(persisted.json()['display_name_work_classifications'], 'Favorito 🐍')
                self.assertEqual(browser.post('/platforms', headers=HEADERS, json=platform).status_code, 403)
                self.assertEqual(browser.post('/platforms', headers=headers, json={**platform, 'platform_url': 'javascript:bad'}).status_code, 422)
            browser.post('/browser/login', headers=HEADERS, json={'username': 'supervisor', 'password': self.api_password})
            headers = {**HEADERS, 'X-CSRF-Token': browser.get('/browser/session').json()['csrf_token']}
            original = CatalogueRepository.create
            def demote(repository, payload, actor):
                self.users.change_role(self.accounts['administrator'].id, self.accounts['supervisor'].id, 'standard')
                return original(repository, payload, actor)
            with patch.object(CatalogueRepository, 'create', demote):
                self.assertEqual(browser.post('/tags', headers=headers, json={'tag_name': 'denied', 'display_name_tags': 'Must not persist'}).status_code, 403)
            with self.provider.connection() as connection:
                self.assertEqual(connection.execute("SELECT count(*) FROM public.tags WHERE tag_name='denied'").fetchone()[0], 0)
                rows = connection.execute("SELECT request_body,response_body FROM public.api_audit_logs WHERE matched_route LIKE '/browser/%'").fetchall()
                self.assertTrue(rows)
                self.assertTrue(all(request is None and response is None for request, response in rows))
