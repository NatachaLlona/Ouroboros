"""English HTTP/OpenAPI contract for the registered schema, without UI services."""
import base64
import json
import secrets
from typing import Annotated, Literal
from urllib.parse import parse_qsl
from fastapi import Depends, FastAPI, Form, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.security import OAuth2, HTTPBearer
from fastapi.openapi.models import OAuthFlows as OAuthFlowsModel
from pydantic import Field, SecretStr, model_validator
from psycopg import Error as SQLFailure
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from shared.request_context import create_interaction_id
from api.app.login_throttle import LoginThrottle
from database.settings import ConfigurationError
from api.service.auth import Authentication, HASHER, denied, require
from api.service.resources import APPEND_ONLY, SPECS, StrictBody, Text, Boolean, schemas
from api.service import repository
from api.service.tls import origin
from api.service.swagger import install as install_swagger
from api.service import rbac
from api.service.authorization import Permissions, install as install_authorization, mutate, account_data


class HumanToken(StrictBody):
    username: Annotated[str,Field(strict=True,min_length=1,max_length=128,title='App User or linked API User')]
    password: SecretStr = Field(title='App Password')


class AccountCreate(StrictBody):
    username: Annotated[str,Field(strict=True,min_length=1,max_length=128,pattern=r'^[A-Za-z0-9._@-]+$',title='API User username')]
    role: Literal['user','manager','administrator'] | None=None
    role_identifier: Text | None=None
    app_user_name: Annotated[str,Field(strict=True,min_length=1,max_length=256,title='App Display Name')] | None=None
    permissions: list[Annotated[str,Field(max_length=100)]]=Field(default_factory=list,max_length=128)

    @model_validator(mode='after')
    def role_choice(self):
        if (self.role is None)==(self.role_identifier is None):
            raise ValueError('Choose role_identifier or the legacy role profile')
        rbac.codes(self.permissions)
        return self


class RoleReplacement(StrictBody):
    role: Literal['user','manager','administrator'] | None=None
    role_identifier: Text | None=None

    @model_validator(mode='after')
    def role_choice(self):
        if (self.role is None)==(self.role_identifier is None):
            raise ValueError('Choose one role representation')
        return self


class ActiveReplacement(StrictBody):
    is_active: Boolean


class PermissionReplacement(Permissions):
    pass


class SettingReplacement(StrictBody):
    value: Annotated[int,Field(strict=True)]


class RuleCreate(StrictBody):
    id_api_user: Text | None=None
    rule_kind: Literal['allow','deny'] | None=None
    resource: Text | None=None
    action: Literal['create','read','update','delete','write','edit'] | None=None
    api_user_identifier: Text | None=None
    permission: Text | None=None

    @model_validator(mode='after')
    def rule_choice(self):
        if self.permission is not None or self.api_user_identifier is not None:
            if self.permission is None or self.api_user_identifier is None or any(value is not None for value in (self.id_api_user,self.rule_kind,self.resource,self.action)):
                raise ValueError('Choose an individual grant or an allow/deny restriction')
            rbac.internal(self.permission)
        elif self.rule_kind is None or self.resource is None or self.action is None:
            raise ValueError('Provide all restriction fields')
        return self


def error_response(request,status,message):
    code={400:'VALIDATION_ERROR',401:'AUTHENTICATION_REQUIRED',403:'INSUFFICIENT_PERMISSIONS',
          404:'RESOURCE_NOT_FOUND',405:'METHOD_NOT_ALLOWED',409:'RELATIONSHIP_CONFLICT',
          413:'VALIDATION_ERROR',422:'VALIDATION_ERROR',429:'REQUEST_LIMIT_EXCEEDED',503:'DATABASE_UNAVAILABLE'}.get(status,'INTERNAL_ERROR')
    required=message.get('required_permission') if isinstance(message,dict) else None
    message=message.get('message','Permission denied') if isinstance(message,dict) else message
    error={'code':code,'message':message,'interaction_id':getattr(request.state,'interaction_id','')}
    if required:
        error['required_permission']=required
    return JSONResponse({'error':error},status_code=status)


