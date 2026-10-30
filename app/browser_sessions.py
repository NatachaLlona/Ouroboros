"""Bounded opaque browser sessions; no bearer tokens or passwords are retained."""
from dataclasses import dataclass, field, replace
import hashlib
import ipaddress
import secrets
import threading
import time
from urllib.parse import urlsplit

from fastapi import HTTPException
from app.config import ConfigurationError


def browser_settings(config):
    """Fail closed for HTTP; permit an explicitly configured loopback dev origin."""
    settings = config.get('browser', {})
    if not isinstance(settings, dict) or set(settings) - {'origin', 'allow_loopback_http', 'idle_timeout_seconds', 'absolute_lifetime_seconds'}:
        raise ConfigurationError('Unsupported browser configuration field')
    idle = settings.get('idle_timeout_seconds', 7200)
    absolute = settings.get('absolute_lifetime_seconds', 43200)
    if type(idle) is not int or type(absolute) is not int or not 60 <= idle <= absolute <= 86400:
        raise ConfigurationError('Browser deadlines require integers: 60 <= idle_timeout_seconds <= absolute_lifetime_seconds <= 86400')
    origin = settings.get('origin', f'https://localhost:{config.get("port", 6969)}')
    allow_http = settings.get('allow_loopback_http', False)
    try:
        parsed = urlsplit(origin)
        if (type(allow_http) is not bool or parsed.scheme not in ('http', 'https') or not parsed.hostname
                or parsed.username is not None or parsed.password is not None or parsed.path or parsed.query
                or parsed.fragment or any(character.isspace() for character in origin)):
            raise ValueError
        parsed.port
        if parsed.scheme == 'http' and not (allow_http and parsed.hostname in ('localhost', '127.0.0.1', '::1')):
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        raise ConfigurationError('browser.origin must be an HTTPS origin; HTTP requires explicit allow_loopback_http and a loopback host') from None
    return origin, parsed.scheme == 'https'


@dataclass(frozen=True)
class BrowserSession:
    user_id: int
    credential_version: int
    expires: float
    csrf: str = field(repr=False)
    absolute_expires: float


class BrowserSessions:
    """Single-worker absolute expiry, bounded storage and revocable random IDs."""
    def __init__(self, config, clock=time.monotonic, capacity=10000):
        self.origin, self.secure = browser_settings(config)
        self.cookie_name = '__Host-ouroboros_session' if self.secure else 'ouroboros_dev_session'
        self.idle_timeout = config.get('browser', {}).get('idle_timeout_seconds', 7200)
        self.ttl = config.get('browser', {}).get('absolute_lifetime_seconds', 43200)
        self.clock, self.capacity = clock, capacity
        self.entries = {}
        self.lock = threading.Lock()

    def digest(self, value):
        return hashlib.sha256(value.encode('utf-8')).digest()

    def transport(self, request):
        """Do not trust forwarded headers or accept foreign origin/browser contexts."""
        if str(request.base_url).rstrip('/') != self.origin:
            raise HTTPException(403, 'Browser origin rejected')
        if not self.secure:
            try:
                if not request.client or not ipaddress.ip_address(request.client.host).is_loopback:
                    raise ValueError
            except ValueError:
                raise HTTPException(403, 'Loopback HTTP development only') from None
        if request.headers.get('sec-fetch-site') == 'cross-site':
            raise HTTPException(403, 'Browser origin rejected')

    def same_origin(self, request):
        self.transport(request)
        if request.headers.get('origin') != self.origin:
            raise HTTPException(403, 'CSRF verification failed')

    def prune(self):
        now = self.clock()
        self.entries = {key: value for key, value in self.entries.items() if min(value.expires, value.absolute_expires) > now}

    def lookup(self, request):
        cookie = request.cookies.get(self.cookie_name)
        if not cookie or len(cookie) > 128:
            return None
        with self.lock:
            self.prune()
            return self.entries.get(self.digest(cookie))

    def discard(self, request):
        cookie = request.cookies.get(self.cookie_name)
        if cookie and len(cookie) <= 128:
            with self.lock:
                self.entries.pop(self.digest(cookie), None)

    def create(self, request, user):
        with self.lock:
            self.prune()
            old = request.cookies.get(self.cookie_name)
            if old and len(old) <= 128:
                self.entries.pop(self.digest(old), None)
            if len(self.entries) >= self.capacity:
                raise HTTPException(503, 'Browser session capacity unavailable')
            cookie = secrets.token_urlsafe(32)
            now = self.clock()
            session = BrowserSession(user.id, user.credential_version, now + self.idle_timeout, secrets.token_urlsafe(32), now + self.ttl)
            self.entries[self.digest(cookie)] = session
            return cookie, session

    def check_csrf(self, request, session):
        self.same_origin(request)
        supplied = request.headers.get('x-csrf-token', '')
        if not supplied.isascii() or not secrets.compare_digest(supplied, session.csrf):
            raise HTTPException(403, 'CSRF verification failed')

    def authenticate(self, request):
        self.transport(request)
        session = self.lookup(request)
        if session is None:
            raise HTTPException(401, 'Browser session required')
        user = request.app.state.auth.users.get_by_id(session.user_id)
        if user is None or not user.is_active or user.credential_version != session.credential_version:
            self.discard(request)
            raise HTTPException(401, 'Browser session expired')
        if request.method not in ('GET', 'HEAD', 'OPTIONS'):
            self.check_csrf(request, session)
        from app.audit_context import authenticated_actor
        authenticated_actor(user)
        request.scope['browser_session_key'] = self.digest(request.cookies[self.cookie_name])
        scopes = set(user.scopes).intersection(('test:read', 'test:write'))
        if user.role == 'supervisor':
            scopes.add('catalogue:access')
        return {'sub': str(user.id), 'role': user.role, 'credential_version': user.credential_version,
                'scopes': sorted(scopes)}, user, session

    def accepted_activity(self, key, renew=False):
        """Renew only accepted user-driven activity, never the absolute deadline."""
        with self.lock:
            self.prune()
            session = self.entries.get(key)
            if session is None:
                return None
            if renew:
                session = replace(session, expires=min(self.clock() + self.idle_timeout, session.absolute_expires))
                self.entries[key] = session
            return max(0, int(min(session.expires, session.absolute_expires) - self.clock())), max(0, int(session.absolute_expires - self.clock()))

    def close(self):
        with self.lock:
            self.entries.clear()
