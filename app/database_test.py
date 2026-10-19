"""Parameterized test queries and transactional integer-ID CRUD persistence."""
from contextlib import contextmanager

from psycopg import errors, sql

from app.audit_context import audit_context, bulk_context, operation_evidence
from app.catalogue_repository import CatalogueError
from app.collection_queries import select_page, template, where_clause
from app.datetimes import present
from app.errors import AuditUnavailable
from app.logger import log_event
from app.config import PROJECT_ROOT

QUERY_DIRECTORY = PROJECT_ROOT / "sql" / "queries"
TEST_COLUMNS = ('id', 'value', 'created_at', 'created_at_timezone')


def query(name):
    return (QUERY_DIRECTORY / name).read_text(encoding="utf-8")


def insert_entry(connection, value):
    """Insert an unchanged value in the caller's transaction and return its ID."""
    log_event("DEBUG", "Database query started", component="database_test")
    with connection.cursor() as cursor:
        cursor.execute(query("insert_test.sql"), (value,))
        result = cursor.fetchone()[0]
        log_event("DEBUG", "Insert query completed", component="database_test")
        return result


def read_entry(connection, entry_id):
    """Read one test row by immutable ID without owning the transaction."""
    log_event("DEBUG", "Database query started", component="database_test")
    with connection.cursor() as cursor:
        cursor.execute(query("read_test.sql"), (entry_id,))
        result = cursor.fetchone()
        log_event("DEBUG", "Read query completed", component="database_test")
        return result


def list_entries(connection, entry_id=None, value=None):
    """Read legacy unbounded rows for internal callers; APIs use page_entries."""
    log_event("DEBUG", "Database query started", component="database_test")
    with connection.cursor() as cursor:
        cursor.execute(query("list_test.sql"), (entry_id, entry_id, value, value))
        result = cursor.fetchall()
        log_event("DEBUG", "List query completed", {"row_count": len(result)}, component="database_test")
        return result


def page_entries(connection, entry_id=None, value=None, page=1, page_size=50, order_by='id', order_direction='asc',
                 created_at=None, created_at_timezone=None, created_at_from=None, created_at_to=None):
    """Read a count and SQL-bounded page in one statement snapshot.

    Args:
        connection: Caller-owned transaction connection.
        entry_id: Optional exact ID filter.
        value: Optional unmodified ILIKE pattern.
        page: Validated one-based page number.
        page_size: Validated page size, from 10 through 50.
        order_by: Whitelisted public stored scalar field.
        order_direction: asc or desc, with NULLS LAST and ID tie-breaks.

    Returns:
        A pagination envelope preserving the filtered count on empty pages.
    """
    return select_page(connection, 'test', TEST_COLUMNS, 'id',
        test_filters(dict(id=entry_id, value=value, created_at=created_at, created_at_timezone=created_at_timezone,
                          created_at_from=created_at_from, created_at_to=created_at_to)),
        page, page_size, order_by, order_direction)


def test_filters(values):
    """Use the same trusted predicate for GET, previews and confirmed mutations."""
    return [(name, 'ILIKE' if name == 'value' else '=', values.get(name)) for name in TEST_COLUMNS] + [
        ('created_at', '>=', values.get('created_at_from')), ('created_at', '<', values.get('created_at_to'))]


def lock_test_actor(cursor, actor, administrator=False):
    """Recheck current account and token scope under membership then actor locks."""
    cursor.execute('SELECT pg_advisory_xact_lock(%s)', (719230818,))
    cursor.execute('SELECT role, is_active, credential_version, scopes FROM public.api_users WHERE id=%s FOR UPDATE',
                   (int(actor['sub']),))
    current = cursor.fetchone()
    if current is None or not current[1] or current[2] != actor['credential_version']:
        raise CatalogueError(401, 'Invalid or expired access token')
    if current[0] == 'administrator':
        return
    if (administrator or current[0] not in ('standard', 'supervisor')
            or 'test:write' not in current[3] or 'test:write' not in actor['scopes']):
        raise CatalogueError(403, 'Current test write permission or administrator access required')


