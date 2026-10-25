"""Supervisor/administrator audit reads; audit facts have no public write route."""
from typing import Annotated
from fastapi import APIRouter, Query, Request, Security
from app.auth import require_scopes
from app.audit_repository import AuditRepository
from app.audit_context import audit_context
from app.datetimes import DisplayZone, present
from app.pagination import Page
from app.schemas.audit import AuditFilters, AuditRecord

router = APIRouter(prefix='/api_audit_logs', tags=['api_audit_logs'])
Reader = Annotated[dict, Security(require_scopes, scopes=['catalogue:access'])]


def representation(record, request, selection):
    return present(record, selection, request.app.state.config.get('default_display_timezone','Europe/Lisbon'),
                   {'started_at':'UTC', 'finished_at':'UTC'})


@router.get('', response_model=Page[AuditRecord])
def collection(request: Request, actor: Reader, selection: Annotated[AuditFilters, Query()]):
    """Read sanitized audit metadata; returned audit bodies are not re-audited."""
    selection.bind_filter_timezone(request.app.state.config)
    result = AuditRepository(request.app.state.database).page(selection)
    result['items'] = [representation(record, request, selection.display_timezone) for record in result['items']]
    if audit_context.get() is not None:
        audit_context.get().mutation_details = {'returned_count': len(result['items']), 'matched_count': result['count']}
    return result


@router.get('/{id}', response_model=AuditRecord)
def read(id: str, request: Request, actor: Reader,
         display_timezone: Annotated[DisplayZone | None, Query(description='Read-only IANA display zone or original; canonical audit clocks stay UTC.', examples=['Europe/Lisbon','original'])] = None):
    """Read one historical request without copying it into the access audit body."""
    result = representation(AuditRepository(request.app.state.database).read(id), request, display_timezone)
    if audit_context.get() is not None:
        audit_context.get().mutation_details = {'returned_count': 1}
    return result
