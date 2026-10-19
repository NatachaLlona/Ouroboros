"""Complete strict contracts for the integer-ID test resource."""
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StrictInt, StrictStr

from app.datetimes import DisplayZone, Instant, ZoneName
from app.pagination import integer_query
from app.ordering import TestOrder
from app.schemas.catalogue import (BulkSelection, PATTERN_HELP, Presentation, Selection,
                                   UpdateInput)

PositiveID = Annotated[StrictInt, Field(gt=0, le=9223372036854775807)]
QueryID = Annotated[int, BeforeValidator(integer_query), Field(gt=0, le=9223372036854775807)]


class TestCreate(BaseModel):
    """Store supplied Unicode TEXT unchanged, without an artificial length limit."""
    model_config = ConfigDict(extra='forbid')
    value: StrictStr = Field(description='Unrestricted PostgreSQL TEXT, including empty and long Unicode values.', examples=['Ouroboros está vivo! 🐍💻'])


class TestEntry(TestCreate):
    """The same full public representation for POST, GET, PUT and page items."""
    id: PositiveID = Field(description='Database-generated integer ID; immutable.')
    created_at: Instant | None = Field(description='Server creation instant in UTC; unknown historical dates remain null.')
    created_at_timezone: ZoneName | None = Field(description='Recorded application source zone; unknown historical context remains null.')
    presentation: Presentation = Field(description='Read-only display of canonical dates.', json_schema_extra={'readOnly': True})


class TestUpdate(UpdateInput):
    """Omitted values stay unchanged; full GET records can be echoed unchanged."""
    value: StrictStr = Field(default=None, description='Omit to preserve. Explicit null is invalid; empty text is valid.')
    id: PositiveID = Field(default=None, description='Omit or echo the unchanged integer ID.')
    created_at: Instant | None = Field(default=None, description='Omit or echo the unchanged server creation instant.')
    created_at_timezone: ZoneName | None = Field(default=None, description='Omit or echo the unchanged source zone.')
    presentation: Presentation = Field(default=None, description='Omit or echo the complete unchanged presentation.', json_schema_extra={'readOnly': True})


class TestFilters(Selection):
    """Identical trusted AND predicates for reads and bulk operations."""
    id: QueryID | None = Field(default=None, description='Optional exact positive integer ID.', examples=[1])
    value: str | None = Field(default=None, description=PATTERN_HELP, examples=['%Ouroboros%', r'literal\%\_\\'])
    created_at: Instant | None = Field(default=None, description='Exact offset-aware creation instant.', examples=['2026-10-19T12:00:00Z'])
    created_at_timezone: str | None = Field(default=None, description='Exact recorded source zone.', examples=['Europe/Lisbon'])
    created_at_from: Instant | None = Field(default=None, description='Inclusive creation instant lower bound; explicit UTC offset required. Historical null dates do not match.', examples=['2026-10-01T00:00:00+01:00'])
    created_at_to: Instant | None = Field(default=None, description='Exclusive creation instant upper bound, after from. Historical null dates do not match.', examples=['2026-11-01T00:00:00Z'])


class TestQuery(TestFilters):
    page: Annotated[int, BeforeValidator(integer_query), Field(ge=1)] = Field(default=1, description='One-based page after filtering and ordering.', examples=[1, 2])
    page_size: Annotated[int, BeforeValidator(integer_query), Field(ge=10, le=50)] = Field(default=50, description='10–50 items; count precedes pagination.', examples=[50, 10])
    order_by: TestOrder = Field(default='id', description='Whitelisted public scalar. Ties use integer ID ascending.', examples=['id', 'value', 'created_at'])
    order_direction: Literal['asc', 'desc'] = Field(default='asc', description='NULL values always sort last.', examples=['asc', 'desc'])
    display_timezone: DisplayZone | None = Field(default=None, description='IANA zone or original; default is configured display zone. Canonical dates remain UTC.', examples=['Europe/Lisbon', 'original'])


class TestBulkQuery(TestFilters, BulkSelection):
    """Strict bulk filters exclude pagination, sorting and presentation controls."""


class TestBulkUpdate(UpdateInput):
    value: StrictStr = Field(default=None, description='Required submitted value; all matching rows are targeted. Empty text is valid.', examples=['Changed in disposable QA'])


def validate_query_id(value):
    """Retain the inherited ID validator for internal compatibility."""
    if value is not None and (not isinstance(value, str) or not value.isascii() or not value.isdecimal()):
        raise ValueError('id must be a positive integer')
    return value
