"""Explicit resource contracts and query models for the eleven catalogue tables.

Models are built from this fixed public contract, not database introspection or
client-provided identifiers. Each route publishes its own named OpenAPI schemas.
"""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import (BaseModel, BeforeValidator, ConfigDict, Field,
                      StrictBool, StrictInt, StrictStr, create_model, model_validator)
from app.pagination import integer_query
from pydantic_core import PydanticCustomError
from app.datetimes import Instant, SourceInstant, ZoneName, DisplayZone, check_range, date_filter_fields, date_predicates
from app.schemas.relationships import collection_record

Text = StrictStr
Technical = Annotated[StrictStr, Field(pattern=r'^[a-z][a-z0-9]*(_[a-z0-9]+)*$')]
PositiveInteger = Annotated[StrictInt, Field(gt=0, le=9223372036854775807)]


def decimal_input(value):
    """Reject booleans while accepting JSON numbers and exact decimal strings."""
    if isinstance(value, bool):
        raise ValueError('Expected a decimal number')
    return value


Price = Annotated[Decimal, BeforeValidator(decimal_input), Field(ge=0, allow_inf_nan=False)]
Duration = Annotated[Decimal, BeforeValidator(decimal_input), Field(gt=0, allow_inf_nan=False)]
PATTERN_HELP = ('Case-insensitive PostgreSQL ILIKE pattern. % matches any sequence; _ matches one character; '
                'backslash escapes %, _ and backslash. No wildcards are added. Omit to disable; empty matches empty text.')


class RecordInput(BaseModel):
    """Strict object structure; preserve Unicode and supplied field values."""
    model_config = ConfigDict(extra='forbid')

    @model_validator(mode='after')
    def association_rules(self):
        """Enforce tag choice/origin rules on a complete work_tags input."""
        if {'id_tags', 'id_tag_relationships'}.issubset(type(self).model_fields) and not isinstance(self, UpdateInput):
            if (self.id_tags is None) == (self.id_tag_relationships is None):
                raise ValueError('Supply exactly one tag or tag relationship')
            if self.id_watchlist_entries is not None and self.id_watch_history is not None:
                raise ValueError('Supply at most one origin')
        return self


class UpdateInput(RecordInput):
    """PUT omissions preserve values; explicit null clears only nullable fields."""

    @model_validator(mode='after')
    def nonempty_update(self):
        """Reject a no-input operation; complete-record validation follows row locking."""
        if not self.model_fields_set:
            raise PydanticCustomError('empty_update', 'Supply at least one field to update or echo')
        return self


class ClassificationBulkUpdate(UpdateInput):
    """Tier is an individual ordering operation, never a shared bulk value."""

    @model_validator(mode='before')
    @classmethod
    def individual_tier_only(cls, value):
        if isinstance(value, dict) and 'tier' in value:
            raise PydanticCustomError('tier_bulk_update',
                'Bulk tier changes are not supported; use individual PUT to reorder classifications')
        return value


class PresentationDate(BaseModel):
    """Friendly read-only display; never used for database filtering or sorting."""
    model_config = ConfigDict(extra='forbid')
    datetime: str
    date: str
    time: str
    timezone: str
    offset: str
    fallback_utc: bool


class Presentation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    display_timezone: DisplayZone
    dates: dict[str, PresentationDate | None]


