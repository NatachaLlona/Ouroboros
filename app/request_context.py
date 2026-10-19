"""Isolated request metadata propagated by AnyIO into synchronous workers."""
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime
import secrets


@dataclass(frozen=True)
class RequestContext:
    interaction_id: str
    method: str
    path: str


request_context = ContextVar("foundation_request_context", default=None)


def create_interaction_id():
    return datetime.now().astimezone().strftime("%Y%m%d%H%M%S") + f"{secrets.randbelow(10**10):010d}"
