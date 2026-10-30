"""Shared object/array creation contracts and safe indexed failure reporting."""
from contextlib import contextmanager
from typing import Annotated, Generic, TypeVar

from fastapi import Body
from pydantic import BaseModel, Field, TypeAdapter, WrapValidator
from pydantic_core import PydanticCustomError
from psycopg import errors

Record = TypeVar('Record')

CREATION_EXAMPLES = {
    'works': {'title': 'Example', 'title_language': 'en'},
    'platforms': {'platform_name': 'Example', 'platform_is_paid': False,
                  'platform_is_episodes': True, 'platform_is_duration_time': True,
                  'platform_access_types': ['application', 'website'], 'platform_url': 'https://example.org/catalogue',
                  'price_amount': None, 'price_currency': None},
    'work_availabilities': {'id_works': 'WK0000001', 'id_platforms': 'PL0000001'},
    'tags': {'tag_name': 'example', 'display_name_tags': 'Example', 'description_tags': 'Example description.'},
    'tag_categories': {'tag_category_name': 'example', 'display_name_tag_categories': 'Example'},
    'tag_category_relationships': {'id_tags': 'TG0000001', 'id_tag_categories': 'TC0000001'},
    'tag_relationships': {'id_tags_source': 'TG0000001', 'id_tags_target': 'TG0000002'},
    'work_classifications': {'work_classification_name': 'example', 'display_name_work_classifications': 'Example',
                             'description_work_classifications': 'A work-rating category, independent of tag categories.'},
    'watchlist_entries': {'id_works': 'WK0000001'},
    'watch_history': {'id_works': 'WK0000001', 'watched_at': None},
    'work_tags': {'id_works': 'WK0000001', 'id_tags': 'TG0000001'},
    'test': {'value': 'Example'},
}


class CreatedBatch(BaseModel, Generic[Record]):
    """An ordered mutation result, not a paginated collection."""
    created_count: int = Field(ge=1, description='Number created atomically in this request.')
    items: list[Record] = Field(description='Full persisted records in request order, with final metadata.')


def creation_body(schema, example):
    """Dispatch validation by JSON shape while preserving plain item locations."""
    batch_type = Annotated[list[schema], Field(min_length=1)]
    adapter = TypeAdapter(batch_type)

    def validate(value, handler):
        if isinstance(value, list):
            if not value:
                raise PydanticCustomError('batch_empty', 'Supply at least one object in the array')
            return adapter.validate_python(value)
        if isinstance(value, dict):
            return schema.model_validate(value)
        raise PydanticCustomError('creation_shape', 'Supply an object or a nonempty array of objects')

    second = {key: ('Second example' if key in ('title', 'platform_name', 'value') or key.startswith('display_name_')
                    else value + '_second' if key in ('tag_name', 'tag_category_name', 'work_classification_name')
                    else 'TG0000003' if key == 'id_tags'
                    else 'TG0000004' if key == 'id_tags_target'
                    else value) for key, value in example.items()}
    examples = {'single': {'summary': 'Create one record', 'value': example},
                'batch': {'summary': 'Create an ordered atomic batch', 'value': [example, second]}}
    if 'work_classification_name' in example:
        examples['insert_at_tier'] = {'summary': 'Insert at tier 1; omitted tier appends', 'value': {**example, 'tier': 1}}
    return Annotated[schema | batch_type, WrapValidator(validate), Body(
        description='One object returns one record. An array creates atomically and returns created_count/items in request order. '
                    'Default maximum 300 items; configured api.max_batch_size applies. Error item indexes are zero-based.',
        openapi_examples=examples)]


def check_batch_size(payload, config):
    """Check the configured item budget before acquiring any business connection."""
    if isinstance(payload, list) and len(payload) > config.get('api', {}).get('max_batch_size', 300):
        from app.catalogue_repository import CatalogueError
        raise CatalogueError(422, 'Batch exceeds configured item limit', details=[{
            'loc': ['body'], 'type': 'batch_too_large', 'msg': 'Array exceeds configured api.max_batch_size.'}])


@contextmanager
def creation_item(index):
    """Translate expected database/domain failures without exposing input or SQL."""
    from app.catalogue_repository import CatalogueError
    from app.classification_ordering import TierPositionError
    try:
        yield
    except CatalogueError as error:
        if error.status not in (409, 422):
            raise
        status, details = error.status, error.details
    except TierPositionError as error:
        status, details = 422, error.details
    except (errors.ForeignKeyViolation, errors.UniqueViolation):
        status, details = 409, None
    except (errors.CheckViolation, errors.NotNullViolation, errors.GeneratedAlways,
            errors.NumericValueOutOfRange, errors.InvalidTextRepresentation, ValueError):
        status, details = 422, None
    else:
        return
    details = details or [{'loc': ['body'], 'type': 'creation_item_conflict' if status == 409 else 'creation_item_invalid',
                           'msg': 'This item violates a field or relationship rule; the entire array was rolled back.'}]
    indexed = [{**detail, 'loc': ['body', index, *detail.get('loc', [])[1:]]} for detail in details]
    raise CatalogueError(status, 'Array creation failed; no items were committed', details=indexed) from None


def batch_context(resource, count):
    """Suppress per-record diffs while mandatory row triggers retain mutation counts."""
    from app.audit_context import audit_context
    state = audit_context.get()
    if state is not None:
        state.bulk, state.resource, state.target_id = True, resource, None
        state.mutation_details = {'operation': 'batch_create', 'requested_count': count}


def batch_evidence(cursor, resource, records, key, shifted_count=0, shifted_records=None):
    """Save counts and a bounded ID sample in the same transaction as every insert."""
    from app.audit_context import operation_evidence
    details = {
        'operation': 'batch_create', 'created_count': len(records),
        'created_ids': [record[key] for record in records[:20]],
        'created_ids_omitted': len(records) > 20, 'shifted_count': shifted_count}
    if shifted_records is not None:
        details['reordering'] = {'action': 'batch_insert', 'affected_count': len(records) + shifted_count,
            'shifted_count': shifted_count, 'shifted_records': shifted_records,
            'shifted_records_omitted': shifted_count > len(shifted_records)}
    operation_evidence(cursor, resource, details, 'committed')