class SafetyMiddleware:
    """Bound bodies, reject duplicates and omit all request/response body logging."""
    def __init__(self,app,limit):
        self.app,self.limit=app,limit

    async def __call__(self,scope,receive,send):
        if scope['type']!='http':
            return await self.app(scope,receive,send)
        interaction=create_interaction_id()
        scope.setdefault('state',{})['interaction_id']=interaction
        query=parse_qsl(scope.get('query_string',b'').decode('ascii',errors='replace'),keep_blank_values=True)
        if (any(key not in {'page','page_size','id'} for key,_ in query)
            or len({key for key,_ in query})!=len(query)
            or (query and scope['method']!='GET')):
            response=error_response(Request(scope),422,'Unknown, duplicate or unsupported query parameter')
            return await response(scope,receive,send)
        body=bytearray()
        while True:
            message=await receive()
            if message['type']=='http.disconnect':
                return
            body.extend(message.get('body',b''))
            if len(body)>self.limit:
                response=error_response(Request(scope),413,'Request body exceeds the permitted limit')
                return await response(scope,receive,send)
            if not message.get('more_body',False):
                break
        def unique(pairs):
            result={}
            for key,value in pairs:
                if key in result:
                    raise ValueError
                result[key]=value
            return result
        content=dict(scope['headers']).get(b'content-type',b'').split(b';')[0]
        try:
            if body and content==b'application/json':
                json.loads(body,object_pairs_hook=unique,parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
            elif body and content==b'application/x-www-form-urlencoded':
                unique(parse_qsl(body.decode(),keep_blank_values=True,strict_parsing=True))
        except (ValueError,UnicodeError):
            response=error_response(Request(scope),422,'Malformed input or duplicate fields')
            return await response(scope,receive,send)
        delivered=False
        async def replay():
            nonlocal delivered
            if not delivered:
                delivered=True
                return {'type':'http.request','body':bytes(body),'more_body':False}
            return await receive()
        async def safe_send(message):
            if message['type']=='http.response.start':
                message={**message,'headers':[*message.get('headers',[]),(b'x-interaction-id',interaction.encode()),
                                             (b'cache-control',b'no-store'),(b'x-content-type-options',b'nosniff')]}
            await send(message)
        await self.app(scope,replay,safe_send)


def create_app(store,key):
    settings=store.settings
    authentication=Authentication(settings,store.document,key)
    throttle=LoginThrottle()
    app=FastAPI(title='Ouroboros API',version='1.0.0',docs_url=None,servers=[{'url':origin(settings)}],description='Database v1 API over HTTPS. Use Authorize for Human Access Token or OAuth2 Client Credentials. PUT replaces the full editable representation; PATCH preserves omitted fields.')
    install_swagger(app)
    app.add_middleware(SafetyMiddleware,limit=settings['limits']['request_bytes']['value'])
    oauth=OAuth2(flows=OAuthFlowsModel(clientCredentials={'tokenUrl':origin(settings)+'/oauth/token','scopes':{}}),auto_error=False,description='OAuth2 Client Credentials. Client ID is the provisioned credential ID. Client Secret is its integration secret.')
    human_bearer=HTTPBearer(auto_error=False,scheme_name='HumanBearer',description='App User authentication. Paste a Human Access Token or sign in through Authorize using your App User or linked API User username and App Password.')

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request,error):
        response=error_response(request,error.status_code,error.detail)
        response.headers.update(error.headers or {})
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(request,error):
        return error_response(request,422,'Unknown, missing or invalid request fields')

    @app.exception_handler(ConfigurationError)
    async def configuration_error(request,error):
        return error_response(request,503,str(error))

    @app.exception_handler(SQLFailure)
    async def sql_error(request,error):
        code=getattr(error,'sqlstate','') or ''
        status=403 if code=='42501' else 409 if code in ('23503','23505') else 422 if code.startswith(('22','23')) else 503
        return error_response(request,status,{403:'Permission denied',409:'Record conflicts with an existing relationship',422:'Record violates the data contract',503:'Database operation unavailable'}[status])

    @app.exception_handler(Exception)
    async def unexpected(request,error):
        return error_response(request,500,'Internal operation failed')

    def context(request:Request,authorization=Depends(oauth),human=Depends(human_bearer)):
        if not authorization or authorization.partition(' ')[0].lower()!='bearer':
            raise HTTPException(401,'Bearer authentication required',headers={'WWW-Authenticate':'Bearer'})
        with store.transaction() as session:
            # One installation membership lock serializes authority transitions with mutations.
            session.execute('SELECT pg_advisory_xact_lock(719230818)')
            actor=authentication.authenticate(session,authorization[7:])
            session.limits()
            yield session,actor

    def token_operation(identifier,password,kind,scope,address):
        with store.transaction() as session:
            session.execute('SELECT pg_advisory_xact_lock(719230818)')
            rows=session.function('api_credential',identifier,kind).fetchall()
            record=rows[0] if len(rows)==1 else None
            rate_identity='actor:'+record['actor'] if record else 'login:'+identifier
            retry=throttle.admit(rate_identity,address)
            if retry:
                raise HTTPException(429,'Authentication attempt limit reached',headers={'Retry-After':str(retry)})
            return authentication.token(session,record,password,kind,scope)

    @app.post('/oauth/token',tags=['Authentication'],summary='Issue an integration token using OAuth 2.0 Client Credentials')
    async def client_token(request:Request,grant_type:Annotated[str,Form(title='OAuth2 Grant Type')],client_id:Annotated[str|None,Form(title='Client ID')]=None,
                           client_secret:Annotated[SecretStr|None,Form(title='Client Secret')]=None,scope:Annotated[str,Form(title='Integration scopes')]=''):
        form=await request.form()
        if set(form)-{'grant_type','client_id','client_secret','scope'} or grant_type!='client_credentials':
            raise HTTPException(400,'Only the client_credentials grant is supported')
        authorization=request.headers.get('authorization')
        if authorization:
            if client_id is not None or client_secret is not None or authorization.partition(' ')[0].lower()!='basic':
                raise HTTPException(400,'Use exactly one client authentication method')
            try:
                decoded=base64.b64decode(authorization[6:],validate=True).decode('utf-8')
                client_id,password=decoded.split(':',1)
            except (ValueError,UnicodeError):
                raise HTTPException(401,'Invalid client authentication') from None
        else:
            password=client_secret.get_secret_value() if client_secret else ''
        if not client_id or not password or len(client_id)>128 or len(password)>1024:
            raise HTTPException(401,'Invalid client authentication')
        return await run_in_threadpool(token_operation,client_id,password,'client_credentials',scope,request.client.host)

    @app.post('/auth/user-token',tags=['Authentication'],summary='Authenticate a linked human identity; never a Client Credentials secret')
    def user_token(body:HumanToken,request:Request):
        if len(body.password.get_secret_value())>1024:
            raise HTTPException(401,'Invalid credentials')
        return token_operation(body.username,body.password.get_secret_value(),'human_password','',request.client.host)

    @app.get('/health',tags=['Operations'])
    def health():
        with store.transaction() as session:
            session.execute('SELECT 1')
        return {'status':'ready'}

    @app.get('/me',tags=['Identity'])
    def me(auth=Depends(context,scope='function')):
        session,actor=auth
        return {**account_data(session,actor['id_api_user']),**{field:actor[field] for field in ('id_api_user','username','roles','person','super','kind')}}

    @app.post('/api-users',status_code=201,tags=['Identity'],summary='Create an authorized account and return its new client secret once')
    def create_account(body:AccountCreate,auth=Depends(context,scope='function')):
        session,actor=auth
        require(session,actor,'api_user','create')
        secret=secrets.token_urlsafe(48)
        if body.role_identifier is not None:
            target,credential=mutate(session,'account_create',None,{'username':body.username,'role_identifier':body.role_identifier,'app_user_name':body.app_user_name,'initial_hash':HASHER.hash(secret)}).split(':')
            if body.permissions:
                mutate(session,'account_permissions',target,{'permissions':rbac.codes(body.permissions)})
        else:
            target,credential=next(iter(session.function('api_create_account',body.username,body.role,body.app_user_name,rbac.codes(body.permissions),HASHER.hash(secret)).fetchone().values()))
        return {'id_api_user':target,'client_id':credential,'client_secret':secret}

    @app.get('/api-users',tags=['Identity'])
    def accounts(page:Annotated[int,Query(ge=1)]=1,page_size:Annotated[int,Query(ge=1)]=10,auth=Depends(context,scope='function')):
        session,actor=auth
        require(session,actor,'api_user','read')
        if page_size>session.limits()['page_size']:
            raise HTTPException(422,'Page size exceeds the permitted limit')
        rows=session.execute('SELECT id_api_user FROM {api_user} WHERE deleted_at IS NULL ORDER BY sequence_api_user LIMIT %s OFFSET %s',(page_size,(page-1)*page_size)).fetchall()
        return {'items':[account_data(session,row['id_api_user']) for row in rows]}

    @app.get('/api-users/{identifier}',tags=['Identity'])
    def account(identifier:str,auth=Depends(context,scope='function')):
        session,actor=auth
        require(session,actor,'api_user','read')
        return account_data(session,identifier)

    @app.delete('/api-users/{identifier}',status_code=204,tags=['Identity'],summary='Soft-delete an ordinary API identity and invalidate its tokens')
    def delete_account(identifier:str,auth=Depends(context,scope='function')):
        session,actor=auth
        require(session,actor,'api_user','delete')
        mutate(session,'account_delete',identifier,{})
        return Response(status_code=204)

    @app.put('/api-users/{identifier}/role',tags=['Identity'])
    def assign_role(identifier:str,body:RoleReplacement,auth=Depends(context,scope='function')):
        session,actor=auth
        require(session,actor,'api_user','update')
        if body.role_identifier is not None:
            mutate(session,'account_role',identifier,{'role_identifier':body.role_identifier})
        else:
            session.function('api_assign_role',identifier,body.role)
        return account_data(session,identifier)

    @app.patch('/api-users/{identifier}',tags=['Identity'],summary='Activate or deactivate an ordinary identity, revoking its existing tokens')
    def set_active(identifier:str,body:ActiveReplacement,auth=Depends(context,scope='function')):
        session,actor=auth
        require(session,actor,'api_user','update')
        mutate(session,'account_active',identifier,{'is_active':body.is_active})
        return {'id_api_user':identifier,'is_active':body.is_active}

    @app.put('/api-users/{identifier}/permissions',tags=['Authorization'],summary='Replace individual permission grants without changing the operational profile')
    def assign_permissions(identifier:str,body:PermissionReplacement,auth=Depends(context,scope='function')):
        session,actor=auth
        require(session,actor,'permission_assignment','update')
        mutate(session,'account_permissions',identifier,{'permissions':rbac.codes(body.permissions)})
        return {'id_api_user':identifier,'permissions':body.permissions}

    @app.post('/api-users/{identifier}/credentials',status_code=201,tags=['Identity'])
    def issue_client(identifier:str,body:StrictBody,auth=Depends(context,scope='function')):
        session,actor=auth
        require(session,actor,'api_user','update')
        secret=secrets.token_urlsafe(48)
        credential=mutate(session,'client_issue',identifier,{'initial_hash':HASHER.hash(secret)})
        return {'client_id':credential,'client_secret':secret}

    @app.delete('/credentials/{identifier}',status_code=204,tags=['Identity'])
    def revoke(identifier:str,auth=Depends(context,scope='function')):
        session,actor=auth
        owner=session.function('api_credential',identifier,'client_credentials').fetchone()
        require(session,actor,'api_user','delete')
        if owner is None:
            raise HTTPException(404,'Client credential not found')
        mutate(session,'client_revoke',owner['actor'],{'credential':identifier})
        return Response(status_code=204)

    @app.get('/installation/plan',tags=['Installation'])
    def current_plan(auth=Depends(context,scope='function')):
        session,actor=auth
        if not actor['super'] or actor['kind']!='human_password' or 'installation_plan:read' not in actor['scopes']:
            denied()
        return session.execute('SELECT ip.id_installation_plan,ip.id_plan,p.plan_number,p.name FROM {installation_plan} ip JOIN {plan} p USING(id_plan) WHERE effective_until IS NULL').fetchone()

    @app.get('/settings',tags=['Installation'])
    def settings_read(auth=Depends(context,scope='function')):
        session,actor=auth
        require(session,actor,'operator_setting','read')
        return {'effective':session.limits(),'operator_limits':settings['limits']}

    @app.put('/settings/{name}',tags=['Installation'])
    def settings_replace(name:str,body:SettingReplacement,auth=Depends(context,scope='function')):
        session,actor=auth
        require(session,actor,'operator_setting','update')
        if name not in settings['limits']:
            raise HTTPException(404,'Unknown adjustable setting')
        bounds=settings['limits'][name]
        if not bounds['minimum']<=body.value<=bounds['maximum']:
            raise HTTPException(422,f"{name}: permitted range is {bounds['minimum']}..{bounds['maximum']}")
        session.function('api_set_setting',name,body.value,bounds['minimum'],bounds['maximum'])
        return {'name':name,'value':body.value}

    @app.post('/access-rules',status_code=201,tags=['Authorization'])
    def add_rule(body:RuleCreate,auth=Depends(context,scope='function')):
        session,actor=auth
        require(session,actor,'access_rule','create')
        if body.permission is not None:
            identifier=mutate(session,'permission_add',body.api_user_identifier,{'permissions':[rbac.internal(body.permission)]})
            return {'identifier':identifier,'api_user_identifier':body.api_user_identifier,'permission':rbac.external(rbac.internal(body.permission)),'kind':'grant'}
        if body.resource not in {*SPECS,*rbac.SECTIONS,'*', 'api_user','operator_setting'}:
            raise HTTPException(422,'Unknown or protected rule resource')
        identifier=next(iter(session.function('api_add_rule',body.id_api_user,body.rule_kind,body.resource,rbac.TO_STORAGE[body.action]).fetchone().values()))
        return {'id_access_rule':identifier}

    @app.get('/access-rules',tags=['Authorization'])
    def rules(page:Annotated[int,Query(ge=1)]=1,page_size:Annotated[int,Query(ge=1)]=10,auth=Depends(context,scope='function')):
        session,actor=auth
        require(session,actor,'access_rule','read')
        if page_size>session.limits()['page_size']:
            raise HTTPException(422,'Page size exceeds the permitted limit')
        if actor['super'] or 'administrator' in actor['roles']:
            rows=session.execute('SELECT * FROM {access_rule} ORDER BY sequence_access_rule LIMIT %s OFFSET %s',(page_size,(page-1)*page_size)).fetchall()
        else:
            rows=session.execute('SELECT * FROM {access_rule} WHERE id_api_user=%s ORDER BY sequence_access_rule LIMIT %s OFFSET %s',(actor['id_api_user'],page_size,(page-1)*page_size)).fetchall()
        # Grants and deny/allow restrictions remain explicitly distinguishable.
        grants=session.execute("SELECT rp.id_role_permission AS identifier,ur.id_api_user AS api_user_identifier,p.resource||':'||p.action AS permission FROM {api_user_role} ur JOIN {role} r USING(id_role) JOIN {role_permission} rp USING(id_role) JOIN {permission} p USING(id_permission) WHERE r.name='identity_'||ur.id_api_user AND (%s OR ur.id_api_user=%s) ORDER BY rp.sequence_role_permission LIMIT %s OFFSET %s",(actor['super'] or 'administrator' in actor['roles'],actor['id_api_user'],page_size,(page-1)*page_size)).fetchall()
        return {'items':[{**dict(row),'kind':'restriction'} for row in rows],
                'individual_grants':[{**dict(row),'permission':rbac.external(row['permission']),'kind':'grant'} for row in grants]}

    @app.delete('/access-rules/{identifier}',status_code=204,tags=['Authorization'])
    def remove_rule(identifier:str,auth=Depends(context,scope='function')):
        session,actor=auth
        require(session,actor,'access_rule','delete')
        grant=session.execute("SELECT ur.id_api_user FROM {role_permission} rp JOIN {role} r USING(id_role) JOIN {api_user_role} ur USING(id_role) WHERE rp.id_role_permission=%s AND r.name='identity_'||ur.id_api_user",(identifier,)).fetchone()
        if grant is not None:
            mutate(session,'permission_delete',grant['id_api_user'],{'permission_identifier':identifier})
            return Response(status_code=204)
        session.function('api_remove_rule',identifier)
        return Response(status_code=204)

    @app.get('/audit',tags=['Evidence'])
    def audits(page:Annotated[int,Query(ge=1)]=1,page_size:Annotated[int,Query(ge=1)]=10,auth=Depends(context,scope='function')):
        session,actor=auth
        require(session,actor,'api_audit_log','read')
        if page_size>session.limits()['page_size']:
            raise HTTPException(422,'Page size exceeds the permitted limit')
        if actor['super'] or 'administrator' in actor['roles']:
            rows=session.execute('SELECT * FROM {api_audit_log} ORDER BY sequence_api_audit_log DESC LIMIT %s OFFSET %s',(page_size,(page-1)*page_size)).fetchall()
        else:
            rows=session.execute('SELECT * FROM {api_audit_log} WHERE id_api_user=%s ORDER BY sequence_api_audit_log DESC LIMIT %s OFFSET %s',(actor['id_api_user'],page_size,(page-1)*page_size)).fetchall()
        return {'items':rows}

    @app.get('/record-versions/{resource}/{identifier}',tags=['Evidence'])
    def versions(resource:str,identifier:str,auth=Depends(context,scope='function')):
        session,actor=auth
        require(session,actor,'record_version','read')
        if resource not in SPECS:
            raise HTTPException(404,'Unknown versioned resource')
        repository.get(session,actor,resource,identifier)
        return {'items':session.execute('SELECT * FROM {record_version} WHERE resource=%s AND record_id=%s ORDER BY version_number DESC LIMIT %s',(store.names[resource],identifier,session.limits()['page_size'])).fetchall()}

    def mount(resource):
        replacement,partial=schemas(resource)
        def listing(request:Request,page:Annotated[int,Query(ge=1)]=1,page_size:Annotated[int,Query(ge=1)]=10,auth=Depends(context,scope='function')):
            session,actor=auth
            return repository.list_records(session,actor,resource,page,page_size,request.query_params)
        def item(identifier:str,auth=Depends(context,scope='function')):
            return repository.get(*auth,resource,identifier)
        def create(body,auth=Depends(context,scope='function')):
            session,actor=auth
            if isinstance(body,list):
                if not body or len(body)>session.limits()['batch_items']:
                    raise HTTPException(422,'Batch size is outside the permitted range')
                items=[repository.create(session,actor,resource,entry.model_dump()) for entry in body]
                # Re-read after ordered shifts so every batch item represents the committed state.
                final=[repository.get(session,actor,resource,entry['id_'+resource],'create') for entry in items]
                return {'created_count':len(final),'items':final}
            return repository.create(session,actor,resource,body.model_dump())
        create.__annotations__['body']=replacement | list[replacement]
        def replace(identifier:str,body,auth=Depends(context,scope='function')):
            return repository.update(*auth,resource,identifier,body.model_dump(),False)
        replace.__annotations__['body']=replacement
        def patch_record(identifier:str,body,auth=Depends(context,scope='function')):
            return repository.update(*auth,resource,identifier,body.model_dump(exclude_unset=True),True)
        patch_record.__annotations__['body']=partial
        def remove(identifier:str,auth=Depends(context,scope='function')):
            repository.delete(*auth,resource,identifier)
            return Response(status_code=204)
        path='/'+resource
        for endpoint,methods,suffix,status,summary in (
            (listing,['GET'],'',200,'List authorized records'),(item,['GET'],'/{identifier}',200,'Read an authorized record'),
            (create,['POST'],'',201,'Create one record or an atomic batch'),
            (replace,['PUT'],'/{identifier}',200,'Replace all editable fields; omitted optional fields reset to defaults'),
            (patch_record,['PATCH'],'/{identifier}',200,'Update only supplied fields'),
            (remove,['DELETE'],'/{identifier}',204,'Delete an authorized record')):
            if resource in APPEND_ONLY and methods[0] in ('PUT','PATCH','DELETE'):
                continue
            app.add_api_route(path+suffix,endpoint,methods=methods,status_code=status,tags=[resource],name=resource+'_'+endpoint.__name__,summary=summary)
    for resource in SPECS:
        mount(resource)
    install_authorization(app,context)
    # Swagger publishes the same section/action contract used by runtime checks.
    for route in app.routes:
        path=getattr(route,'path','')
        if path=='/installation/plan':
            route.openapi_extra={'x-required-permission':'installation_plan:read','x-reserved-human':True}
            continue
        methods=getattr(route,'methods',set())
        resource=path.strip('/').split('/')[0]
        resource={'api-users':'api_user','credentials':'api_user','roles':'role','permissions':'permission',
                  'access-rules':'access_rule','settings':'operator_setting','audit':'api_audit_log','record-versions':'record_version'}.get(resource,resource)
        if resource not in rbac.RESOURCE_SECTION:
            continue
        method=next(iter(methods-{'HEAD','OPTIONS'}),'GET')
        action={'GET':'read','POST':'write','PUT':'edit','PATCH':'edit','DELETE':'delete'}.get(method)
        if path.endswith('/permissions') and resource=='api_user':
            resource='permission_assignment'
        if path.endswith('/credentials') and method=='POST':
            action='edit'
        route.openapi_extra={'x-required-permission':rbac.RESOURCE_SECTION[resource]+':'+action}
    return app
