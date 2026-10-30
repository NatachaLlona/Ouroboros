"""Isolated request metadata propagated by AnyIO into synchronous workers."""
from contextvars import ContextVar
from dataclasses import dataclass
import secrets
from app.datetimes import utcnow


@dataclass(frozen=True)
class RequestContext:
    interaction_id: str
    method: str
    path: str


request_context = ContextVar("foundation_request_context", default=None)


def create_interaction_id():
    return utcnow().strftime("%Y%m%d%H%M%S") + f"{secrets.randbelow(10**10):010d}"
