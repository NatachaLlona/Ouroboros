"""Thread-safe bounded admission limits before expensive password verification."""
import hashlib
import math
import threading
import time


class LoginThrottle:
    """Single-worker fixed windows: 10/account and 50/client per five minutes.

    Count every admitted attempt, including concurrent/successful requests.
    At capacity, reject new identities until expiry rather than evicting limits.
    No raw usernames or client addresses are retained or logged.
    """
    def __init__(self, clock=time.monotonic, window=300, capacity=10000):
        self.clock, self.window, self.capacity = clock, window, capacity
        self.entries = {}
        self.lock = threading.Lock()

    def admit(self, username, address):
        keys = [(kind, hashlib.sha256(value.encode('utf-8')).digest(), limit)
                for kind, value, limit in (('account', username, 10), ('client', address, 50))]
        with self.lock:
            now = self.clock()
            self.entries = {key: value for key, value in self.entries.items() if value[0] > now}
            waits = [self.entries[(kind, digest)][0] - now for kind, digest, limit in keys
                     if (kind, digest) in self.entries and self.entries[(kind, digest)][1] >= limit]
            needed = sum((kind, digest) not in self.entries for kind, digest, _ in keys)
            if len(self.entries) + needed > self.capacity:
                waits.append(min(value[0] for value in self.entries.values()) - now)
            if waits:
                return max(1, math.ceil(max(waits)))
            for kind, digest, _ in keys:
                expires, count = self.entries.get((kind, digest), (now + self.window, 0))
                self.entries[(kind, digest)] = (expires, count + 1)
            return None