class TestRepository:
    """Own business transactions and preserve central transactional audit hooks."""
    def __init__(self, database):
        self.database = database

    def statement(self, filename, **parts):
        """Only fixed server-owned identifiers enter composable SQL."""
        return template(filename).format(table=sql.Identifier('test'), key=sql.Identifier('id'),
            columns=sql.SQL(', ').join(map(sql.Identifier, TEST_COLUMNS)), **parts)

    @staticmethod
    def mapped(row):
        return dict(zip(TEST_COLUMNS, row)) if row is not None else None

    @contextmanager
    def writing(self, actor, administrator=False, preview=False):
        """Lock/revalidate before all writes; missing audit fails closed."""
        state = audit_context.get()
        if state is not None and state.audit_id is None and not preview:
            raise AuditUnavailable('Mandatory audit unavailable')
        try:
            with self.database.connection() as connection, connection.cursor() as cursor:
                lock_test_actor(cursor, actor, administrator)
                yield cursor
        except (errors.CheckViolation, errors.NotNullViolation, errors.GeneratedAlways,
                errors.NumericValueOutOfRange, errors.InvalidTextRepresentation):
            raise CatalogueError(422, 'Invalid resulting test record or immutable creation metadata') from None
        except (errors.ForeignKeyViolation, errors.UniqueViolation):
            raise CatalogueError(409, 'A dependency prevents the complete test operation') from None

    def create(self, payload, actor):
        with self.writing(actor) as cursor:
            cursor.execute(self.statement('catalogue_insert.sql', fields=sql.Identifier('value'), values=sql.Placeholder()),
                           (payload.value,))
            result = self.mapped(cursor.fetchone())
        return result

    def read(self, entry_id):
        with self.database.connection() as connection, connection.cursor() as cursor:
            cursor.execute(self.statement('catalogue_read.sql', lock=sql.SQL('')), (entry_id,))
            result = self.mapped(cursor.fetchone())
        if result is None:
            raise CatalogueError(404, 'Test entry not found')
        return result

    def update(self, entry_id, payload, actor):
        supplied = payload.model_dump(exclude_unset=True)
        with self.writing(actor) as cursor:
            cursor.execute(self.statement('catalogue_read.sql', lock=sql.SQL('FOR UPDATE')), (entry_id,))
            current = self.mapped(cursor.fetchone())
            if current is None:
                raise CatalogueError(404, 'Test entry not found')
            for field in ('id', 'created_at', 'created_at_timezone'):
                if field in supplied and supplied[field] != current[field]:
                    raise CatalogueError(422, 'Immutable test metadata cannot be changed')
            if 'presentation' in supplied:
                echoed = supplied['presentation']
                if echoed != present(current, echoed['display_timezone'])['presentation']:
                    raise CatalogueError(422, 'Read-only presentation must be echoed unchanged')
            if 'value' in supplied:
                cursor.execute(self.statement('catalogue_update.sql', assignments=sql.SQL('value=%s')),
                               (supplied['value'], entry_id))
                current = self.mapped(cursor.fetchone())
        return current

    def delete(self, actor, entry_id):
        with self.writing(actor) as cursor:
            cursor.execute(self.statement('catalogue_delete.sql', where=sql.SQL('id=%s')), (entry_id,))
            if not cursor.rowcount:
                raise CatalogueError(404, 'Test entry not found')

    def bulk(self, actor, selection, payload=None):
        """Count a preview or atomically change every matching row without paging."""
        values = selection.model_dump()
        changes = payload.model_dump(exclude_unset=True) if payload is not None else None
        bulk_context('test', {key: value for key, value in values.items()
                             if key not in ('confirm', 'dry_run') and value is not None}, changes)
        state = audit_context.get()
        if state is not None:
            state.mutation_details['dry_run'] = values['dry_run']
        predicate, parameters = where_clause(TEST_COLUMNS, test_filters(values))
        with self.writing(actor, administrator=True, preview=values['dry_run']) as cursor:
            if values['dry_run']:
                cursor.execute(sql.SQL('SELECT count(*) FROM public.test WHERE {}').format(predicate), parameters)
                matched, applied = cursor.fetchone()[0], 0
            else:
                parts = {'where': predicate}
                if changes is not None:
                    parts['assignments'] = sql.SQL('value=%s')
                cursor.execute(self.statement('catalogue_bulk_update.sql' if changes is not None else 'catalogue_bulk_delete.sql', **parts),
                               (*parameters, changes['value']) if changes is not None else parameters)
                matched, applied = cursor.fetchone()
            operation_evidence(cursor, 'test', {'matched_count': matched, 'applied_count': applied},
                               'preview' if values['dry_run'] else 'committed')
        result = dict(matched_count=matched, dry_run=values['dry_run'],
                      summary='Preview only; counts may change before execution.' if values['dry_run']
                      else 'All matching rows were successfully targeted in one committed transaction.')
        if not values['dry_run']:
            result['updated_count' if changes is not None else 'deleted_count'] = applied
        return result
