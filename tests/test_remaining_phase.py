"""Tier ordering and complete integer-ID CRUD in owned disposable storage."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
import uuid
from unittest.mock import patch
import test_catalogue_api as legacy
from app.database import connect, ensure_database
from app.migrate import migrate


@unittest.skipUnless(os.environ.get('FOUNDATION_RUN_INTEGRATION') == '1', 'Requires owned disposable Docker integration')
class RemainingPhaseTests(unittest.TestCase):
    setUpClass = classmethod(legacy.CatalogueAPITests.setUpClass.__func__)
    cleanup = classmethod(legacy.CatalogueAPITests.cleanup.__func__)
    setUp = legacy.CatalogueAPITests.setUp
    call = legacy.CatalogueAPITests.call
    create = legacy.CatalogueAPITests.create

    def classification(self, name, **extra):
        return self.create('work_classifications', work_classification_name=name,
                           display_name_work_classifications=name + ' 🐉', **extra)

    def ordered(self):
        return self.call('GET','/work_classifications').json()['items']

    def audit(self, response):
        return self.call('GET','/api_audit_logs',params={'interaction_id':response.headers['X-Interaction-ID']}).json()['items'][0]

    def test_01_backfill_empty_nine_and_gaps_preserves_records(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'sql/migrations').mkdir(parents=True)
            for source in (self.root / 'sql/migrations').glob('*.sql'):
                if source.name[:3] <= '008': shutil.copy(source,root / 'sql/migrations')
            for sequences in ([],list(range(1,10)),[2,7,15]):
                database = {**self.db,'name':'backfill_' + uuid.uuid4().hex}
                ensure_database(database,self.master)
                with connect(database,self.master) as connection:
                    migrate(connection,root)
                    for value in sequences:
                        connection.execute('ALTER SEQUENCE public.work_classifications_sequence_work_classifications_seq RESTART WITH ' + str(value))
                        connection.execute("INSERT INTO public.work_classifications(work_classification_name,display_name_work_classifications,description_work_classifications) VALUES (%s,%s,%s)",
                                           ('class_' + str(value),'Original 🐉 ' + str(value),'Keep description'))
                    before = connection.execute('SELECT * FROM public.work_classifications ORDER BY sequence_work_classifications').fetchall()
                    connection.execute("INSERT INTO public.test(value) VALUES ('Historical text')")
                with connect(database,self.master) as connection:
                    migrate(connection,self.root)
                    after = connection.execute('SELECT * FROM public.work_classifications ORDER BY sequence_work_classifications').fetchall()
                    self.assertEqual([row[:-1] for row in after],before)
                    self.assertEqual([row[-1] for row in after],list(range(1,len(sequences)+1)))
                    comment = connection.execute("SELECT col_description('public.work_classifications'::regclass,(SELECT attnum FROM pg_attribute WHERE attrelid='public.work_classifications'::regclass AND attname='tier'))").fetchone()[0]
                    self.assertIn('contiguous_sequence_rank' if sequences == [2,7,15] else 'preserved_sequence',comment)
                    self.assertEqual(connection.execute('SELECT value,created_at,created_at_timezone FROM public.test').fetchone(),('Historical text',None,None))
                    original = connection.execute('SELECT version,checksum FROM foundation_migrations ORDER BY version').fetchall()
                    migrate(connection,self.root)
                    self.assertEqual(connection.execute('SELECT version,checksum FROM foundation_migrations ORDER BY version').fetchall(),original)

    def test_02_append_insert_move_validation_and_shift_audit(self):
        first = self.classification('first')
        last = self.classification('last')
        middle = self.classification('middle',tier=2)
        beginning = self.classification('beginning',tier=1)
        self.assertEqual([r['work_classification_name'] for r in self.ordered()],['beginning','first','middle','last'])
        path = '/work_classifications/' + last['id_work_classifications']
        response = self.call('PUT',path,json={'tier':1})
        self.assertEqual(response.json()['tier'],1)
        audit = self.audit(response)
        order = audit['mutation_details']['reordering']
        self.assertEqual(order['moved'],{'id':last['id_work_classifications'],'old_tier':4,'new_tier':1})
        self.assertEqual(order['affected_count'],4)
        self.assertEqual(audit['target_id'],last['id_work_classifications'])
        self.assertEqual(audit['mutation_count'],4)
        self.assertEqual(audit['differences']['tier'],{'before':4,'after':1})
        for tier in (None,True,False,1.5,0,-1,5):
            self.call('PUT',path,expected=422,json={'tier':tier})
        for tier in (None,True,1.5,0,6):
            self.call('POST','/work_classifications',expected=422,json={'work_classification_name':'invalid','display_name_work_classifications':'invalid','tier':tier})
        self.call('PUT',path,json={'tier':4})
        unchanged = self.call('GET',path).json()
        self.assertEqual(self.call('PUT',path,json=unchanged).json(),unchanged)
        self.assertEqual(self.call('PUT',path,json={'description_work_classifications':'Changed text'}).json()['tier'],4)
        self.call('PUT',path,expected=422,json={'sequence_work_classifications':999})
        bad = self.call('PUT','/work_classifications',role='administrator',expected=422,params={'confirm':True},json={'tier':1})
        self.assertIn('individual PUT',str(bad.json()))
        self.assertEqual([r['tier'] for r in self.ordered()],[1,2,3,4])
        self.assertEqual(unchanged['sequence_work_classifications'],last['sequence_work_classifications'])
        self.assertEqual(self.classification('explicit_last',tier=5)['tier'],5)

    def test_03_delete_compaction_references_and_atomic_rollback(self):
        rows = [self.classification('entry_' + str(i)) for i in range(5)]
        work = self.create('works',title='Referenced',title_language='en')
        history = self.create('watch_history',id_works=work['id_works'],id_work_classifications=rows[1]['id_work_classifications'])
        before = self.ordered()
        self.call('DELETE','/work_classifications/' + rows[1]['id_work_classifications'],expected=409)
        self.assertEqual(self.ordered(),before)
        self.call('DELETE','/work_classifications',role='administrator',expected=409,params={'confirm':True})
        self.assertEqual(self.ordered(),before)
        self.call('DELETE','/work_classifications/' + rows[0]['id_work_classifications'],expected=204)
        self.assertEqual([r['tier'] for r in self.ordered()],[1,2,3,4])
        response = self.call('DELETE','/work_classifications',role='administrator',params={'confirm':True,'tier':2})
        self.assertEqual(response.json()['deleted_count'],1)
        self.assertEqual([r['tier'] for r in self.ordered()],[1,2,3])
        self.assertEqual([r['id_work_classifications'] for r in self.ordered()], [rows[i]['id_work_classifications'] for i in (1,3,4)])
        self.assertEqual(self.audit(response)['mutation_details']['reordering']['shifted_count'],2)
        self.call('DELETE','/work_classifications/' + rows[4]['id_work_classifications'],expected=204)
        self.call('DELETE','/watch_history/' + history['id_watch_history'],expected=204)
        self.assertEqual(self.call('DELETE','/work_classifications',role='administrator',params={'confirm':True}).json()['deleted_count'],2)
        self.assertEqual(self.ordered(),[])
        self.assertGreater(self.classification('after_clear')['sequence_work_classifications'],rows[-1]['sequence_work_classifications'])

    def test_04_concurrent_ordering_and_small_audit_limit(self):
        rows = [self.classification('initial_' + str(i)) for i in range(12)]
        def action(index):
            if index % 3 == 0:
                return self.client.post('/work_classifications',headers=self.headers['supervisor'],json={'work_classification_name':'new_' + str(index),'display_name_work_classifications':'New','tier':1})
            if index % 3 == 1:
                return self.client.put('/work_classifications/' + rows[index % 12]['id_work_classifications'],headers=self.headers['supervisor'],json={'tier':1})
            return self.client.delete('/work_classifications/' + rows[index % 12]['id_work_classifications'],headers=self.headers['supervisor'])
        with ThreadPoolExecutor(max_workers=6) as workers:
            responses = list(workers.map(action,range(12)))
        self.assertEqual([r.status_code for r in responses],[201,200,204]*4)
        records = self.ordered()
        self.assertEqual([r['tier'] for r in records],list(range(1,len(records)+1)))
        from app.audit_context import bounded_mutation_details
        details = {'reordering':{'action':'move','moved':{'id':'WC0000001','old_tier':12,'new_tier':1},'affected_count':12,'shifted_count':11,'shifted_records':[{'id':'WC0000002','old_tier':2,'new_tier':3}]*20}}
        bounded = bounded_mutation_details(details,256)
        self.assertLessEqual(len(json.dumps(bounded).encode()),256)
        self.assertEqual(bounded['reordering']['moved']['id'],'WC0000001')
        self.assertTrue(bounded['reordering']['shifted_records_omitted'])
        self.config['audit']['mutation_max_bytes'] = 256
        response = self.call('PUT','/work_classifications/' + records[-1]['id_work_classifications'],json={'tier':1})
        evidence = self.audit(response)['mutation_details']
        self.assertLessEqual(len(json.dumps(evidence).encode()),256)
        self.assertEqual(evidence['reordering']['moved']['id'],records[-1]['id_work_classifications'])
        self.assertTrue(evidence['reordering']['shifted_records_omitted'])

    def test_05_complete_test_crud_roles_and_roundtrip(self):
        for role in ('standard','supervisor','administrator'):
            row = self.call('POST','/test',role=role,expected=201,json={'value':'Text 🐉 ' + role}).json()
            self.assertIsInstance(row['id'],int)
            self.assertTrue(row['created_at'].endswith('Z'))
            path = '/test/' + str(row['id'])
            self.assertEqual(self.call('GET',path,role=role).json(),row)
            self.assertEqual(self.call('PUT',path,role=role,json=row).json(),row)
            updated = self.call('PUT',path,role=role,json={'value':'x 🐉' * 20000}).json()
            self.assertEqual(updated['value'],'x 🐉' * 20000)
            for payload in ({},{'unknown':1},{'id':row['id']+1},{'created_at':None},{'value':None}):
                self.call('PUT',path,role=role,expected=422,json=payload)
            self.call('DELETE',path,role=role,expected=204)
            self.call('GET',path,role=role,expected=404)
        schema = self.client.get('/openapi.json').json()
        refs = [schema['paths'][path][method]['responses'][status]['content']['application/json']['schema'] for path,method,status in (
            ('/test','post','201'),('/test/{id}','get','200'),('/test/{id}','put','200'))]
        self.assertEqual(refs[0],refs[1]); self.assertEqual(refs[1],refs[2])

    def test_06_test_bulk_filters_preview_and_current_permissions(self):
        rows = [self.call('POST','/test',role='standard',expected=201,json={'value':value}).json() for value in ('Exact%_\\','Other','Other')]
        self.assertEqual(self.call('GET','/test',role='standard',params={'value':r'Exact\%\_\\'}).json()['count'],1)
        self.assertEqual(self.call('GET','/test',params={'created_at_to':rows[0]['created_at']}).json()['count'],0)
        self.call('GET','/test',expected=422,params={'created_at_from':'2026-01-01T00:00:00'})
        self.call('GET','/test',expected=422,params={'created_at_to':rows[0]['created_at'],'created_at_from':rows[1]['created_at']})
        for role in ('standard','supervisor'):
            for method in ('PUT','DELETE'):
                self.call(method,'/test',role=role,expected=403,params={'confirm':True},**({'json':{'value':'denied'}} if method=='PUT' else {}))
        for params in ({},{'confirm':False},{'confirm':True,'page':1},{'confirm':True,'vlaue':'typo'},{'confirm':True,'display_timezone':'UTC'}):
            self.call('DELETE','/test',role='administrator',expected=422,params=params)
        preview = self.call('PUT','/test',role='administrator',params={'dry_run':True,'value':'Other'},json={'value':'Changed'}).json()
        self.assertEqual(preview['matched_count'],2)
        actual = self.call('PUT','/test',role='administrator',params={'confirm':True,'value':'Other'},json={'value':'Changed'})
        self.assertEqual(actual.json()['updated_count'],2)
        self.assertEqual(self.audit(actual)['mutation_count'],2)
        self.assertEqual(self.call('DELETE','/test',role='administrator',params={'confirm':True,'value':'Changed'}).json()['deleted_count'],2)
        self.assertEqual(self.call('DELETE','/test',role='administrator',params={'confirm':True,'value':'missing'}).json()['deleted_count'],0)
        later = self.call('POST','/test',role='standard',expected=201,json={'value':'Later'}).json()
        self.assertGreater(later['id'],rows[-1]['id'])
        from app.database_test import TestRepository
        original = TestRepository.update
        def revoke(repository, entry_id, payload, claims):
            with self.provider.connection() as connection:
                connection.execute('UPDATE api_users SET credential_version=credential_version+1 WHERE id=%s',(self.accounts['standard'].id,))
            return original(repository,entry_id,payload,claims)
        with patch.object(TestRepository,'update',revoke):
            self.call('PUT','/test/' + str(later['id']),role='standard',expected=401,json={'value':'denied'})
        self.assertEqual(self.call('GET','/test/' + str(later['id'])).json()['value'],'Later')
