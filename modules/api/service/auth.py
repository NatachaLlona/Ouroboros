"""Separate human and OAuth client credentials with current SQL authorization."""
import secrets
import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError
from fastapi import HTTPException
from shared.datetimes import utcnow
from database.settings import structural_identity
from api.service.resources import SPECS, ADMIN_RESOURCES, ACTIONS

HASHER=PasswordHasher()
DUMMY_HASH=HASHER.hash(secrets.token_urlsafe(48))


def denied():
    raise HTTPException(403,'Permission denied')


def identity(session,actor):
    row=session.execute('SELECT id_api_user,username,is_active,credential_version FROM {api_user} WHERE id_api_user=%s',(actor,)).fetchone()
    if row is None or not row['is_active']:
        raise HTTPException(401,'Invalid or revoked access token',headers={'WWW-Authenticate':'Bearer'})
    row=dict(row)
    row['roles']={item['name'] for item in session.execute('SELECT r.name FROM {api_user_role} ur JOIN {role} r USING(id_role) WHERE ur.id_api_user=%s',(actor,))}
    people=session.execute('SELECT l.id_app_user FROM {app_user_api} l JOIN {app_user} p USING(id_app_user) WHERE l.id_api_user=%s AND l.valid_until IS NULL AND p.is_active ORDER BY l.id_app_user',(actor,)).fetchall()
    row['person']=people[0]['id_app_user'] if len(people)==1 else None
    row['super']=session.execute('SELECT id_super_administrator FROM {super_administrator} s JOIN {app_user_api} l USING(id_app_user_api) JOIN {app_user} p ON p.id_app_user=s.id_app_user WHERE s.id_api_user=%s AND l.valid_until IS NULL AND p.is_active',(actor,)).fetchone() is not None
    return row


def bind(session,actor):
    session.execute("SELECT set_config('ouroboros.actor_api_user',%s,true)",(actor['id_api_user'],))
    session.execute("SELECT set_config('ouroboros.actor_app_user',%s,true)",(actor['person'] or '',))


def can(session,actor,resource,action):
    return next(iter(session.function('api_can',actor['id_api_user'],resource,action).fetchone().values())) is True


def require(session,actor,resource,action):
    scope=resource+':'+action
    if scope not in actor.get('scopes',[]) or not can(session,actor,resource,action):
        denied()


class Authentication:
    def __init__(self,settings,document,key):
        self.settings,self.key=settings,key
        self.realm=structural_identity(document)[0]

    def token(self,session,record,password,kind,requested=''):
        try:
            valid=HASHER.verify(record['password_hash'] if record else DUMMY_HASH,password)
        except (VerificationError,InvalidHashError):
            valid=False
        if not valid or record is None:
            raise HTTPException(401,'Invalid authentication credentials',headers={'WWW-Authenticate':'Bearer'})
        actor=identity(session,record['actor'])
        allowed={resource+':'+action for resource in (*SPECS,*ADMIN_RESOURCES) for action in ACTIONS if can(session,actor,resource,action)}
        if actor['super'] and kind=='human_password':
            allowed.update(('installation_plan:read','installation_plan:update'))
        scopes=set(requested.split()) if requested else allowed
        if not scopes<=allowed:
            denied()
        now=int(utcnow().timestamp())
        lifetime=session.limits()['token_ttl_seconds']
        token=jwt.encode({'sub':record['actor'],'credential':record['credential'], 'credential_version':actor['credential_version'],
                          'kind':kind,'scopes':sorted(scopes),'db':self.realm,'iat':now,'nbf':now,'exp':now+lifetime,
                          'iss':self.settings['token']['issuer'],'aud':self.settings['token']['audience'],
                          'jti':secrets.token_hex(16)},self.key,algorithm='HS256')
        return {'access_token':token,'token_type':'bearer','expires_in':lifetime,'scope':' '.join(sorted(scopes))}

    def authenticate(self,session,token):
        try:
            claims=jwt.decode(token,self.key,algorithms=['HS256'],issuer=self.settings['token']['issuer'],
                              audience=self.settings['token']['audience'],leeway=self.settings['token']['clock_skew_seconds'],
                              options={'require':['sub','credential','credential_version','kind','scopes','db','iat','nbf','exp','jti']})
            if (claims['db']!=self.realm or claims['kind'] not in ('human_password','client_credentials')
                or type(claims['credential_version']) is not int or type(claims['scopes']) is not list
                or any(type(scope) is not str for scope in claims['scopes'])
                or any(type(claims[field]) is not int for field in ('iat','nbf','exp'))
                or claims['exp']<=claims['iat'] or type(claims['sub']) is not str or type(claims['credential']) is not str):
                raise ValueError
            actor=identity(session,claims['sub'])
            current=next(iter(session.function('api_credential_current',claims['credential'],claims['sub'],claims['kind']).fetchone().values()))
            if (not current or claims['credential_version']!=actor['credential_version']
                or (claims['kind']=='human_password' and actor['person'] is None)):
                raise ValueError
        except (jwt.InvalidTokenError,ValueError,TypeError,KeyError):
            raise HTTPException(401,'Invalid or revoked access token',headers={'WWW-Authenticate':'Bearer'}) from None
        actor.update(scopes=claims['scopes'],kind=claims['kind'])
        bind(session,actor)
        return actor
