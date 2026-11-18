"""Sympla-style RBAC on the actual restricted SQL login and disposable database."""
import unittest
import uuid
from fastapi.testclient import TestClient
from psycopg import sql
from api.qa import test_service
from api.service.app import create_app
from api.service import rbac
from database.model import render
from database import runtime


class ScopedRBACTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base=test_service.APITests
        cls.base.setUpClass()
        cls.store=cls.base.store

    @classmethod
    def tearDownClass(cls):
        cls.base.tearDownClass()

    def setUp(self):
        self.client=TestClient(create_app(self.store,self.base.key),raise_server_exceptions=False)
        token=self.client.post('/auth/user-token',json={'username':'qa_operator','password':self.base.harness.app_password})
        self.assertEqual(token.status_code,200)
        self.master={'Authorization':'Bearer '+token.json()['access_token']}

    def tearDown(self):
        self.client.close()

    def role(self,permissions,headers=None):
        response=self.client.post('/roles',json={'name':'qa_'+uuid.uuid4().hex[:12],'permissions':permissions},headers=headers or self.master)
        self.assertEqual(response.status_code,201,response.text)
        return response.json()

    def account(self,permissions,person=False):
        role=self.role(permissions)
        body={'username':'qa_'+uuid.uuid4().hex[:12],'role_identifier':role['identifier']}
        if person:
            body['app_user_name']='Disposable QA Person'
        response=self.client.post('/api-users',json=body,headers=self.master)
        self.assertEqual(response.status_code,201,response.text)
        account=response.json()
        return role,account,self.login(account)

    def login(self,account,scope=None):
        body={'grant_type':'client_credentials','client_id':account['client_id'],'client_secret':account['client_secret']}
        if scope is not None:body['scope']=scope
        response=self.client.post('/oauth/token',data=body)
        self.assertEqual(response.status_code,200)
        return {'Authorization':'Bearer '+response.json()['access_token']}

    def test_catalogue_openapi_and_zero_grant_authentication(self):
        response=self.client.get('/permissions',headers=self.master)
        self.assertEqual(response.status_code,200)
        self.assertEqual({row['code'] for row in response.json()['items']},{section+':'+action for section in rbac.SECTIONS for action in rbac.PUBLIC_ACTIONS})
        _,account,headers=self.account([])
        self.assertEqual(self.client.get('/me',headers=headers).status_code,200)
        denied=self.client.get('/permissions',headers=headers)
        self.assertEqual(denied.status_code,403)
        self.assertEqual(denied.json()['error']['required_permission'],'authorization:read')
        schema=self.client.get('/openapi.json').json()['paths']
        self.assertEqual(schema['/roles']['post']['x-required-permission'],'roles:write')
        self.assertEqual(schema['/platform/{identifier}']['patch']['x-required-permission'],'catalogue:edit')
        self.assertNotIn('x-required-permission',schema['/auth/user-token']['post'])

    def test_independent_read_write_edit_delete(self):
        _,_,write=self.account(['catalogue:write'])
        created=self.client.post('/platform',json={'name':'Disposable'},headers=write)
        self.assertEqual(created.status_code,201)
        identifier=created.json()['id_platform']
        self.assertEqual(self.client.get('/platform',headers=write).status_code,403)
        self.assertEqual(self.client.patch('/platform/'+identifier,json={'name':'No'},headers=write).status_code,403)
        _,_,read=self.account(['catalogue:read'])
        self.assertEqual(self.client.get('/platform/'+identifier,headers=read).status_code,200)
        self.assertEqual(self.client.post('/platform',json={'name':'No'},headers=read).status_code,403)
        _,_,edit=self.account(['catalogue:edit'])
        self.assertEqual(self.client.patch('/platform/'+identifier,json={'name':'Edited'},headers=edit).status_code,200)
        self.assertEqual(self.client.delete('/platform/'+identifier,headers=edit).status_code,403)
        _,_,delete=self.account(['catalogue:delete'])
        self.assertEqual(self.client.delete('/platform/'+identifier,headers=delete).status_code,204)

    def test_delegation_cannot_escalate_or_replace_more_privileged_role(self):
        _,_,delegate=self.account(['identity:write','roles:write','roles:edit','catalogue:read'])
        role=self.role(['catalogue:read'],delegate)
        created=self.client.post('/api-users',json={'username':'delegated_'+uuid.uuid4().hex[:8],'role_identifier':role['identifier']},headers=delegate)
        self.assertEqual(created.status_code,201)
        response=self.client.post('/roles',json={'name':'Denied_'+uuid.uuid4().hex[:8],'permissions':['identity:edit']},headers=delegate)
        self.assertEqual(response.status_code,403)
        stronger=self.role(['catalogue:edit'])
        self.assertEqual(self.client.put('/roles/'+stronger['identifier']+'/permissions',json={'permissions':[]},headers=delegate).status_code,403)
        self.assertEqual(self.client.post('/api-users',json={'username':'no_'+uuid.uuid4().hex[:8],'role_identifier':stronger['identifier']},headers=delegate).status_code,403)

    def test_role_permissions_and_direct_grants_revoke_tokens(self):
        role,account,headers=self.account(['catalogue:read'])
        response=self.client.put('/roles/'+role['identifier']+'/permissions',json={'permissions':['catalogue:read','catalogue:write']},headers=self.master)
        self.assertEqual(response.status_code,200)
        self.assertEqual(self.client.get('/me',headers=headers).status_code,401)
        headers=self.login(account)
        changed=self.client.put('/api-users/'+account['id_api_user']+'/permissions',json={'permissions':['authorization:read']},headers=self.master)
        self.assertEqual(changed.status_code,200)
        self.assertEqual(self.client.get('/me',headers=headers).status_code,401)
        headers=self.login(account)
        self.assertEqual(self.client.get('/permissions',headers=headers).status_code,200)
        metadata=self.client.get('/api-users/'+account['id_api_user'],headers=self.master).json()
        self.assertEqual(metadata['role_identifier'],role['identifier'])
        self.assertIn('authorization:read',metadata['individual_permissions'])
        self.assertIn('catalogue:read',metadata['permissions'])

    def test_system_roles_references_and_soft_delete_protect_history(self):
        roles=self.client.get('/roles',headers=self.master).json()['items']
        system=next(role for role in roles if role['is_system'])
        self.assertEqual(self.client.delete('/roles/'+system['identifier'],headers=self.master).status_code,403)
        role,account,headers=self.account(['catalogue:read'])
        self.assertEqual(self.client.delete('/roles/'+role['identifier'],headers=self.master).status_code,409)
        self.assertEqual(self.client.delete('/api-users/'+account['id_api_user'],headers=self.master).status_code,204)
        self.assertEqual(self.client.get('/me',headers=headers).status_code,401)
        self.assertEqual(self.client.patch('/api-users/'+account['id_api_user'],json={'is_active':True},headers=self.master).status_code,409)
        self.assertEqual(self.client.get('/api-users/'+account['id_api_user'],headers=self.master).status_code,404)
        master_id=self.client.get('/me',headers=self.master).json()['id_api_user']
        self.assertEqual(self.client.delete('/api-users/'+master_id,headers=self.master).status_code,403)

    def test_narrow_token_cannot_delegate_and_personal_data_stays_owned(self):
        _,account,_=self.account(['roles:write','catalogue:read'])
        restricted=self.login(account,'roles:write')
        denied=self.client.post('/roles',json={'name':'no_'+uuid.uuid4().hex[:8],'permissions':['catalogue:read']},headers=restricted)
        self.assertEqual(denied.status_code,403)
        _,first,a=self.account(['personal:read','personal:write'],True)
        _,second,b=self.account(['personal:read','personal:write'],True)
        created=self.client.post('/tag',json={'name':'private_'+uuid.uuid4().hex[:8],'display_name':'Private'},headers=a)
        self.assertEqual(created.status_code,201)
        self.assertEqual(self.client.get('/tag/'+created.json()['id_tag'],headers=b).status_code,404)

    def test_deny_rules_override_section_grants(self):
        _,account,headers=self.account(['catalogue:read'])
        response=self.client.post('/access-rules',json={'id_api_user':account['id_api_user'],'rule_kind':'deny','resource':'platform','action':'read'},headers=self.master)
        self.assertEqual(response.status_code,201)
        self.assertEqual(self.client.get('/platform',headers=headers).status_code,403)
        self.assertEqual(self.client.get('/work',headers=headers).status_code,200)

    def test_permission_validation_and_audit_are_atomic(self):
        for permissions in (['catalogue:read','catalogue:read'],['admin'],['installation_plan:edit']):
            response=self.client.post('/roles',json={'name':'invalid','permissions':permissions},headers=self.master)
            self.assertEqual(response.status_code,422)
        role=self.role(['catalogue:read'])
        self.assertEqual(self.client.patch('/roles/'+role['identifier'],json={'is_system':True},headers=self.master).status_code,422)
        with runtime.connect(self.base.harness.fixture,self.base.harness.document,self.base.harness.operational) as connection:
            count=connection.execute(render('SELECT count(*) FROM {api_audit_log} WHERE resource=\'role\' AND target_id=%s',self.base.harness.document),(role['identifier'],)).fetchone()[0]
            self.assertGreater(count,0)

    def test_individual_grant_lifecycle_and_role_assignment(self):
        role,account,headers=self.account(['catalogue:read'])
        grant=self.client.post('/access-rules',json={'api_user_identifier':account['id_api_user'],'permission':'authorization:read'},headers=self.master)
        self.assertEqual(grant.status_code,201,grant.text)
        self.assertEqual(self.client.get('/me',headers=headers).status_code,401)
        headers=self.login(account)
        self.assertEqual(self.client.get('/permissions',headers=headers).status_code,200)
        other=self.role(['catalogue:write'])
        changed=self.client.put('/api-users/'+account['id_api_user']+'/role',json={'role_identifier':other['identifier']},headers=self.master)
        self.assertEqual(changed.status_code,200,changed.text)
        self.assertIn('authorization:read',changed.json()['individual_permissions'])
        self.assertEqual(self.client.delete('/access-rules/'+grant.json()['identifier'],headers=self.master).status_code,204)
        headers=self.login(account)
        self.assertEqual(self.client.get('/permissions',headers=headers).status_code,403)
        self.assertEqual(self.client.delete('/roles/'+role['identifier'],headers=self.master).status_code,204)

    def test_credentials_cannot_impersonate_a_more_privileged_identity(self):
        _,account,headers=self.account(['identity:edit','identity:delete'])
        _,stronger,_=self.account(['catalogue:read'])
        self.assertEqual(self.client.post('/api-users/'+stronger['id_api_user']+'/credentials',json={},headers=headers).status_code,403)
        # Even an administrator's narrowed token cannot use the legacy profile
        # payload to manufacture an unbounded administrator credential.
        _,administrator,_=self.account(['identity:write','catalogue:read'])
        narrow=self.login(administrator,'identity:write')
        response=self.client.post('/api-users',json={'username':'legacy_'+uuid.uuid4().hex[:8],'role':'user'},headers=narrow)
        self.assertEqual(response.status_code,403)

    def test_audit_failure_rolls_back_custom_role_creation(self):
        h=self.base.harness
        schema=sql.Identifier(h.document['schema'])
        name='rollback_'+uuid.uuid4().hex[:8]
        with runtime.connect(h.fixture,h.document,h.operational) as connection:
            connection.execute(sql.SQL("CREATE FUNCTION {}.qa_reject_role_audit() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW.resource='role' THEN RAISE EXCEPTION 'Synthetic audit outage'; END IF; RETURN NEW; END $$").format(schema))
            connection.execute(sql.SQL('CREATE TRIGGER qa_reject_role_audit BEFORE INSERT ON {}.api_audit_log FOR EACH ROW EXECUTE FUNCTION {}.qa_reject_role_audit()').format(schema,schema))
            try:
                response=self.client.post('/roles',json={'name':name,'permissions':[]},headers=self.master)
                self.assertEqual(response.status_code,503)
                self.assertEqual(connection.execute(render('SELECT count(*) FROM {role} WHERE name=%s',h.document),(name,)).fetchone()[0],0)
            finally:
                connection.execute(sql.SQL('DROP TRIGGER qa_reject_role_audit ON {}.api_audit_log').format(schema))
                connection.execute(sql.SQL('DROP FUNCTION {}.qa_reject_role_audit()').format(schema))


if __name__=='__main__':
    unittest.main()
