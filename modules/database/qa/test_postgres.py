"""Real database-only start and relational/security checks on exact owned QA resources."""
import copy
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import uuid

import psycopg
from psycopg import sql

from database import runtime
from database.documentation import example
from database.model import ORDER, render
from database.provision import apply_baseline, bootstrap
from database.secrets import protect
from database.settings import ConfigurationError, mapping, read_jsonc

ROOT = Path(__file__).resolve().parents[3]


class PostgreSQLTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = Path(tempfile.mkdtemp(prefix='database-qa-',dir=ROOT/'.tmp'))
        cls.project = 'ouroboros-db-qa-'+uuid.uuid4().hex[:12]
        cls.document = example()
        cls.document['database_name'] = 'database_qa'
        cls.document['schema'] = 'qa_catalogue'
        cls.operational = read_jsonc(ROOT/'modules/database/config.example.jsonc')
        cls.operational['published_address'] = '127.0.0.1'
        # Explicit owner-approved disposable port; production validation still requires 6669.
        cls.operational['published_port'] = int(os.environ.get('OUROBOROS_QA_DB_PORT','2424'))
        if cls.operational['published_port'] not in (2424,4242):
            raise RuntimeError('Select an explicitly approved disposable PostgreSQL port: 2424 or 4242')
        cls.password = 'Aa1!'+secrets.token_hex(5)
        cls.app_password = 'Bb2!'+secrets.token_hex(5)
        (cls.fixture/'modules/database').mkdir(parents=True)
        shutil.copyfile(ROOT/'modules/database/compose.yaml',cls.fixture/'modules/database/compose.yaml')
        (cls.fixture/'modules/api').mkdir(parents=True)
        shutil.copyfile(ROOT/'modules/api/compose.yaml',cls.fixture/'modules/api/compose.yaml')
        shutil.copyfile(ROOT/'compose.basic.yaml',cls.fixture/'compose.basic.yaml')
        (cls.fixture/'.secrets').mkdir()
        protect(cls.fixture/'.secrets',True)
        (cls.fixture/'.secrets/database_sql_password').write_text(cls.password,encoding='utf-8')
        protect(cls.fixture/'.secrets/database_sql_password')
        cls.environment = runtime.environment(cls.fixture,cls.document,cls.operational)
        cls.command = ['compose','--project-name',cls.project,'--project-directory',str(cls.fixture),'--file',str(cls.fixture/'compose.basic.yaml')]
        try:
            # Interrupt hashing after person/API inserts: the enrollment transaction rolls back.
            with patch('argon2.PasswordHasher.hash',side_effect=KeyboardInterrupt):
                cls.start(expected=130)
            with runtime.connect(cls.fixture,cls.document,cls.operational) as connection:
                for table in ('app_user','api_user','super_administrator','plan','module','installation_plan'):
                    if connection.execute(render('SELECT count(*) FROM {'+table+'}',cls.document)).fetchone()[0] != 0:
                        raise RuntimeError('Interrupted enrollment was not atomic')
            cls.start()
        except BaseException:
            cls.cleanup()
            raise

    @classmethod
    def start(cls, expected=0):
        with patch.object(runtime,'PROJECT',cls.project), patch.object(runtime,'prepare_initial',return_value=(cls.document,cls.operational)), patch('sys.stdin.isatty',return_value=True), patch('builtins.input',side_effect=['qa_app_operator','QA Operator','qa_operator']), patch('database.secrets.prompt_password',return_value=cls.app_password):
            if runtime.main(cls.fixture,['--database-only']) != expected:
                raise RuntimeError('Isolated database-only startup failed')

    @classmethod
    def cleanup(cls):
        # Exact UUID-owned test project only; no discovery/prefix cleanup.
        result = subprocess.run(['docker',*cls.command,'--profile','api','down','--volumes'],env=cls.environment,capture_output=True,timeout=60)
        if result.returncode:
            raise RuntimeError('Owned QA resource cleanup failed')

    @classmethod
    def tearDownClass(cls):
        cls.cleanup()

    def setUp(self):
        self.connection = runtime.connect(self.fixture,self.document,self.operational)

    def tearDown(self):
        self.connection.close()

    def execute(self,text,parameters=()):
        return self.connection.execute(render(text,self.document),parameters)

    def insert(self,table,columns,values):
        return self.execute('INSERT INTO {'+table+'}('+columns+') VALUES ('+','.join(['%s']*len(values))+') RETURNING id_'+table,values).fetchone()[0]

    def reject(self,text,parameters=(),exception=psycopg.Error):
        with self.assertRaises(exception):
            with self.connection.transaction():
                self.execute(text,parameters)

    def test_01_second_start_reuses_baseline_and_operator(self):
        before = self.execute('SELECT count(*) FROM {api_audit_log}').fetchone()[0]
        self.start()
        self.assertFalse(apply_baseline(self.connection,self.document,self.operational['master_user']))
        versions={row[0] for row in self.execute('SELECT version FROM {foundation_migration}')}
        self.assertEqual(versions,{'database-v1/001','database-v1/002','database-v1/003'})
        self.assertEqual(self.execute('SELECT name FROM {plan} WHERE plan_number=1').fetchone()[0],
                         'Basic (Plan 1: Database + API Integration)')
        self.assertEqual(self.execute('SELECT count(*) FROM {super_administrator}').fetchone()[0],1)
        self.assertEqual(self.execute('SELECT count(*) FROM {api_audit_log}').fetchone()[0],before)
        modules = self.execute('SELECT m.name FROM {installation_plan} ip JOIN {plan_module} pm USING(id_plan) JOIN {module} m USING(id_module) WHERE ip.effective_until IS NULL ORDER BY m.name').fetchall()
        self.assertEqual(modules,[('api_integration',),('database',)])
        self.assertEqual(len(self.execute('SELECT * FROM {module}').fetchall()),4)
        self.assertFalse(bootstrap(self.connection,self.document,'Duplicate','duplicate',self.app_password))
        credential = self.execute('SELECT secret_hash FROM {api_user_credential}').fetchone()[0]
        from argon2 import PasswordHasher
        self.assertTrue(PasswordHasher().verify(credential,self.app_password))
        # Never print hashes or SQL/application credentials.
        self.reject("INSERT INTO {role}(name) VALUES ('super_administrator')")
        self.reject("INSERT INTO {permission}(resource,action) VALUES ('installation_plan','update')")
        self.reject('INSERT INTO {super_administrator}(id_app_user,id_api_user,id_app_user_api) SELECT id_app_user,id_api_user,id_app_user_api FROM {super_administrator}')

    def test_02_sql_authentication_and_privileges(self):
        self.assertEqual(self.connection.execute('SELECT current_user').fetchone()[0],self.operational['master_user'])
        with self.assertRaises(psycopg.OperationalError):
            psycopg.connect(host='127.0.0.1',port=2424,dbname=self.document['database_name'],user=self.operational['master_user'],password=secrets.token_urlsafe(32),connect_timeout=5)
        with self.connection.transaction():
            self.connection.execute('SET LOCAL ROLE ouroboros_runtime')
            self.reject('CREATE TABLE "qa_catalogue".forbidden(value text)')
            self.reject('DELETE FROM {api_audit_log}')
            self.reject('SELECT secret_hash FROM {api_user_credential}')
            self.reject('DELETE FROM {super_administrator}')
            self.reject('DELETE FROM {installation_plan}')
            self.reject('CREATE TABLE public.forbidden(value text)')

    def test_03_generated_ids_and_atomic_audit(self):
        identifier = self.insert('test','value',('qa',))
        self.assertRegex(identifier,r'^QA[0-9]{7,}$')
        self.reject('UPDATE {test} SET sequence_test = sequence_test+1 WHERE id_test=%s',(identifier,))
        self.reject("UPDATE {test} SET prefix_test='XX' WHERE id_test=%s",(identifier,))
        self.execute('UPDATE {test} SET value=%s WHERE id_test=%s',('changed',identifier))
        events = self.execute('SELECT action FROM {api_audit_log} WHERE resource=%s AND target_id=%s ORDER BY sequence_api_audit_log',('test',identifier)).fetchall()
        self.assertEqual(events,[('INSERT',),('UPDATE',)])
        self.assertEqual(self.execute('SELECT version_number FROM {record_version} WHERE resource=%s AND record_id=%s ORDER BY version_number',('test',identifier)).fetchall(),[(1,),(2,)])
        with self.assertRaises(psycopg.Error):
            with self.connection.transaction():
                self.connection.execute("SELECT set_config('ouroboros.actor_api_user','absent',true)")
                self.insert('test','value',('audit must rollback',))
        self.assertEqual(self.execute('SELECT count(*) FROM {test} WHERE value=%s',('audit must rollback',)).fetchone()[0],0)
        # Width growth: controlled disposable identity advancement, never normal data.
        self.execute('ALTER TABLE {test} ALTER COLUMN sequence_test RESTART WITH 10000000')
        self.assertEqual(self.insert('test','value',('growth',)),'QA10000000')

    def test_04_personal_links_and_availability(self):
        p1 = self.insert('app_user','personal_name',('One',))
        p2 = self.insert('app_user','personal_name',('Two',))
        work = self.insert('work','title,title_language',('QA Work','en'))
        other = self.insert('work','title,title_language',('Other','en'))
        platform = self.insert('platform','name',('QA Platform',))
        availability = self.insert('work_availability','id_work,id_platform',(work,platform))
        self.reject('INSERT INTO {work_availability}(id_work,id_platform) VALUES (%s,%s)',(work,platform))
        self.insert('user_work','id_app_user,id_work',(p1,work))
        self.insert('user_work','id_app_user,id_work',(p2,work))
        entry = self.insert('watch_list_entry','id_app_user,id_work,id_work_availability',(p1,work,availability))
        self.reject('INSERT INTO {watch_history}(id_app_user,id_work,id_work_availability) VALUES (%s,%s,%s)',(p1,other,availability))
        history1 = self.insert('watch_history','id_app_user,id_work',(p1,work))
        history2 = self.insert('watch_history','id_app_user,id_work',(p1,work))
        self.assertNotEqual(history1,history2)
        tag = self.insert('tag','id_app_user,name,display_name',(p1,'qa_tag','QA'))
        self.reject('INSERT INTO {work_tag}(id_app_user,id_work,id_tag) VALUES (%s,%s,%s)',(p2,work,tag))
        self.reject('INSERT INTO {work_tag}(id_app_user,id_work,id_tag,id_watch_list_entry) VALUES (%s,%s,%s,%s)',(p2,work,tag,entry))
        self.insert('work_tag','id_app_user,id_work,id_tag,id_watch_history',(p1,work,tag,history1))
        self.reject('UPDATE {tag} SET id_app_user=%s WHERE id_tag=%s',(p2,tag))
        self.reject('DELETE FROM {work} WHERE id_work=%s',(work,))

    def test_05_structural_changes_fail_and_all_tables_have_identity(self):
        for change in ('prefixes','schema','vocabulary','base_quantity_digits'):
            changed = copy.deepcopy(self.document)
            if change == 'prefixes': changed['prefixes']['work']='ZZ'
            elif change == 'schema': changed['schema']='another_schema'
            elif change == 'base_quantity_digits': changed[change]=8
            else: changed['vocabulary']['work']['name']='magazine'
            with self.assertRaises(ConfigurationError):
                apply_baseline(self.connection,changed,self.operational['master_user'])
        names = mapping(self.document)
        columns = self.connection.execute('SELECT table_name,column_name FROM information_schema.columns WHERE table_schema=%s',(self.document['schema'],)).fetchall()
        for table in ORDER:
            for prefix in ('id_','sequence_','prefix_'):
                self.assertIn((names[table],prefix+names[table]),columns)

    def test_06_plan_change_reserved_holder(self):
        plan = self.execute('SELECT id_plan FROM {plan}').fetchone()[0]
        ordinary = self.insert('api_user','username',('ordinary_'+uuid.uuid4().hex[:6],))
        with self.connection.transaction():
            self.connection.execute('SET LOCAL ROLE ouroboros_runtime')
            self.connection.execute("SELECT set_config('ouroboros.actor_api_user',%s,true)",(ordinary,))
            self.reject('SELECT "qa_catalogue".change_plan(%s)',(plan,))
        holder = self.execute('SELECT id_api_user FROM {super_administrator}').fetchone()[0]
        with self.connection.transaction():
            self.connection.execute('SET LOCAL ROLE ouroboros_runtime')
            self.connection.execute("SELECT set_config('ouroboros.actor_api_user',%s,true)",(holder,))
            self.execute('SELECT "qa_catalogue".change_plan(%s)',(plan,))
        self.assertEqual(self.execute('SELECT count(*) FROM {installation_plan} WHERE effective_until IS NULL').fetchone()[0],1)

    def test_07_startup_rejects_structure_before_recreating_container(self):
        changed = copy.deepcopy(self.document)
        changed['prefixes']['work']='XY'
        actual_docker = runtime.docker
        commands = []
        def monitored(arguments,*args,**kwargs):
            commands.append(arguments)
            return actual_docker(arguments,*args,**kwargs)
        with patch.object(runtime,'PROJECT',self.project), patch.object(runtime,'prepare_initial',return_value=(changed,self.operational)), patch.object(runtime,'docker',side_effect=monitored):
            self.assertEqual(runtime.main(self.fixture,[]),1)
        self.assertFalse(any('up' in command for command in commands))

    def test_08_membership_history_and_effective_health(self):
        holder = self.execute('SELECT id_app_user_api FROM {super_administrator}').fetchone()[0]
        self.reject('DELETE FROM {app_user_api} WHERE id_app_user_api=%s',(holder,))
        self.reject('UPDATE {app_user_api} SET valid_from=valid_from-interval \'1 day\' WHERE id_app_user_api=%s',(holder,))
        with patch.object(runtime,'PROJECT',self.project):
            resources,_ = runtime.owned_resources(self.fixture)
        self.assertEqual(len(resources),1)
        health = resources[0]['Config']['Healthcheck']
        self.assertEqual(health['Interval'],self.operational['healthcheck']['interval_seconds']*1000000000)
        self.assertEqual(health['Timeout'],self.operational['healthcheck']['timeout_seconds']*1000000000)
        self.assertEqual(health['Retries'],self.operational['healthcheck']['retries'])


class AlternateVocabularyTests(PostgreSQLTests):
    @classmethod
    def setUpClass(cls):
        # Reuse the real startup harness with a second explicitly approved QA port.
        original = runtime.environment
        def alternate_environment(root,document,operational):
            document['vocabulary']['work']['name']='book'
            document['vocabulary']['activity']['name']='read'
            operational['published_port']=4242
            return original(root,document,operational)
        with patch.object(runtime,'environment',side_effect=alternate_environment):
            super().setUpClass()

    def test_02_sql_authentication_and_privileges(self):
        self.assertEqual(self.connection.execute('SELECT current_user').fetchone()[0],self.operational['master_user'])

    def test_06_plan_change_reserved_holder(self):
        super().test_06_plan_change_reserved_holder()


if __name__ == '__main__':
    unittest.main()
