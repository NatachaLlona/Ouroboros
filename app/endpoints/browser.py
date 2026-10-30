"""Browser session boundary and static pages; catalogue writes use existing APIs."""
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel, ConfigDict, SecretStr, StrictStr, Field
from typing import Annotated, Literal
from app.config import PROJECT_ROOT
from app.errors import ErrorResponse

router = APIRouter(tags=['browser'])
FRONTEND = PROJECT_ROOT / 'frontend'
BUILD = FRONTEND / 'dist' / 'browser'


def application_shell(status_code=200):
    """Only explicit frontend routes serve the SPA; API/static misses stay misses."""
    if not (BUILD / 'index.html').is_file():
        raise HTTPException(503, 'Frontend build unavailable')
    return FileResponse(BUILD / 'index.html', status_code=status_code, headers={'Cache-Control': 'no-store'})


class BrowserLogin(BaseModel):
    model_config = ConfigDict(extra='forbid')
    username: StrictStr = Field(min_length=1)
    password: SecretStr = Field(strict=True, min_length=1)


class AnonymousSession(BaseModel):
    authenticated: Literal[False]


class AuthenticatedSession(BaseModel):
    authenticated: Literal[True]
    username: str
    role: Literal['standard', 'supervisor', 'administrator']
    is_active: bool
    can_create: bool
    csrf_token: str = Field(repr=False, description='Synchronizer token for X-CSRF-Token, held only in browser memory; never a bearer token.')
    expires_in: int = Field(ge=0, description='Remaining seconds until the earlier idle or absolute deadline.')
    absolute_expires_in: int = Field(ge=0, description='Remaining absolute lifetime; never extended by activity.')


SessionView = Annotated[AnonymousSession | AuthenticatedSession, Field(discriminator='authenticated')]


def session_view(user, session, sessions):
    return {'authenticated': True, 'username': user.username, 'role': user.role, 'is_active': user.is_active,
            'can_create': user.role in ('supervisor', 'administrator'), 'csrf_token': session.csrf,
            'expires_in': max(0, int(min(session.expires, session.absolute_expires) - sessions.clock())),
            'absolute_expires_in': max(0, int(session.absolute_expires - sessions.clock()))}


@router.get('/', include_in_schema=False)
def home():
    return application_shell()


@router.get('/cadastros', include_in_schema=False)
@router.get('/consultas', include_in_schema=False)
def entries(request: Request):
    try:
        _, user, _ = request.app.state.browser_sessions.authenticate(request)
    except HTTPException as error:
        if error.status_code == 401:
            destination = 'consultas' if request.url.path == '/consultas' else 'cadastros'
            return RedirectResponse('/?entrar=1&destino=' + destination, status_code=303)
        raise
    if user.role not in ('administrator', 'supervisor'):
        return application_shell(status_code=403)
    return application_shell()


@router.get('/cadastrar', include_in_schema=False)
@router.get('/consultar', include_in_schema=False)
def selection():
    return application_shell()


@router.get('/browser/session', response_model=SessionView)
def current_session(request: Request, response: Response):
    response.headers['Cache-Control'] = 'no-store'
    try:
        _, user, session = request.app.state.browser_sessions.authenticate(request)
    except HTTPException as error:
        if error.status_code == 401:
            return {'authenticated': False}
        raise
    return session_view(user, session, request.app.state.browser_sessions)


@router.post('/browser/login', response_model=AuthenticatedSession, responses={429: {'model': ErrorResponse, 'description': 'Shared account/client login limit; Retry-After seconds.', 'headers': {'Retry-After': {'schema': {'type': 'integer'}, 'description': 'Seconds before retrying.'}}}})
def login(payload: BrowserLogin, request: Request, response: Response):
    sessions = request.app.state.browser_sessions
    sessions.same_origin(request)
    if request.headers.get('content-type', '').split(';')[0].strip() != 'application/json':
        raise HTTPException(403, 'CSRF verification failed')
    retry = request.app.state.login_throttle.admit(payload.username, request.client.host if request.client else 'unknown')
    if retry is not None:
        raise HTTPException(429, 'Login attempt limit reached', headers={'Retry-After': str(retry), 'Cache-Control': 'no-store'})
    user = request.app.state.auth.verify_password(payload.username, payload.password.get_secret_value())
    if user is None:
        raise HTTPException(401, 'Invalid credentials')
    cookie, session = sessions.create(request, user)
    response.set_cookie(sessions.cookie_name, cookie, max_age=sessions.ttl, httponly=True,
                        secure=sessions.secure, samesite='strict', path='/')
    response.headers['Cache-Control'] = 'no-store'
    return session_view(user, session, sessions)


@router.post('/browser/logout', status_code=204)
def logout(request: Request):
    sessions = request.app.state.browser_sessions
    sessions.same_origin(request)
    session = sessions.lookup(request)
    if session is not None:
        sessions.check_csrf(request, session)
    sessions.discard(request)
    response = Response(status_code=204, headers={'Cache-Control': 'no-store'})
    response.delete_cookie(sessions.cookie_name, path='/', secure=sessions.secure, httponly=True, samesite='strict')
    return response


class BrowserHeadersMiddleware:
    """Local-only assets and no framing, embedding, sniffing or secret caching."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        async def secured(message):
            if message['type'] == 'http.response.start':
                headers = list(message.get('headers', []))
                key = scope.get('browser_session_key')
                application = scope.get('app')
                if key and application is not None and 200 <= message['status'] < 300:
                    incoming = dict(scope.get('headers', ()))
                    renew = scope['path'] in ('/cadastros', '/consultas') or (
                        not scope['path'].startswith('/browser/') and incoming.get(b'x-ouroboros-activity') == b'user')
                    deadlines = application.state.browser_sessions.accepted_activity(key, renew=renew)
                    if deadlines is not None:
                        headers += [(b'x-browser-expires-in', str(deadlines[0]).encode()),
                                    (b'x-browser-absolute-expires-in', str(deadlines[1]).encode())]
                if scope['path'] in ('/docs', '/openapi.json', '/redoc'):
                    headers = [(key, value) for key, value in headers if key.lower() != b'cache-control']
                    headers.append((b'cache-control', b'no-store'))
                message = {**message, 'headers': headers}
            if message['type'] == 'http.response.start' and (scope['path'] in ('/', '/cadastros', '/consultas', '/cadastrar', '/consultar') or scope['path'].startswith(('/frontend/', '/browser/'))):
                headers = list(message.get('headers', []))
                headers.extend([(b'x-content-type-options', b'nosniff'), (b'referrer-policy', b'no-referrer'),
                    (b'x-frame-options', b'DENY'),
                    (b'content-security-policy', b"default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; font-src 'self'; connect-src 'self'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'")])
                if scope['path'].startswith('/browser/'):
                    headers = [(key, value) for key, value in headers if key.lower() != b'cache-control']
                    headers.append((b'cache-control', b'no-store'))
                message = {**message, 'headers': headers}
            await send(message)
        await self.app(scope, receive, secured)