class Selection(BaseModel):
    """Reject unknown filters and invalid inclusive/exclusive creation ranges."""
    model_config = ConfigDict(extra='forbid')

    filter_timezone: ZoneName | None = Field(default=None, description='IANA zone for calendar filters; defaults to application_timezone, independent of display_timezone.', examples=['Europe/Lisbon', 'America/New_York'])

    @model_validator(mode='after')
    def date_bounds(self):
        values = self.model_dump()
        fields = [name[:-5] for name in type(self).model_fields if name.endswith('_date')]
        # Mixed date/instant ordering needs the configured application zone at the route.
        if self.filter_timezone is not None or not any(isinstance(v, datetime) for k, v in values.items() if k.endswith(('_from', '_to'))):
            date_predicates(values, fields)
        else:
            for field in fields:
                if values.get(field + '_date') is not None and any(values.get(field + suffix) is not None for suffix in ('_from', '_to')):
                    raise ValueError('Exact calendar day cannot be combined with range bounds')
                start, end = values.get(field + '_from'), values.get(field + '_to')
                if isinstance(start, datetime) and isinstance(end, datetime):
                    check_range(start, end)
        return self

    def bind_filter_timezone(self, config):
        from app.catalogue_repository import CatalogueError
        self.filter_timezone = self.filter_timezone or config.get('application_timezone', 'Europe/Lisbon')
        try:
            date_predicates(self.model_dump(), [name[:-5] for name in type(self).model_fields if name.endswith('_date')])
        except ValueError:
            raise CatalogueError(422, 'Invalid date filter') from None
        return self


class BulkSelection(Selection):
    """A preview has no mutation; actual bulk requests require confirmation."""
    confirm: bool = Field(default=False, description='Actual execution requires explicit true. No filters targets the whole resource.', examples=[False, True])
    dry_run: bool = Field(default=False, description='Preview matched_count only; confirmation is not required. Counts may change before execution.', examples=[True, False])

    @model_validator(mode='after')
    def confirmation(self):
        if not self.dry_run and not self.confirm:
            raise PydanticCustomError('confirmation_required', 'Explicit confirm=true is required')
        return self


@dataclass(frozen=True)
class Resource:
    """Trusted public contract used by schemas, SQL repositories and routers."""
    table: str
    fields: dict
    create: type[BaseModel]
    update: type[BaseModel]
    record: type[BaseModel]
    query: type[BaseModel]
    columns: tuple[str, ...]
    immutable: tuple[str, ...]
    pattern_fields: tuple[str, ...]
    bulk_query: type[BaseModel]
    bulk_update: type[BaseModel]
    list_record: type[BaseModel]

    @property
    def key(self):
        return 'id_' + self.table


# Values are (annotation, default). Ellipsis means required; None means nullable.
CONTRACTS = {
    'works': dict(title=(Text, ...), title_language=(Text, ...), synopsis=(Text | None, None)),
    'platforms': dict(platform_name=(Text, ...), platform_is_paid=(StrictBool, ...),
        platform_is_episodes=(StrictBool, ...), platform_is_duration_time=(StrictBool, ...),
        price_amount=(Price | None, None), price_currency=(Text | None, None)),
    'work_availabilities': dict(id_works=(Text, ...), id_platforms=(Text, ...),
        duration_minutes=(Duration | None, None), episode_quantity=(PositiveInteger | None, None),
        publisher_profile=(Text | None, None), url=(Text | None, None)),
    'tags': dict(tag_name=(Technical, ...), display_name_tags=(Text, ...), description_tags=(Text | None, None)),
    'tag_categories': dict(tag_category_name=(Technical, ...), display_name_tag_categories=(Text, ...), description_tag_categories=(Text | None, None)),
    'tag_category_relationships': dict(id_tags=(Text, ...), id_tag_categories=(Text, ...)),
    'tag_relationships': dict(id_tags_source=(Text, ...), id_tags_target=(Text, ...)),
    'work_classifications': dict(work_classification_name=(Technical, ...), display_name_work_classifications=(Text, ...), description_work_classifications=(Text | None, None), tier=(PositiveInteger, None)),
    'watchlist_entries': dict(id_works=(Text, ...), id_work_availabilities=(Text | None, None),
        id_work_classifications_predicted=(Text | None, None), observations=(Text | None, None)),
    'watch_history': dict(id_works=(Text, ...), id_work_availabilities=(Text | None, None),
        id_work_classifications=(Text | None, None), observations=(Text | None, None), watched_at=(SourceInstant | None, None),
        watched_at_timezone=(ZoneName | None, None)),
    'work_tags': dict(id_works=(Text, ...), id_tags=(Text | None, None), id_tag_relationships=(Text | None, None),
        id_watchlist_entries=(Text | None, None), id_watch_history=(Text | None, None)),
}


