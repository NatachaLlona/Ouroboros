"""Real restricted-login HTTP verification on UUID-owned PostgreSQL only."""
import copy
import secrets
import unittest
import uuid
import json
import socket
import subprocess
import time
import urllib.request
import ssl
import jwt
from fastapi.testclient import TestClient
from database.qa import test_postgres
from database import runtime
from database.model import render
from api.service.app import create_app
from api.service.config import load
from api.service.migrations import inspect_contract, migrate, LOGIN
from api.service.store import Store
from api.qa.test_tls import certificate
from unittest.mock import patch


class APITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.harness=test_postgres.PostgreSQLTests
        cls.harness.setUpClass()
        cls.runtime_password=secrets.token_urlsafe(48)
        cls.key=secrets.token_urlsafe(64)
        cls.settings=load(test_postgres.ROOT)
        try:
            with runtime.connect(cls.harness.fixture,cls.harness.document,cls.harness.operational) as connection:
                # Inspect actual tables/columns and capability flags before mounting endpoints.
                inspect_contract(connection,cls.harness.document)
                migrate(connection,cls.harness.document,cls.runtime_password)
                cls.assert_registered=inspect_contract(connection,cls.harness.document,require_api=True)
        except BaseException:
            cls.harness.tearDownClass()
            raise
        cls.store=Store(cls.harness.document,cls.settings,{
            'host':'127.0.0.1','port':cls.harness.operational['published_port'],'dbname':cls.harness.document['database_name'],
            'user':LOGIN,'password':cls.runtime_password})

    @classmethod
    def tearDownClass(cls):
        cls.harness.tearDownClass()

    def setUp(self):
        self.client=TestClient(create_app(self.store,self.key),raise_server_exceptions=False)
        response=self.client.post('/auth/user-token',json={'username':'qa_operator','password':self.harness.app_password})
        self.assertEqual(response.status_code,200)
        self.super_headers={'Authorization':'Bearer '+response.json()['access_token']}

    def tearDown(self):
        self.client.close()

    def account(self,role='user',person=True,permissions=(),headers=None):
        body={'username':'account_'+uuid.uuid4().hex[:12],'role':role,'permissions':list(permissions)}
        if person:
            body['app_user_name']='Disposable Test Person'
        response=self.client.post('/api-users',json=body,headers=headers or self.super_headers)
        self.assertEqual(response.status_code,201)
        credentials=response.json()
        response=self.client.post('/oauth/token',data={'grant_type':'client_credentials','client_id':credentials['client_id'],'client_secret':credentials['client_secret']})
        self.assertEqual(response.status_code,200)
        return credentials,{'Authorization':'Bearer '+response.json()['access_token']}

    def test_01_restricted_runtime_and_authentication_revocation(self):
        credentials,headers=self.account('administrator',False)
        self.assertEqual(self.client.get('/api-users',headers=headers).status_code,200)
        self.assertEqual(self.client.get('/api-users').status_code,401)
        self.assertEqual(self.client.post('/oauth/token',data={'grant_type':'client_credentials','client_id':'qa_operator','client_secret':self.harness.app_password}).status_code,401)
        token=headers['Authorization'][7:]
        claims=jwt.decode(token,self.key,algorithms=['HS256'],options={'verify_aud':False})
        claims.update(iat=1,nbf=1,exp=2)
        expired=jwt.encode(claims,self.key,algorithm='HS256')
        self.assertEqual(self.client.get('/api-users',headers={'Authorization':'Bearer '+expired}).status_code,401)
        self.assertEqual(self.client.delete('/credentials/'+credentials['client_id'],headers=self.super_headers).status_code,204)
        self.assertEqual(self.client.get('/api-users',headers=headers).status_code,401)
        with self.store.transaction() as session:
            self.assertEqual(session.execute('SELECT current_user AS name').fetchone()['name'],LOGIN)
            row=session.execute("SELECT rolsuper,rolcreaterole FROM pg_roles WHERE rolname=current_user").fetchone()
            self.assertFalse(row['rolsuper'] or row['rolcreaterole'])

    def test_02_manager_creation_ceiling_and_self_promotion(self):
        manager,headers=self.account('manager')
        for role in ('manager','user'):
            self.account(role,headers=headers)
        response=self.client.post('/api-users',json={'username':'blocked_'+uuid.uuid4().hex[:8],'role':'administrator'},headers=headers)
        self.assertEqual(response.status_code,403)
        response=self.client.put('/api-users/'+manager['id_api_user']+'/role',json={'role':'administrator'},headers=headers)
        self.assertEqual(response.status_code,403)
        response=self.client.post('/api-users',json={'username':'blocked_'+uuid.uuid4().hex[:8],'role':'user','permissions':['work:update']},headers=headers)
        self.assertEqual(response.status_code,403)
        response=self.client.post('/api-users',json={'username':'blocked_'+uuid.uuid4().hex[:8],'role':'super_administrator'},headers=self.super_headers)
        self.assertEqual(response.status_code,422)
        self.assertEqual(self.client.put('/api-users/'+manager['id_api_user']+'/permissions',json={'permissions':['work:create']},headers=headers).status_code,403)

    def test_03_ownership_before_count_and_personal_catalogue_separation(self):
        work=self.client.post('/work',json={'title':'Owned QA','title_language':'en'},headers=self.super_headers).json()['id_work']
        permissions=['user_work:create','user_work:update','watch_list_entry:create']
        _,first=self.account(permissions=permissions)
        _,second=self.account(permissions=permissions)
        response=self.client.post('/user_work',json={'id_work':work,'personal_name':'Private label'},headers=first)
        self.assertEqual(response.status_code,201)
        identifier=response.json()['id_user_work']
        self.assertEqual(self.client.get('/user_work',headers=second).json()['total'],0)
        self.assertEqual(self.client.get('/user_work/'+identifier,headers=second).status_code,404)
        self.assertEqual(self.client.patch('/user_work/'+identifier,json={'personal_name':'stolen'},headers=second).status_code,404)
        self.assertEqual(self.client.patch('/work/'+work,json={'title':'forbidden'},headers=first).status_code,403)
        self.assertEqual(self.client.post('/user_work',json={'id_work':work,'id_app_user':'spoofed'},headers=second).status_code,422)
        _,integration=self.account('administrator',False)
        self.assertEqual(self.client.get('/watch_history',headers=integration).status_code,403)

    def test_04_put_replacement_patch_and_extra_fields(self):
        response=self.client.post('/platform',json={'name':'Original','description':'Keep','url':'https://example.test'},headers=self.super_headers)
        self.assertEqual(response.status_code,201)
        identifier=response.json()['id_platform']
        path='/platform/'+identifier
        self.assertEqual(self.client.patch(path,json={'name':'Patched'},headers=self.super_headers).json()['description'],'Keep')
        response=self.client.put(path,json={'name':'Replaced'},headers=self.super_headers)
        self.assertEqual(response.status_code,200)
        self.assertIsNone(response.json()['description'])
        self.assertEqual(self.client.put(path,json={'description':'missing required name'},headers=self.super_headers).status_code,422)
        for field in ('id_app_user','role','id_plan','id_platform','created_at','prefix_platform'):
            self.assertEqual(self.client.patch(path,json={field:'forbidden'},headers=self.super_headers).status_code,422)
        self.assertEqual(self.client.patch(path,json={'name':None},headers=self.super_headers).status_code,422)
        self.assertEqual(self.client.patch(path,json={'url':None},headers=self.super_headers).status_code,200)

    def test_05_reserved_plan_and_audit_version_linkage(self):
        _,administrator=self.account('administrator')
        response=self.client.get('/installation/plan',headers=self.super_headers)
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['plan_number'],1)
        self.assertEqual(response.json()['name'],'Basic (Plan 1: Database + API Integration)')
        for headers in (administrator,self.super_headers):
            self.assertEqual(self.client.put('/installation/plan',json={'id_plan':response.json()['id_plan']},headers=headers).status_code,405)
        self.assertNotIn('put',self.client.get('/openapi.json').json()['paths']['/installation/plan'])
        for path in ('/plan','/installation_plan','/super_administrator','/role','/foundation_migration','/api_user_credential'):
            self.assertEqual(self.client.post(path,json={'id_plan':response.json()['id_plan']},headers=administrator).status_code,404)
        with self.store.transaction() as session:
            evidence=session.execute('SELECT a.id_api_user,a.id_app_user,v.version_number FROM {api_audit_log} a JOIN {record_version} v USING(id_api_audit_log) WHERE a.resource=%s AND a.target_id=%s',('installation_plan',response.json()['id_installation_plan'])).fetchone()
            self.assertIsNotNone(evidence['id_api_user'])
            self.assertIsNotNone(evidence['id_app_user'])

    def test_06_deny_precedes_allow_and_allow_does_not_grant(self):
        target,headers=self.account('user',permissions=['work:read'])
        body={'id_api_user':target['id_api_user'],'rule_kind':'allow','resource':'work','action':'read'}
        self.assertEqual(self.client.post('/access-rules',json=body,headers=self.super_headers).status_code,201)
        self.assertEqual(self.client.get('/work',headers=headers).status_code,200)
        body['rule_kind']='deny'
        denial=self.client.post('/access-rules',json=body,headers=self.super_headers)
        self.assertEqual(denial.status_code,201)
        self.assertEqual(self.client.get('/work',headers=headers).status_code,403)
        self.assertEqual(self.client.delete('/access-rules/'+denial.json()['id_access_rule'],headers=self.super_headers).status_code,204)
        self.assertEqual(self.client.get('/work',headers=headers).status_code,200)
        other,headers=self.account('user')
        body.update(id_api_user=other['id_api_user'],rule_kind='allow')
        self.assertEqual(self.client.post('/access-rules',json=body,headers=self.super_headers).status_code,201)
        self.assertEqual(self.client.get('/work',headers=headers).status_code,403)

    def test_07_settings_limits_batches_and_openapi(self):
        self.assertEqual(self.client.put('/settings/batch_items',json={'value':301},headers=self.super_headers).status_code,422)
        self.assertEqual(self.client.put('/settings/batch_items',json={'value':2},headers=self.super_headers).status_code,200)
        batch=[{'value':'one'},{'value':'two'},{'value':'three'}]
        self.assertEqual(self.client.post('/test',json=batch,headers=self.super_headers).status_code,422)
        self.assertEqual(self.client.post('/test',json=batch[:2],headers=self.super_headers).status_code,201)
        spec=self.client.get('/openapi.json').json()
        self.assertIn('clientCredentials',spec['components']['securitySchemes']['OAuth2']['flows'])
        self.assertIn('patch',spec['paths']['/work/{identifier}'])
        self.assertNotIn('/api_user_credential',spec['paths'])
        self.assertEqual(self.client.post('/platform',content='{"name":"one","name":"two"}',headers={**self.super_headers,'Content-Type':'application/json'}).status_code,422)

    def test_08_real_container_runtime_on_approved_api_port(self):
        with socket.socket() as probe:
            if probe.connect_ex(('127.0.0.1',6969))==0:
                self.skipTest('Approved API port 6969 is occupied; existing service preserved')
        fixture=self.harness.fixture
        (fixture/'modules/api').mkdir(parents=True,exist_ok=True)
        (fixture/'modules/api/config.jsonc').write_text(json.dumps(self.settings),encoding='utf-8')
        (fixture/'provisioning.jsonc').write_text(json.dumps(self.harness.document),encoding='utf-8')
        from api.service.launcher import protected_file
        password=protected_file(fixture,'api_sql_password')
        password.write_text(self.runtime_password,encoding='utf-8')
        signing=protected_file(fixture,'api_token_signing_key')
        signing.write_text(self.key,encoding='utf-8')
        cert,key=certificate(fixture)
        context=ssl.create_default_context(cafile=str(cert))
        context.verify_flags |= ssl.VERIFY_X509_PARTIAL_CHAIN
        name='ouroboros-api-qa-'+uuid.uuid4().hex[:12]
        for mounts in ([],['--mount',f'type=bind,source={cert},target=/run/secrets/api_tls_certificate,readonly']):
            failed=subprocess.run(['docker','run','--rm',*mounts,'ouroboros-api-v1:verification'],
                                  capture_output=True,text=True,timeout=30)
            self.assertNotEqual(failed.returncode,0)
            self.assertIn('Valid TLS certificate and matching unencrypted PEM key are required',failed.stderr)
        command=['docker','run','--detach','--name',name,'--read-only','--tmpfs','/tmp','--cap-drop','ALL',
                 '--network',self.harness.project+'_default','--publish','127.0.0.1:6969:8000']
        for source,target in ((fixture/'modules/api/config.jsonc','/runtime/api/config.jsonc'),
                              (fixture/'provisioning.jsonc','/runtime/provisioning.jsonc'),
                              (password,'/run/secrets/api_sql_password'),(signing,'/run/secrets/api_token_signing_key'),
                              (cert,'/run/secrets/api_tls_certificate'),(key,'/run/secrets/api_tls_private_key')):
            command.extend(['--mount',f'type=bind,source={source},target={target},readonly'])
        command.append('ouroboros-api-v1:verification')
        try:
            result=subprocess.run(command,capture_output=True,timeout=30)
            self.assertEqual(result.returncode,0,'Owned API container could not be started')
            ready=False
            for _ in range(30):
                try:
                    with urllib.request.urlopen('https://localhost:6969/health',context=context,timeout=2) as response:
                        ready=json.load(response).get('status')=='ready'
                    if ready:
                        break
                except Exception:
                    time.sleep(0.3)
            self.assertTrue(ready,'Owned API container did not become ready; private diagnostics suppressed')
            with urllib.request.urlopen('https://localhost:6969/openapi.json',context=context,timeout=5) as response:
                spec=json.load(response)
                self.assertEqual(spec['info']['title'],'Ouroboros API')
                self.assertEqual(spec['servers'][0]['url'],'https://localhost:6969')
                self.assertEqual(spec['components']['securitySchemes']['OAuth2']['flows']['clientCredentials']['tokenUrl'],
                                 'https://localhost:6969/oauth/token')
            for path in ('/health','/docs','/openapi.json','/oauth/token'):
                with self.assertRaises(Exception):
                    urllib.request.urlopen('http://localhost:6969'+path,timeout=3)
            with urllib.request.urlopen('https://localhost:6969/docs',context=context,timeout=5) as response:
                self.assertIn(b'SwaggerUIBundle',response.read())
            credentials,_=self.account('user')
            from urllib.parse import urlencode
            body=urlencode({'grant_type':'client_credentials','client_id':credentials['client_id'],
                            'client_secret':credentials['client_secret']}).encode()
            with urllib.request.urlopen('https://localhost:6969/oauth/token',data=body,context=context,timeout=5) as response:
                self.assertIn('access_token',json.load(response))
        finally:
            cleanup=subprocess.run(['docker','rm','--force',name],capture_output=True,timeout=30)
            self.assertEqual(cleanup.returncode,0,'Owned API container cleanup failed')

    def test_09_atomic_rollback_ordering_and_account_deactivation(self):
        administrator,headers=self.account('administrator')
        self.assertEqual(self.client.patch('/api-users/'+administrator['id_api_user'],json={'is_active':False},headers=self.super_headers).status_code,200)
        self.assertEqual(self.client.get('/api-users',headers=headers).status_code,401)
        first=self.client.post('/work_classification',json={'name':'first_qa','display_name':'First'},headers=self.super_headers)
        second=self.client.post('/work_classification',json={'name':'second_qa','display_name':'Second','tier':1},headers=self.super_headers)
        self.assertEqual(first.status_code,201)
        self.assertEqual(second.status_code,201)
        identifier=first.json()['id_work_classification']
        moved=self.client.patch('/work_classification/'+identifier,json={'tier':1},headers=self.super_headers)
        self.assertEqual(moved.status_code,200)
        self.assertEqual(moved.json()['tier'],1)
        before=self.client.get('/platform',headers=self.super_headers).json()['total']
        invalid=[{'name':'rollback one'},{'name':'rollback two','is_paid':'not a boolean'}]
        self.assertEqual(self.client.post('/platform',json=invalid,headers=self.super_headers).status_code,422)
        self.assertEqual(self.client.get('/platform',headers=self.super_headers).json()['total'],before)

    def test_10_permission_assignment_and_privilege_hardening(self):
        target,headers=self.account('user')
        response=self.client.put('/api-users/'+target['id_api_user']+'/permissions',json={'permissions':['work:read']},headers=self.super_headers)
        self.assertEqual(response.status_code,200)
        self.assertEqual(self.client.get('/user_work',headers=headers).status_code,401)
        renewed=self.client.post('/oauth/token',data={'grant_type':'client_credentials','client_id':target['client_id'],'client_secret':target['client_secret']})
        self.assertEqual(renewed.status_code,200)
        headers={'Authorization':'Bearer '+renewed.json()['access_token']}
        self.assertEqual(self.client.get('/work',headers=headers).status_code,200)
        with self.store.transaction() as session:
            count=session.execute("SELECT count(*) AS count FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace CROSS JOIN LATERAL aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) a WHERE n.nspname=%s AND a.grantee=0",(self.harness.document['schema'],)).fetchone()['count']
            self.assertEqual(count,0)

    def test_12_human_aliases_and_nonbasic_errors(self):
        identities=[]
        for login in ('qa_app_operator','qa_operator'):
            response=self.client.post('/auth/user-token',json={'username':login,'password':self.harness.app_password})
            self.assertEqual(response.status_code,200)
            headers={'Authorization':'Bearer '+response.json()['access_token']}
            first=self.client.get('/me',headers=headers)
            second=self.client.get('/installation/plan',headers=headers)
            self.assertEqual(first.status_code,200)
            self.assertEqual(second.status_code,200)
            identities.append(first.json())
        self.assertEqual(identities[0],identities[1])
        self.assertEqual(identities[0]['kind'],'human_password')
        for login in ('qa_app_operator','qa_operator','QA Operator'):
            response=self.client.post('/auth/user-token',json={'username':login,'password':'invalid-test-password'})
            self.assertEqual(response.status_code,401)
            self.assertEqual(response.headers.get('WWW-Authenticate'),'Bearer')
        response=self.client.post('/auth/user-token',json={'username':'QA Operator','password':self.harness.app_password})
        self.assertEqual(response.status_code,401)
        response=self.client.post('/oauth/token',data={'grant_type':'client_credentials','client_id':'invalid','client_secret':'invalid'})
        self.assertEqual(response.status_code,401)
        self.assertNotIn('Basic',response.headers.get('WWW-Authenticate',''))
        credentials,_=self.account()
        rejected=self.client.post('/oauth/token',data={'grant_type':'client_credentials','client_id':credentials['client_id'],'client_secret':self.harness.app_password})
        self.assertEqual(rejected.status_code,401)
        import base64
        basic=base64.b64encode((credentials['client_id']+':'+credentials['client_secret']).encode()).decode()
        response=self.client.post('/oauth/token',data={'grant_type':'client_credentials'},headers={'Authorization':'Basic '+basic})
        self.assertEqual(response.status_code,200)

    def test_13_swagger_authorization_assets_and_labels(self):
        html=self.client.get('/docs')
        self.assertEqual(html.status_code,200)
        self.assertIn('/docs/assets/vendor/swagger-ui-bundle.js',html.text)
        self.assertIn('OuroborosAuthPlugin',html.text)
        script=self.client.get('/docs/assets/authorize.js')
        self.assertEqual(script.status_code,200)
        self.assertIn('Human Access Token',script.text)
        self.assertIn('OAuth2 Client Credentials',script.text)
        spec=self.client.get('/openapi.json').json()
        fields=spec['components']['schemas']['HumanToken']['properties']
        self.assertEqual(fields['username']['title'],'App User or linked API User')
        self.assertEqual(fields['password']['title'],'App Password')
        self.assertEqual(spec['components']['schemas']['AccountCreate']['properties']['username']['title'],'API User username')

    def test_14_human_alias_collision_and_expired_links_deny(self):
        from api.service.auth import HASHER
        first,_=self.account()
        second,_=self.account()
        with runtime.connect(self.harness.fixture,self.harness.document,self.harness.operational) as connection:
            for account,app_name in ((first,second['id_api_user']), (second,'unique_app_'+uuid.uuid4().hex[:8])):
                connection.execute(render('UPDATE {app_user} p SET username=%s FROM {app_user_api} l WHERE p.id_app_user=l.id_app_user AND l.id_api_user=%s',self.harness.document),(app_name,account['id_api_user']))
                connection.execute(render("INSERT INTO {api_user_credential}(id_api_user,credential_kind,secret_hash) VALUES(%s,'human_password',%s)",self.harness.document),(account['id_api_user'],HASHER.hash(self.harness.app_password)))
            second_api=connection.execute(render('SELECT username FROM {api_user} WHERE id_api_user=%s',self.harness.document),(second['id_api_user'],)).fetchone()[0]
            connection.execute(render('UPDATE {app_user} p SET username=%s FROM {app_user_api} l WHERE p.id_app_user=l.id_app_user AND l.id_api_user=%s',self.harness.document),(second_api,first['id_api_user']))
        response=self.client.post('/auth/user-token',json={'username':second_api,'password':self.harness.app_password})
        self.assertEqual(response.status_code,401)
        with runtime.connect(self.harness.fixture,self.harness.document,self.harness.operational) as connection:
            first_api=connection.execute(render('SELECT username FROM {api_user} WHERE id_api_user=%s',self.harness.document),(first['id_api_user'],)).fetchone()[0]
        valid=self.client.post('/auth/user-token',json={'username':first_api,'password':self.harness.app_password})
        self.assertEqual(valid.status_code,200)
        human_headers={'Authorization':'Bearer '+valid.json()['access_token']}
        with runtime.connect(self.harness.fixture,self.harness.document,self.harness.operational) as connection:
            connection.execute(render('UPDATE {app_user_api} SET valid_until=clock_timestamp() WHERE id_api_user=%s',self.harness.document),(first['id_api_user'],))
        self.assertEqual(self.client.post('/auth/user-token',json={'username':first_api,'password':self.harness.app_password}).status_code,401)
        self.assertEqual(self.client.get('/me',headers=human_headers).status_code,401)

    def test_15_legacy_human_alias_backfill_preserves_credentials(self):
        from api.service.auth import HASHER
        account,_=self.account()
        legacy_name='legacy_app_'+uuid.uuid4().hex[:8]
        with runtime.connect(self.harness.fixture,self.harness.document,self.harness.operational) as connection:
            connection.execute(render('UPDATE {app_user} p SET personal_name=%s FROM {app_user_api} l WHERE p.id_app_user=l.id_app_user AND l.id_api_user=%s',self.harness.document),(legacy_name,account['id_api_user']))
            connection.execute(render("INSERT INTO {api_user_credential}(id_api_user,credential_kind,secret_hash) VALUES(%s,'human_password',%s)",self.harness.document),(account['id_api_user'],HASHER.hash(self.harness.app_password)))
            before=connection.execute(render("SELECT id_api_user_credential,secret_hash FROM {api_user_credential} WHERE id_api_user=%s AND credential_kind='human_password'",self.harness.document),(account['id_api_user'],)).fetchone()
            source=(test_postgres.ROOT/'modules/database/sql/upgrades/003_app_username.sql').read_text(encoding='utf-8')
            connection.execute(render('WITH candidates'+source.split('WITH candidates',1)[1],self.harness.document))
            after=connection.execute(render("SELECT id_api_user_credential,secret_hash FROM {api_user_credential} WHERE id_api_user=%s AND credential_kind='human_password'",self.harness.document),(account['id_api_user'],)).fetchone()
            self.assertTrue(before==after,'Legacy credential identity or hash changed')
        response=self.client.post('/auth/user-token',json={'username':legacy_name,'password':self.harness.app_password})
        self.assertEqual(response.status_code,200)

    def test_16_human_aliases_share_the_account_rate_limit(self):
        with TestClient(create_app(self.store,self.key)) as client:
            for attempt in range(10):
                login=('qa_app_operator','qa_operator')[attempt%2]
                self.assertEqual(client.post('/auth/user-token',json={'username':login,'password':'invalid-test-password'}).status_code,401)
            rejected=client.post('/auth/user-token',json={'username':'qa_app_operator','password':self.harness.app_password})
            self.assertEqual(rejected.status_code,429)
            self.assertIn('Retry-After',rejected.headers)


    def test_11_combined_compose_start_and_restart(self):
        from api.service import launcher
        from api.service.config import ROOT
        with socket.socket() as probe:
            if probe.connect_ex(('127.0.0.1',6969))==0:
                self.skipTest('Approved port is occupied; existing service preserved')
        fixture=self.harness.fixture
        settings=copy.deepcopy(self.settings)
        cert,key=certificate(fixture)
        settings['tls'].update(certificate_file=str(cert),private_key_file=str(key))
        (fixture/'modules/api/config.jsonc').write_text(json.dumps(settings),encoding='utf-8')
        (fixture/'provisioning.jsonc').write_text(json.dumps(self.harness.document),encoding='utf-8')
        source=(ROOT/'modules/api/compose.yaml').read_text(encoding='utf-8')
        (fixture/'modules/api/compose.yaml').write_text(source.replace('context: ../..','context: '+ROOT.as_posix()),encoding='utf-8')
        launcher.protected_file(fixture,'api_sql_password').write_text(self.runtime_password,encoding='utf-8')
        launcher.protected_file(fixture,'api_token_signing_key').write_text(self.key,encoding='utf-8')
        context=ssl.create_default_context(cafile=str(cert))
        context.verify_flags |= ssl.VERIFY_X509_PARTIAL_CHAIN
        plan_before=None
        for attempt in range(2):
            with patch.object(runtime,'PROJECT',self.harness.project),patch.object(runtime,'prepare',return_value=(self.harness.document,self.harness.operational)),patch.object(runtime,'prepare_initial',return_value=(self.harness.document,self.harness.operational)),patch('builtins.input',side_effect=AssertionError('Unexpected bootstrap')):
                self.assertEqual(launcher.main(fixture,['--with-api']),0)
            request=urllib.request.Request('https://localhost:6969/auth/user-token',
                data=json.dumps({'username':'qa_operator','password':self.harness.app_password}).encode(),
                headers={'Content-Type':'application/json'})
            with urllib.request.urlopen(request,context=context,timeout=5) as response:
                token=json.load(response)['access_token']
            request=urllib.request.Request('https://localhost:6969/installation/plan',headers={'Authorization':'Bearer '+token})
            with urllib.request.urlopen(request,context=context,timeout=5) as response:
                plan=json.load(response)
            self.assertEqual(plan['name'],'Basic (Plan 1: Database + API Integration)')
            if attempt:
                self.assertEqual(plan,plan_before)
            plan_before=plan


if __name__=='__main__':
    unittest.main()
