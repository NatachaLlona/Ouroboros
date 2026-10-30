"""Next-phase contracts on exclusively owned disposable PostgreSQL."""
import os
import unittest
from unittest.mock import patch
import test_catalogue_api as legacy


@unittest.skipUnless(os.environ.get('FOUNDATION_RUN_INTEGRATION') == '1', 'Requires owned disposable Docker integration')
class NextPhaseTests(unittest.TestCase):
    setUpClass = classmethod(legacy.CatalogueAPITests.setUpClass.__func__)
    cleanup = classmethod(legacy.CatalogueAPITests.cleanup.__func__)
    setUp = legacy.CatalogueAPITests.setUp
    call = legacy.CatalogueAPITests.call
    create = legacy.CatalogueAPITests.create
    graph = legacy.CatalogueAPITests.graph

    def test_audit_creation_roundtrip_and_errors(self):
        rows = self.graph()
        for table, row in rows.items():
            self.assertTrue(row['created_at'].endswith('Z'))
            self.assertEqual(row['created_at_timezone'], 'Europe/Lisbon')
            self.assertEqual(self.call('PUT', '/' + table + '/' + row['id_' + table], json=row).json(), row)
        response = self.call('GET', '/works/MISSING', expected=404)
        interaction = response.headers['X-Interaction-ID']
        self.assertEqual(response.json()['error']['code'], 'RESOURCE_NOT_FOUND')
        self.assertEqual(response.json()['error']['interaction_id'], interaction)
        audit = self.call('GET', '/api_audit_logs', params={'interaction_id': interaction}).json()['items'][0]
        self.assertEqual(audit['status'], 'failure')
        self.assertEqual(audit['error_code'], 'RESOURCE_NOT_FOUND')
        self.assertEqual(audit['http_status'], 404)
        self.call('GET', '/api_audit_logs', role='standard', expected=403)
        for method in ('POST', 'PUT', 'DELETE'):
            self.call(method, '/api_audit_logs', role='administrator', expected=405)

    def test_bulk_confirmation_preview_and_transaction(self):
        first = self.create('works', title='First', title_language='en')
        self.create('works', title='Second', title_language='en')
        params = {'id_works': first['id_works']}
        response = self.call('PUT', '/works', role='administrator', expected=422, params=params, json={'synopsis':'Changed'})
        self.assertEqual(response.json()['error']['code'], 'CONFIRMATION_REQUIRED')
        preview = self.call('PUT', '/works', role='administrator', params={**params,'dry_run':True}, json={'synopsis':'Changed'}).json()
        self.assertEqual(preview['matched_count'], 1)
        self.assertIsNone(self.call('GET', '/works/' + first['id_works']).json()['synopsis'])
        actual = self.call('PUT', '/works', role='administrator', params={**params,'confirm':True}, json={'synopsis':'Changed'}).json()
        self.assertEqual(actual['updated_count'], 1)
        for invalid in ('page','order_by','display_timezone','titlle'):
            self.call('DELETE', '/works', role='administrator', expected=422, params={'confirm':True,invalid:'x'})
        self.call('PUT', '/works', expected=403, params={'confirm':True}, json={'synopsis':'denied'})
        deletion = self.call('DELETE', '/works', role='administrator', params={**params,'confirm':True}).json()
        self.assertEqual(deletion['deleted_count'], 1)
        self.assertEqual(self.call('GET', '/works').json()['count'], 1)

    def test_source_timezone_and_bounds(self):
        work = self.create('works', title='Date', title_language='en')
        row = self.create('watch_history', id_works=work['id_works'], watched_at='2026-07-01T12:00:00+01:00', watched_at_timezone='Europe/Lisbon')
        self.assertEqual(row['watched_at'], '2026-07-01T11:00:00Z')
        self.assertEqual(row['watched_at_offset'], '+01:00')
        original = self.call('GET', '/watch_history/' + row['id_watch_history'], params={'display_timezone':'original'}).json()
        self.assertEqual(original['presentation']['dates']['watched_at']['offset'], '+01:00')
        self.assertEqual(self.call('PUT', '/watch_history/' + row['id_watch_history'], params={'display_timezone':'original'}, json=original).json(), original)
        for stamp in ('2026-07-01T12:00:00','2026-07-01T12:00:00+00:00'):
            self.call('POST', '/watch_history', expected=422, json={'id_works':work['id_works'],'watched_at':stamp,'watched_at_timezone':'Europe/Lisbon'})
        self.assertEqual(self.call('GET', '/works', params={'created_at_from':work['created_at']}).json()['count'],1)
        self.assertEqual(self.call('GET', '/works', params={'created_at_to':work['created_at']}).json()['count'],0)
        self.call('GET', '/works', expected=422, params={'created_at_from':'2026-01-01T00:00:00'})
        path = '/watch_history/' + row['id_watch_history']
        self.call('PUT',path,expected=422,json={'watched_at':'2026-07-01T12:00:00+00:00','watched_at_timezone':'Europe/Lisbon'})
        changed = self.call('PUT',path,json={'watched_at':'2026-12-01T12:00:00-03:00'}).json()
        self.assertEqual(changed['watched_at_offset'],'-03:00')
        self.assertIsNone(changed['watched_at_timezone'])
        cleared = self.call('PUT',path,json={'watched_at':None}).json()
        self.assertIsNone(cleared['watched_at_offset'])
        self.assertIsNone(cleared['watched_at_timezone'])

    def audit(self, response):
        return self.call('GET', '/api_audit_logs', params={'interaction_id':response.headers['X-Interaction-ID']}).json()['items'][0]

    def test_audit_atomicity_outage_and_finalization(self):
        from app.audit_store import AuditStore
        work = self.create('works', title='Preserved', title_language='en')
        with patch.object(AuditStore, 'begin', side_effect=RuntimeError('safe injected outage')):
            self.call('PUT', '/works/' + work['id_works'], expected=503, json={'synopsis':'must roll back'})
            self.call('POST', '/test', role='administrator', expected=503, json={'value':'must roll back'})
            self.call('PUT', '/users/me/password', role='standard', expected=503,
                json={'current_password':self.api_password,'new_password':'New-password-for-isolated-test-123!'})
            self.call('GET', '/health')
        self.assertIsNone(self.call('GET', '/works/' + work['id_works']).json()['synopsis'])
        # Fail only the transactional evidence writer after request entry commits.
        with self.provider.connection() as connection, connection.cursor() as cursor:
            cursor.execute("CREATE OR REPLACE FUNCTION public.capture_api_mutation() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'Injected audit failure' USING ERRCODE='P9001'; END; $$")
        rejected = self.call('PUT', '/works/' + work['id_works'], expected=503, json={'synopsis':'must also roll back'})
        self.assertEqual(rejected.json()['error']['code'], 'AUDIT_UNAVAILABLE')
        self.assertEqual(self.audit(rejected)['business_outcome'], 'rolled_back')
        self.assertIsNone(self.call('GET', '/works/' + work['id_works']).json()['synopsis'])
        # Restore only the function from the copied migration in this owned database.
        migration = (self.root / 'sql/migrations/008_create_api_audit_logs.sql').read_text(encoding='utf-8')
        function = migration.split('CREATE FUNCTION public.capture_api_mutation()',1)[1].split('\nDO $$',1)[0]
        with self.provider.connection() as connection, connection.cursor() as cursor:
            cursor.execute('CREATE OR REPLACE FUNCTION public.capture_api_mutation()' + function)
        with patch.object(AuditStore, 'finish', side_effect=RuntimeError('safe injected finalization failure')):
            committed = self.call('PUT', '/works/' + work['id_works'], json={'synopsis':'committed evidence'})
        audit = self.audit(committed)
        self.assertEqual(audit['status'], 'in_progress')
        self.assertEqual(audit['business_outcome'], 'committed')
        self.assertEqual(audit['differences']['synopsis']['after'], 'committed evidence')
        self.assertIn('API audit persistence failed', self.output.getvalue())

    def test_unknown_routes_auth_and_internal_error_codes(self):
        from app.catalogue_repository import CatalogueRepository
        for method,path,status,code in [('GET','/unknown-route',404,'RESOURCE_NOT_FOUND'),('PATCH','/works',405,'METHOD_NOT_ALLOWED')]:
            response = self.call(method,path,expected=status)
            self.assertEqual(response.json()['error']['code'],code)
            self.assertEqual(self.audit(response)['error_code'],code)
        response = self.client.get('/works')
        self.assertEqual(response.status_code,401)
        self.assertEqual(self.audit(response)['status'],'failure')
        with patch.object(CatalogueRepository,'page',side_effect=RuntimeError('private SQL detail')):
            response = self.call('GET','/works',expected=500)
        self.assertEqual(self.audit(response)['error_code'],'INTERNAL_ERROR')
        self.assertNotIn('private SQL detail',response.text + self.output.getvalue())

    def test_migration_preserves_unknown_historical_context(self):
        import shutil
        import tempfile
        import uuid
        from pathlib import Path
        from app.database import ensure_database, connect
        from app.migrate import migrate
        database = {**self.db,'name':'historical_' + uuid.uuid4().hex}
        ensure_database(database,self.master)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'sql/migrations').mkdir(parents=True)
            for source in (self.root / 'sql/migrations').glob('*.sql'):
                if source.name[:3] < '007': shutil.copy(source,root / 'sql/migrations')
            with connect(database,self.master) as connection:
                migrate(connection,root)
                connection.execute("INSERT INTO public.works(title,title_language) VALUES ('Historical','en')")
            with connect(database,self.master) as connection:
                migrate(connection,self.root)
                self.assertEqual(connection.execute('SELECT created_at,created_at_timezone FROM public.works').fetchone(),(None,None))
                row = connection.execute("INSERT INTO public.works(title,title_language,created_at) VALUES ('New','en',NULL) RETURNING created_at,created_at_timezone").fetchone()
                self.assertIsNotNone(row[0])
                self.assertEqual(row[1],'Europe/Lisbon')

    def test_bounded_privacy_and_read_access(self):
        response = self.call('POST', '/test', role='administrator', expected=201,
            json={'value':'{"nested":{"password":"NEVER-AUDIT-THIS"}}'})
        audit = self.audit(response)
        self.assertNotIn('NEVER-AUDIT-THIS', str(audit))
        self.assertIn('REDACTED', str(audit['differences']))
        response = self.call('POST', '/test', role='administrator', expected=201, json={'value':'x' * 20000})
        audit = self.audit(response)
        self.assertIsNone(audit['request_body'])
        self.assertTrue(audit['capture']['request']['truncated'])
        self.assertIsNone(audit['differences'])
        token = self.client.post('/token', data={'username':'administrator','password':self.api_password})
        audit = self.audit(token)
        self.assertIsNone(audit['request_body'])
        self.assertIsNone(audit['response_body'])
        invalid = self.client.put('/users/me/password',headers=self.headers['standard'],json={'password=NEVER-AUDIT-THIS':True})
        self.assertEqual(invalid.status_code,422)
        audit = self.audit(invalid)
        self.assertIsNone(audit['request_body'])
        self.assertIsNone(audit['response_body'])
        self.assertNotIn('NEVER-AUDIT-THIS',str(audit) + invalid.text + self.output.getvalue())
        access = self.call('GET', '/api_audit_logs', params={'page_size':10})
        audit = self.audit(access)
        self.assertIsNone(audit['response_body'])
        self.assertEqual(audit['mutation_details']['returned_count'],len(access.json()['items']))

    def test_bulk_rollback_zero_matches_and_all_resource_previews(self):
        rows = self.graph()
        for table, row in rows.items():
            preview = self.call('DELETE', '/' + table, role='administrator', params={'dry_run':True,'id_' + table:row['id_' + table]}).json()
            self.assertEqual(preview['matched_count'],1)
            self.call('PUT', '/' + table, role='administrator', expected=422, params={'confirm':True}, json={'created_at':row['created_at']})
        rejected = self.call('DELETE', '/works', role='administrator', expected=409, params={'confirm':True})
        self.assertEqual(self.audit(rejected)['business_outcome'],'rolled_back')
        self.assertEqual(self.call('GET', '/works').json()['count'],1)
        self.call('PUT', '/work_tags', role='administrator', expected=422, params={'confirm':True}, json={'id_tags':None})
        self.assertEqual(self.call('GET', '/work_tags/' + rows['work_tags']['id_work_tags']).json()['id_tags'],rows['tags']['id_tags'])
        zero = self.call('PUT', '/works', role='administrator', params={'confirm':True,'id_works':'WK9999999'}, json={'synopsis':None})
        self.assertEqual(zero.json()['updated_count'],0)
        self.assertEqual(self.audit(zero)['mutation_details']['applied_count'],0)
        unchanged = self.call('PUT','/works',role='administrator',params={'confirm':True},json={'title':rows['works']['title']})
        self.assertEqual(unchanged.json()['updated_count'],1)

