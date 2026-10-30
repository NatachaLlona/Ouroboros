"""Complete protected CRUD for the inherited integer-ID test resource."""
from typing import Annotated

from fastapi import APIRouter, Path, Query, Request, Response, Security

from app.auth import require_scopes
from app.database_test import TestRepository, page_entries
from app.datetimes import DisplayZone, present
from app.logger import log_event
from app.pagination import Page
from app.schemas.catalogue import BulkResult
from app.schemas.test import (QueryID, TestBulkQuery, TestBulkUpdate, TestCreate,
                              TestEntry, TestQuery, TestUpdate)
from app.creation import CREATION_EXAMPLES, CreatedBatch, check_batch_size, creation_body

router = APIRouter(prefix='/test', tags=['test'])
TestReader = Annotated[dict, Security(require_scopes, scopes=['test:read'])]
TestWriter = Annotated[dict, Security(require_scopes, scopes=['test:write'])]
Administrator = Annotated[dict, Security(require_scopes, scopes=['users:manage'])]
EntryID = Annotated[QueryID, Path(description='Permanent positive integer ID. No catalogue prefix.', examples=[1])]
Display = Annotated[DisplayZone | None, Query(description='IANA display zone or original. Canonical timestamps stay UTC.', examples=['Europe/Lisbon', 'original'])]


def representation(record, request, display):
    return present(record, display, request.app.state.config.get('default_display_timezone', 'Europe/Lisbon'))


@router.post('', response_model=TestEntry | CreatedBatch[TestEntry], status_code=201)
def create_entry(payload: creation_body(TestCreate, CREATION_EXAMPLES['test']),
                 request: Request, actor: TestWriter, display_timezone: Display = None):
    """Create one object or an atomic array; arrays return a mutation result, not a page."""
    log_event('DEBUG', 'Request validation completed')
    check_batch_size(payload, request.app.state.config)
    if isinstance(payload, list):
        results = TestRepository(request.app.state.database).create_many(payload, actor)
        log_event('INFO', 'Test batch created', {'created_count': len(results)})
        return {'created_count': len(results), 'items': [representation(row, request, display_timezone) for row in results]}
    result = TestRepository(request.app.state.database).create(payload, actor)
    log_event('INFO', 'Test entry created', {'entry_id': result['id']})
    return representation(result, request, display_timezone)


@router.get('', response_model=Page[TestEntry])
def get_entries(request: Request, actor: TestReader, selection: Annotated[TestQuery, Query()]):
    """Apply strict AND filters, then whitelisted ordering and SQL pagination."""
    log_event('DEBUG', 'Request validation completed')
    selection.bind_filter_timezone(request.app.state.config)
    values = selection.model_dump(exclude={'display_timezone'})
    values['entry_id'] = values.pop('id')
    with request.app.state.database.connection() as connection:
        result = page_entries(connection, **values)
    result['items'] = [representation(record, request, selection.display_timezone) for record in result['items']]
    log_event('INFO', 'Test entries retrieved', {'row_count': len(result['items']), 'count': result['count']})
    return result


@router.get('/{id}', response_model=TestEntry)
def read_entry(id: EntryID, request: Request, actor: TestReader, display_timezone: Display = None):
    """Read the complete record for copying to individual PUT."""
    result = TestRepository(request.app.state.database).read(id)
    log_event('INFO', 'Test entry retrieved', {'entry_id': id})
    return representation(result, request, display_timezone)


@router.put('/{id}', response_model=TestEntry)
def update_entry(id: EntryID, payload: TestUpdate, request: Request, actor: TestWriter, display_timezone: Display = None):
    """Omissions preserve fields; immutable fields and presentation may echo unchanged."""
    result = TestRepository(request.app.state.database).update(id, payload, actor)
    log_event('INFO', 'Test entry updated', {'entry_id': id})
    return representation(result, request, display_timezone)


@router.delete('/{id}', status_code=204, response_class=Response)
def delete_entry(id: EntryID, request: Request, actor: TestWriter):
    """Delete one integer ID without resetting its sequence; absent records are 404."""
    TestRepository(request.app.state.database).delete(actor, id)
    log_event('INFO', 'Test entry deleted', {'actor_id': int(actor['sub']), 'entry_id': id, 'deleted_count': 1, 'outcome': 'committed'})
    return Response(status_code=204)


@router.put('', response_model=BulkResult, response_model_exclude_none=True)
def bulk_update(payload: TestBulkUpdate, request: Request, actor: Administrator,
                selection: Annotated[TestBulkQuery, Query()]):
    """Administrator-only filtered PUT. Preview with dry_run=true; execute with confirm=true.

    All matching rows are targeted without pagination. Unknown filters, sorting,
    display controls and immutable body fields are rejected.
    """
    selection.bind_filter_timezone(request.app.state.config)
    result = TestRepository(request.app.state.database).bulk(actor, selection, payload)
    log_event('INFO', 'Test bulk previewed' if result['dry_run'] else 'Test bulk updated', {'actor_id': int(actor['sub']), **result})
    return result


@router.delete('', response_model=BulkResult, response_model_exclude_none=True)
def bulk_delete(request: Request, actor: Administrator, selection: Annotated[TestBulkQuery, Query()]):
    """Administrator-only filtered DELETE; no filters selects every row.

    Preview with dry_run=true or explicitly confirm=true for atomic execution.
    There is no TRUNCATE, cascade, page limit or sequence reset.
    """
    selection.bind_filter_timezone(request.app.state.config)
    result = TestRepository(request.app.state.database).bulk(actor, selection)
    log_event('INFO', 'Test bulk previewed' if result['dry_run'] else 'Test records deleted', {'actor_id': int(actor['sub']), **result})
    return result
