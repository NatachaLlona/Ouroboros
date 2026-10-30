"""Read-only public audit schemas and strictly allowlisted query controls."""
from decimal import Decimal
from typing import Any, Literal, Annotated
from pydantic import BaseModel, ConfigDict, Field, BeforeValidator
from app.datetimes import Instant, DisplayZone, CalendarDate, DateBound, date_filter_fields
from app.pagination import integer_query
from app.schemas.catalogue import Presentation, Selection

AuditStatus = Literal['in_progress', 'success', 'failure']
BusinessOutcome = Literal['not_started','committed','rolled_back','read_only','preview']
AUDIT_COLUMNS = ('id_api_audit_logs','sequence_api_audit_logs','prefix_api_audit_logs','fantasy_name_api_audit_logs',
    'interaction_id','started_at','finished_at','duration_ms','status','method','path','matched_route','http_status',
    'response_started','error_code','actor_id','actor_username','actor_role','request_query','request_body','response_body',
    'resource','target_id','differences','operation_summary','capture','business_outcome','mutation_count','mutation_details')
JSON_FIELDS = ('request_query','request_body','response_body','differences','capture','mutation_details')
AUDIT_ORDER = tuple(field for field in AUDIT_COLUMNS if field not in JSON_FIELDS)


class AuditRecord(BaseModel):
    """Sanitized server-owned evidence; no credential columns or write endpoints."""
    id_api_audit_logs: str
    sequence_api_audit_logs: int
    prefix_api_audit_logs: Literal['AL']
    fantasy_name_api_audit_logs: Literal['Auditoria de APIs']
    interaction_id: str
    started_at: Instant
    finished_at: Instant | None
    duration_ms: Decimal | None
    status: AuditStatus
    method: str
    path: str
    matched_route: str | None
    http_status: int | None
    response_started: bool
    error_code: str | None
    actor_id: int | None
    actor_username: str | None
    actor_role: str | None
    request_query: Any
    request_body: Any
    response_body: Any
    resource: str | None
    target_id: str | None
    differences: Any
    operation_summary: str
    capture: dict
    business_outcome: BusinessOutcome
    mutation_count: int
    mutation_details: Any
    presentation: Presentation


class AuditFilters(Selection):
    """All audit criteria are values, never SQL identifiers or write instructions."""
    model_config = ConfigDict(extra='forbid')
    interaction_id: str | None = Field(default=None, description='Exact server interaction ID, also returned in X-Interaction-ID.', examples=['202610191200001234567890'])
    actor_id: Annotated[int | None, BeforeValidator(integer_query), Field(gt=0, le=9223372036854775807)] = Field(default=None, description='Exact historical actor ID; no account FK.', examples=[1])
    actor_username: str | None = Field(default=None, description='Exact authenticated username snapshot.', examples=['qa_supervisor'])
    started_at_date: CalendarDate | None = date_filter_fields('started_at')['started_at_date'][1]
    started_at_from: DateBound | None = date_filter_fields('started_at')['started_at_from'][1]
    started_at_to: DateBound | None = date_filter_fields('started_at')['started_at_to'][1]
    finished_at_date: CalendarDate | None = date_filter_fields('finished_at')['finished_at_date'][1]
    finished_at_from: DateBound | None = date_filter_fields('finished_at')['finished_at_from'][1]
    finished_at_to: DateBound | None = date_filter_fields('finished_at')['finished_at_to'][1]
    method: str | None = Field(default=None, description='Exact HTTP method snapshot.', examples=['GET', 'PUT'])
    resource: str | None = Field(default=None, description='Exact catalogue/infrastructure resource name.', examples=['works'])
    status: AuditStatus | None = Field(default=None, description='Request status; handled 4xx count as failure.', examples=['failure'])
    http_status: Annotated[int | None, BeforeValidator(integer_query), Field(ge=100, le=599)] = Field(default=None, description='Exact status accepted by the server send callback; unknown status is null.', examples=[422])
    error_code: str | None = Field(default=None, description='Exact stable code from the versioned error catalogue.', examples=['VALIDATION_ERROR'])
    target_id: str | None = Field(default=None, description='Exact individual target ID; bulk operations have no individual target.', examples=['WK0000001'])
    page: Annotated[int, BeforeValidator(integer_query), Field(ge=1)] = Field(default=1, description='One-based page, after filtering and ordering.', examples=[1])
    page_size: Annotated[int, BeforeValidator(integer_query), Field(ge=10, le=50)] = Field(default=50, description='10–50 items, count before pagination.', examples=[50, 10])
    order_by: Literal[AUDIT_ORDER] = Field(default='sequence_api_audit_logs', description='Public stored scalar column; JSON/presentation fields are not sortable.', examples=['started_at'])
    order_direction: Literal['asc','desc'] = Field(default='asc', description='NULLS LAST in both directions; unique audit ID ascending tie-breaker.', examples=['asc','desc'])
    display_timezone: DisplayZone | None = Field(default=None, description='Configured display zone by default, explicit IANA zone or original (UTC for audit clocks).', examples=['Europe/Lisbon','original'])
