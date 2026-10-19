"""One mutable server-owned audit context shared with AnyIO worker copies."""
from contextvars import ContextVar
from dataclasses import dataclass, field


@dataclass
class AuditContext:
    interaction_id: str
    application_timezone: str = 'Europe/Lisbon'
    audit_id: str | None = None
    actor_id: int | None = None
    actor_username: str | None = None
    actor_role: str | None = None
    error_code: str | None = None
    bulk: bool = False
    resource: str | None = None
    target_id: str | None = None
    sensitive: bool = False
    mutation_limit: int = 8192
    mutation_details: dict = field(default_factory=dict)


audit_context = ContextVar('ouroboros_audit_context', default=None)


def authenticated_actor(user):
    """Retain verified identity only, never credentials or an unverified JWT role."""
    context = audit_context.get()
    if context is not None:
        from app.audit_privacy import safe_path
        context.actor_id, context.actor_username, context.actor_role = user.id, safe_path(user.username), user.role


def bulk_context(resource, filters, changes=None):
    """Mark bounded bulk intent before acquiring the business transaction."""
    context = audit_context.get()
    if context is not None:
        from app.audit_privacy import bounded_value
        context.bulk, context.resource = True, resource
        value, flags = bounded_value({'filters': filters, 'intended_changes': changes}, context.mutation_limit)
        context.mutation_details = value if value is not None else {'capture': flags, 'changed_fields': list(changes or {})}


def operation_evidence(cursor, resource, details, outcome):
    """Persist a bounded bulk/preview summary in its transaction, including zero matches."""
    context = audit_context.get()
    if context is None:
        return
    if context.audit_id is None:
        if outcome == 'preview':
            return
        from app.errors import AuditUnavailable
        raise AuditUnavailable('Mandatory audit unavailable')
    from psycopg.types.json import Jsonb
    context.mutation_details.update(details)
    context.mutation_details = bounded_mutation_details(context.mutation_details, context.mutation_limit)
    import psycopg
    from app.errors import AuditUnavailable
    try:
        cursor.execute('''UPDATE public.api_audit_logs SET resource=%s, mutation_details=%s,
            business_outcome=%s, operation_summary=%s WHERE id_api_audit_logs=%s''',
            (resource, Jsonb(context.mutation_details), outcome, ('Preview ' if outcome == 'preview' else
                'Reorder ' if 'reordering' in context.mutation_details else 'Bulk ') + resource, context.audit_id))
    except psycopg.Error:
        raise AuditUnavailable('Mandatory audit unavailable') from None
    if cursor.rowcount != 1:
        from app.errors import AuditUnavailable
        raise AuditUnavailable('Mandatory audit unavailable')


def bounded_mutation_details(details, limit):
    """Bound final summaries after counts are added, retaining core reorder facts.

    Samples and submitted text are optional evidence. Moved IDs, tiers and
    affected counts take priority at the smallest supported capture limit.
    """
    from app.audit_privacy import bounded_value
    value, flags = bounded_value(details, limit)
    if value is not None:
        return value
    compact = {key: details[key] for key in ('matched_count', 'applied_count', 'dry_run') if key in details}
    compact['details_omitted'] = True
    ordering = details.get('reordering')
    if isinstance(ordering, dict):
        compact['reordering'] = {key: ordering[key] for key in ('action', 'moved', 'shifted_count', 'affected_count') if key in ordering}
        compact['reordering']['shifted_records_omitted'] = True
    value, flags = bounded_value(compact, limit)
    if value is not None:
        return value
    if isinstance(ordering, dict):
        compact['reordering'].pop('action', None)
        compact['reordering'].pop('shifted_count', None)
        value, flags = bounded_value(compact, limit)
        if value is not None:
            return value
    return {'details_omitted': True}
