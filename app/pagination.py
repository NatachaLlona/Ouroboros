"""Shared SQL collection pagination and response contracts."""
from typing import Annotated, Generic, TypeVar

from fastapi import Query
from pydantic import BaseModel, BeforeValidator

T = TypeVar("T")


def integer_query(value):
    """Reject fractional query strings instead of coercing them.

    Args:
        value: Query text or the integer default.

    Returns:
        The unchanged value for bounded integer validation.

    Raises:
        ValueError: If the representation is not a decimal integer.
    """
    if isinstance(value, str) and (not value.isascii() or not value.isdecimal()):
        raise ValueError("Expected a decimal integer")
    return value


PageNumber = Annotated[int, Query(ge=1, description="One-based page after filtering, ordered by ascending ID. Count includes every matching record.", examples=[1, 2]), BeforeValidator(integer_query)]
PageSize = Annotated[int, Query(ge=10, le=50, description="Maximum records per page (10–50); count is computed before pagination.", examples=[50, 10]), BeforeValidator(integer_query)]


class Page(BaseModel, Generic[T]):
    """A filtered count and a bounded page from the same database snapshot."""

    count: int
    page: int
    page_size: int
    items: list[T]


def pagination(page: PageNumber = 1, page_size: PageSize = 50):
    """Return validated shared parameters for collection endpoints."""
    return {"page": page, "page_size": page_size}
