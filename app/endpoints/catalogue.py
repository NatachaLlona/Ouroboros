"""Individual CRUD and confirmed bulk routes for each fixed catalogue resource."""
from typing import Annotated
from fastapi import APIRouter, Query, Request, Response, Security

from app.auth import require_scopes
from app.catalogue_repository import CatalogueError, CatalogueRepository
from app.logger import log_event
from app.pagination import Page
from app.schemas.catalogue import BulkResult, RESOURCES
from app.datetimes import DisplayZone, present
from app.creation import CREATION_EXAMPLES, CreatedBatch, check_batch_size, creation_body

CatalogueActor = Annotated[dict, Security(require_scopes, scopes=['catalogue:access'])]
Administrator = Annotated[dict, Security(require_scopes, scopes=['users:manage'])]
Display = Annotated[DisplayZone | None, Query(description='Read-only presentation zone: IANA name or original. Default comes from configuration; canonical timestamps remain UTC.', examples=['Europe/Lisbon', 'original'])]


def resource_router(resource):
    """Bind real named schemas to a fixed resource's seven endpoint forms."""
    router = APIRouter(prefix='/' + resource.table, tags=[resource.table])

    def repository(request):
        return CatalogueRepository(request.app.state.database, resource)

    def representation(record, request, display):
        return present(record, display, request.app.state.config.get('default_display_timezone', 'Europe/Lisbon'))

    @router.post('', status_code=201, response_model=resource.record | CreatedBatch[resource.record])
    def create(payload: creation_body(resource.create, CREATION_EXAMPLES[resource.table]),
               request: Request, actor: CatalogueActor, display_timezone: Display = None):
        """Create one object or an atomic ordered array with the same permissions.

        Array results are mutation results, not paginated GET collections. No
        implicit references between items or cross-table creation are supported.
        """
        check_batch_size(payload, request.app.state.config)
        if isinstance(payload, list):
            results = repository(request).create_many(payload, actor)
            log_event('INFO', 'Catalogue batch created', {'resource': resource.table, 'created_count': len(results)})
            return {'created_count': len(results), 'items': [representation(row, request, display_timezone) for row in results]}
        return representation(repository(request).create(payload, actor), request, display_timezone)

    @router.get('', response_model=Page[resource.list_record])
    def collection(request: Request, actor: CatalogueActor, selection: Annotated[resource.query, Query()]):
        """Filter with AND, then order and paginate in one database snapshot."""
        selection.bind_filter_timezone(request.app.state.config)
        result = repository(request).page(selection)
        result['items'] = [representation(record, request, selection.display_timezone) for record in result['items']]
        return result

    @router.get('/{id}', response_model=resource.record)
    def read(id: str, request: Request, actor: CatalogueActor, display_timezone: Display = None):
        """Fetch a full persisted record, suitable for copying to PUT."""
        return representation(repository(request).read(id), request, display_timezone)

    @router.put('/{id}', response_model=resource.record)
    def update(id: str, payload: resource.update, request: Request, actor: CatalogueActor, display_timezone: Display = None):
        """Update supplied fields atomically; omit to preserve, null to clear nullable fields.

        A full GET record may be echoed with unchanged metadata/added_at. Changes
        to those fields, unknown properties and empty objects return 422. watched_at
        remains editable. The resulting full record must satisfy all constraints.
        """
        return representation(repository(request).update(id, payload, actor), request, display_timezone)

    def remove(request, actor, record_id=None):
        audit = dict(actor_id=int(actor['sub']), resource=resource.table, target_id=record_id)
        try:
            count = repository(request).delete(actor, record_id)
        except CatalogueError as error:
            log_event('WARNING', 'Catalogue deletion rejected', {**audit, 'outcome': 'rejected', 'status': error.status})
            raise
        log_event('INFO', 'Catalogue records deleted', {**audit, 'deleted_count': count, 'outcome': 'committed'})
        return count

    @router.delete('/{id}', status_code=204, response_class=Response)
    def delete_one(id: str, request: Request, actor: CatalogueActor):
        """Delete one unreferenced record; dependencies return 409, missing ID 404."""
        remove(request, actor, id)
        return Response(status_code=204)

    @router.put('', response_model=BulkResult, response_model_exclude_none=True)
    def bulk_update(payload: resource.bulk_update, request: Request, actor: Administrator,
                    selection: Annotated[resource.bulk_query, Query()]):
        """Administrator-only filtered PUT. Preview with dry_run=true; confirm=true executes.

        No page/order/display parameters are accepted. All matching rows are
        targeted atomically, including unchanged values in updated_count.
        """
        selection.bind_filter_timezone(request.app.state.config)
        result = repository(request).bulk(actor, selection, payload)
        log_event('INFO', 'Catalogue bulk previewed' if result['dry_run'] else 'Catalogue bulk updated',
                  {'actor_id':int(actor['sub']), 'resource':resource.table, **result})
        return result

    @router.delete('', response_model=BulkResult, response_model_exclude_none=True)
    def bulk_delete(request: Request, actor: Administrator, selection: Annotated[resource.bulk_query, Query()]):
        """Administrator-only filtered DELETE; no filters targets the whole resource.

        dry_run=true previews matched_count without confirmation. Actual execution
        requires confirm=true and is atomic on dependencies; no cascades/resets.
        """
        audit = {'actor_id':int(actor['sub']), 'resource':resource.table, 'target_id':None}
        try:
            selection.bind_filter_timezone(request.app.state.config)
            result = repository(request).bulk(actor, selection)
        except CatalogueError as error:
            log_event('WARNING','Catalogue deletion rejected',{**audit,'outcome':'rejected','status':error.status})
            raise
        log_event('INFO', 'Catalogue bulk previewed' if result['dry_run'] else 'Catalogue records deleted',
                  {**audit, **result, 'outcome':'preview' if result['dry_run'] else 'committed'})
        return result

    return router


routers = [resource_router(resource) for resource in RESOURCES.values()]
