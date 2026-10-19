"""Strict request and response schemas for test entries."""
from pydantic import BaseModel, ConfigDict, StrictStr


class TestCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: StrictStr


class TestEntry(BaseModel):
    id: int
    value: str


def validate_query_id(value):
    """Reject fractional representations instead of silently coercing them to IDs."""
    if value is not None and (not isinstance(value, str) or not value.isascii() or not value.isdecimal()):
        raise ValueError("id must be a positive integer")
    return value