def build_resource(table, fields):
    """Publish named input/record/query models with real enums and explicit filters."""
    title = ''.join(part.title() for part in table.split('_'))
    common = {'id_' + table: (Text, Field(description='Permanent database-generated ID; prefix plus at least seven digits.')),
              'sequence_' + table: (PositiveInteger, Field(description='Independent immutable BIGINT identity; gaps are allowed.')),
              'prefix_' + table: (Text, Field(description='Fixed immutable table prefix supplied by PostgreSQL.')),
              'fantasy_name_' + table: (Text, Field(description='Fixed immutable friendly table name, stored on every row.'))}
    automatic = {'created_at': (Instant | None, Field(default=None, description='Automatic UTC creation instant; unknown historical dates remain null. Immutable.')),
                 'created_at_timezone': (ZoneName | None, Field(default=None, description='Application IANA zone at creation; historical unknown context remains null. Immutable.'))}
    if table == 'watchlist_entries':
        automatic.update(added_at=(Instant, Field(description='Server-controlled watchlist-added instant; may be echoed unchanged.')),
                         added_at_timezone=(ZoneName | None, None))
    if table == 'watch_history':
        automatic['watched_at_offset'] = (Text | None, Field(default=None, description='Server-recorded input UTC offset; updated automatically when watched_at changes.'))
    described_fields = {name: (annotation, Field(default=default, description=(
        'Optional long English synopsis; language compliance is a content policy, not automatically detected.' if name == 'synopsis'
        else 'Editable completion instant with UTC offset; null means the historical completion date is unknown.' if name == 'watched_at'
        else 'Explicit IANA source zone; requires watched_at with a matching supplied offset. Never inferred from an offset.' if name == 'watched_at_timezone'
        else 'Positive unique classification position. Omit on POST to append; insert at 1 through N+1. Individual PUT moves within 1 through N. Null and booleans are rejected.' if name == 'tier'
        else 'Editable domain field; null is accepted only when the schema is nullable.')))
        for name, (annotation, default) in fields.items()}
    if table == 'work_classifications':
        # An omitted optional input appends, while explicit JSON null stays invalid.
        described_fields['tier'] = (PositiveInteger, Field(default_factory=lambda: None,
            description='Omit to append. Supply a positive position from 1 through N+1 to insert and shift following classifications.', examples=[1, 2]))
    create = create_model(title + 'Create', __base__=RecordInput, **described_fields)
    record_fields = dict(described_fields)
    if table == 'work_classifications':
        record_fields['tier'] = (PositiveInteger, Field(description='Independent required unique positive classification position; ordering never changes IDs or sequences.'))
    record = create_model(title + 'Record', __base__=RecordInput, **common, **record_fields, **automatic,
        presentation=(Presentation, Field(description='Read-only date/time display, separate from canonical UTC instants.', json_schema_extra={'readOnly': True})))
    update_fields = {name: (annotation, Field(default=None, description=(
        'Immutable/server-controlled: omit or echo the current value unchanged.' if name in {**common, **automatic}
        else 'Omit to preserve; supplied null is allowed only for nullable fields.')))
                     for name, (annotation, _) in {**common, **fields, **automatic}.items()}
    update_fields['presentation'] = (Presentation, Field(default=None, description='May echo the unchanged GET presentation; it is never a mutable field.', json_schema_extra={'readOnly': True}))
    update = create_model(title + 'Update', __base__=UpdateInput, **update_fields)
    columns = tuple({**common, **fields, **automatic})
    filters = {}
    for name, (annotation, _) in {**common, **fields, **automatic}.items():
        if name.startswith(('id_', 'sequence_', 'prefix_', 'fantasy_name_')) or name.endswith('_name'):
            description = 'Optional exact match; combined with all supplied filters using AND.'
            example = 'WK0000001' if name.startswith('id_') else 'example'
            filter_type = int if name.startswith('sequence_') else str
        elif annotation is StrictBool:
            description, example, filter_type = 'Optional exact boolean match (true or false).', True, bool
        elif name in ('price_amount', 'duration_minutes'):
            description, example, filter_type = 'Optional exact finite decimal match within the field numeric limits.', '12.5', Price if name == 'price_amount' else Duration
        elif name in ('episode_quantity', 'tier'):
            description, example, filter_type = 'Optional exact positive integer match.', 2, Annotated[int, BeforeValidator(integer_query), Field(gt=0, le=9223372036854775807)]
        elif name in ('watched_at', 'added_at', 'created_at'):
            description, example, filter_type = 'Optional exact timezone-aware instant; equivalent offsets compare equally.', '2026-10-19T12:00:00Z', Instant
        elif name.endswith(('_timezone', '_offset')):
            description, example, filter_type = 'Optional exact recorded source context.', 'Europe/Lisbon' if name.endswith('_timezone') else '+01:00', str
        else:
            description, example, filter_type = PATTERN_HELP, '%Ouroboros%', str
        # Only defined technical names are exact. Human platform names use ILIKE.
        if name == 'platform_name':
            description, example, filter_type = PATTERN_HELP, '%Library%', str
        if name.startswith('sequence_'):
            filter_type, example = Annotated[int, BeforeValidator(integer_query), Field(gt=0, le=9223372036854775807)], 1
        filters[name] = (filter_type | None, Field(default=None, description=description, examples=[example]))
    for field in ('created_at', 'added_at', 'watched_at'):
        if field in columns:
            filters.update(date_filter_fields(field))
    bulk_query = create_model(title + 'BulkFilters', __base__=BulkSelection, **filters)
    bulk_fields = {name: (annotation, Field(default=None, description='Supplied mutable fields only; omitted fields are preserved.')) for name, (annotation, _) in fields.items()}
    if table == 'work_classifications':
        bulk_fields.pop('tier')
    bulk_update = create_model(title + 'BulkUpdate', __base__=ClassificationBulkUpdate if table == 'work_classifications' else UpdateInput, **bulk_fields)
    default_order = 'tier' if table == 'work_classifications' else 'sequence_' + table
    filters.update(display_timezone=(DisplayZone | None, Field(default=None, description='IANA display zone or original; default is configured display timezone. Canonical timestamps stay UTC.', examples=['Europe/Lisbon', 'original'])),
        page=(Annotated[int, BeforeValidator(integer_query), Field(ge=1)], Field(default=1, description='One-based page after filtering and ordering.', examples=[1, 2])),
        page_size=(Annotated[int, BeforeValidator(integer_query), Field(ge=10, le=50)], Field(default=50, description='10–50 items; count precedes pagination.', examples=[50, 10])),
        order_by=(Literal[columns], Field(default=default_order, description='Any public stored scalar field; ties use permanent ID ascending.', examples=[default_order])),
        order_direction=(Literal['asc', 'desc'], Field(default='asc', description='NULL values always sort last.', examples=['asc', 'desc'])))
    query = create_model(title + 'Filters', __base__=Selection, **filters)
    pattern_fields = tuple(name for name in columns if query.model_fields[name].description == PATTERN_HELP)
    return Resource(table, fields, create, update, record, query, columns, tuple(common) + tuple(automatic), pattern_fields, bulk_query, bulk_update,
                    collection_record(table, record))


RESOURCES = {table: build_resource(table, fields) for table, fields in CONTRACTS.items()}


class BulkResult(BaseModel):
    """Bounded summary: preview counts can change before an actual execution."""
    matched_count: int
    updated_count: int | None = None
    deleted_count: int | None = None
    dry_run: bool
    summary: str
