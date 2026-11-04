"""Short-lived, body-bound delegation issued only after API authorization."""
import hashlib
import hmac
import json
import secrets
import threading
import time
from pathlib import Path


def signing_key(path):
    key = Path(path).read_bytes().strip()
    if len(key) < 32:
        raise ValueError('Invalid service delegation key')
    return key


def delegate(key, operation, body, actor, clock=time.time):
    claims = {'operation': operation, 'digest': hashlib.sha256(body).hexdigest(),
              'subject': str(actor['sub']), 'scope': 'catalogue:access',
              'issued': int(clock()), 'nonce': secrets.token_hex(24)}
    encoded = json.dumps(claims, sort_keys=True, separators=(',', ':')).encode().hex()
    signature = hmac.new(key, encoded.encode(), hashlib.sha256).hexdigest()
    return encoded + '.' + signature


class DelegationVerifier:
    def __init__(self, key, clock=time.time, max_age=30):
        self.key, self.clock = key, clock
        self.seen = {}
        self.lock = threading.Lock()
        self.max_age = max_age

    def verify(self, token, operation, body):
        if not token or len(token) > 4096:
            raise ValueError('Invalid service authorization')
        encoded, signature = token.split('.')
        expected = hmac.new(self.key, encoded.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError('Invalid service authorization')
        claims = json.loads(bytes.fromhex(encoded))
        now = self.clock()
        if (claims['operation'] != operation or claims['scope'] != 'catalogue:access'
                or not claims['subject'] or not 0 <= now - claims['issued'] <= self.max_age
                or claims['digest'] != hashlib.sha256(body).hexdigest()):
            raise ValueError('Invalid service authorization')
        with self.lock:
            self.seen = {nonce: issued for nonce, issued in self.seen.items() if now-issued <= self.max_age}
            if claims['nonce'] in self.seen or len(self.seen) >= 10000:
                raise ValueError('Service authorization replay rejected')
            self.seen[claims['nonce']] = claims['issued']
        return claims
