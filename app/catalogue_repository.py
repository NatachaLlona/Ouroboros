"""Transactional catalogue persistence with safe errors and current-role checks."""
from contextlib import contextmanager
from psycopg import errors, sql, IsolationLevel
from pydantic import ValidationError

from app.collection_queries import select_page, template, where_clause
from app.datetimes import source_values, present, utc, date_predicates
from app.audit_context import audit_context, bulk_context, operation_evidence
from app.errors import AuditUnavailable
from app.classification_ordering import ClassificationOrdering, TierPositionError
from app.creation import batch_context, batch_evidence, creation_item
from app.schemas.relationships import RELATIONSHIPS
from app.relationship_reads import enrich_page


class CatalogueError(Exception):
    """Application-owned guidance, safe to expose without SQL or rejected values."""
    def __init__(self, status, detail, details=None):
        self.status, self.details = status, details
        super().__init__(detail)


def lock_catalogue_actor(cursor, actor, administrator=False):
    """Revalidate active role and token version under the membership lock.

    Lock order is membership advisory lock, actor row, then catalogue row(s).
    This serializes catalogue writes with demotions, admin resets and user
    administration. The actor row also prevents concurrent self-password changes
    from letting a revoked token start a write after the version changes.
    """
    cursor.execute('SELECT pg_advisory_xact_lock(%s)', (719230818,))
    cursor.execute('SELECT role, is_active, credential_version FROM public.api_users WHERE id=%s FOR UPDATE', (int(actor['sub']),))
    current = cursor.fetchone()
    if current is None or not current[1] or current[2] != actor['credential_version']:
        raise CatalogueError(401, 'Invalid or expired access token')
    if current[0] not in (('administrator',) if administrator else ('supervisor', 'administrator')):
        raise CatalogueError(403, 'Active administrator required' if administrator else 'Supervisor or administrator access required')


class CatalogueRepository:
    """Persist one resource at a time; never own normal infrastructure lifecycle."""
    def __init__(self, database, resource):
        self.database, self.resource = database, resource

    def statement(self, filename, **parts):
        """Compose identifiers exclusively from the fixed resource contract."""
        resource = self.resource
        return template(filename).format(table=sql.Identifier(resource.table),
            columns=sql.SQL(', ').join(map(sql.Identifier, resource.columns)),
            key=sql.Identifier(resource.key), **parts)

    @contextmanager
    def writing(self, actor, administrator=False):
        """Commit or roll back a write and translate expected constraint errors."""
        try:
            state = audit_context.get()
            if state is not None and state.audit_id is None:
                raise AuditUnavailable('Mandatory audit unavailable')
            with self.database.connection() as connection, connection.cursor() as cursor:
                lock_catalogue_actor(cursor, actor, administrator)
                yield cursor
        except TierPositionError as error:
            raise CatalogueError(422, str(error), details=error.details) from None
        except (errors.ForeignKeyViolation, errors.UniqueViolation):
            raise CatalogueError(409, 'A referenced record is missing, a dependency prevents deletion, or this relationship already exists') from None
        except (errors.CheckViolation, errors.NotNullViolation, errors.GeneratedAlways,
                errors.NumericValueOutOfRange, errors.InvalidTextRepresentation, ValidationError, ValueError):
            raise CatalogueError(422, 'Invalid resulting record; check required fields, numeric limits, fixed metadata and tag/origin choices') from None

    def mapped(self, row):
        return dict(zip(self.resource.columns, row)) if row is not None else None

    def create(self, payload, actor):
        """Return database-generated metadata/defaults after transaction commit."""
        values = payload.model_dump()
        values = self.source_context(values)
        with self.writing(actor) as cursor:
            ordering = ClassificationOrdering(cursor) if self.resource.table == 'work_classifications' else None
            if ordering is not None:
                values['tier'], shifted = ordering.insert(values.get('tier'))
            cursor.execute(self.statement('catalogue_insert.sql',
                fields=sql.SQL(', ').join(map(sql.Identifier, values)),
                values=sql.SQL(', ').join(sql.Placeholder() for _ in values)), tuple(values.values()))
            result = self.mapped(cursor.fetchone())
            if ordering is not None:
                ordering.evidence('insert', {'id': result[self.resource.key], 'old_tier': None, 'new_tier': result['tier']}, shifted)
        return result

    def create_many(self, payloads, actor):
        """Insert ordered items on one authorized transaction; never commit a prefix."""
        resource = self.resource
        batch_context(resource.table, len(payloads))
        results, shifted_count, shifted_records, statement = [], 0, [], None
        with self.writing(actor) as cursor:
            ordering = ClassificationOrdering(cursor) if resource.table == 'work_classifications' else None
            for index, payload in enumerate(payloads):
                with creation_item(index):
                    values = self.source_context(payload.model_dump())
                    if ordering is not None:
                        values['tier'], shifted = ordering.insert(values.get('tier'))
                        shifted_count += shifted['shifted_count']
                        shifted_records.extend({'item_index': index, **row}
                            for row in shifted['shifted_records'][:20 - len(shifted_records)])
                    if statement is None:
                        statement = self.statement('catalogue_insert.sql',
                            fields=sql.SQL(', ').join(map(sql.Identifier, values)),
                            values=sql.SQL(', ').join(sql.Placeholder() for _ in values))
                    cursor.execute(statement, tuple(values.values()))
                    results.append(self.mapped(cursor.fetchone()))
            if ordering is not None:
                # Later inserts may shift earlier items: return their final persisted tiers.
                cursor.execute(sql.SQL('SELECT {} FROM public.{} WHERE {} = ANY(%s)').format(
                    sql.SQL(', ').join(map(sql.Identifier, resource.columns)),
                    sql.Identifier(resource.table), sql.Identifier(resource.key)),
                    ([record[resource.key] for record in results],))
                persisted = {row[resource.key]: row for row in map(self.mapped, cursor.fetchall())}
                results = [persisted[record[resource.key]] for record in results]
            batch_evidence(cursor, resource.table, results, resource.key, shifted_count,
                           shifted_records if ordering is not None else None)
        return results

    def read(self, record_id):
        """Read an exact permanent ID or return safe 404 guidance."""
        with self.database.connection() as connection, connection.cursor() as cursor:
            cursor.execute(self.statement('catalogue_read.sql', lock=sql.SQL('')), (record_id,))
            result = self.mapped(cursor.fetchone())
        if result is None:
            raise CatalogueError(404, 'Catalogue record not found')
        return result

    def update(self, record_id, payload, actor):
        """Apply only supplied mutable fields after locking and validating the row.

        A concurrent update cannot be overwritten by an unprotected read/merge.
        Full-record echoes are allowed only when immutable values match the
        locked database record. Explicit null is validated against full input.
        """
        resource = self.resource
        supplied = payload.model_dump(exclude_unset=True)
        with self.writing(actor) as cursor:
            ordering = ClassificationOrdering(cursor) if resource.table == 'work_classifications' else None
            cursor.execute(self.statement('catalogue_read.sql', lock=sql.SQL('FOR UPDATE')), (record_id,))
            current = self.mapped(cursor.fetchone())
            if current is None:
                raise CatalogueError(404, 'Catalogue record not found')
            for field in resource.immutable:
                if field in supplied and supplied[field] != current[field]:
                    raise CatalogueError(422, 'Immutable metadata or a server-controlled timestamp cannot be changed: ' + field)
            if 'presentation' in supplied:
                echoed = supplied['presentation']
                if echoed != present(current, echoed['display_timezone'])['presentation']:
                    raise CatalogueError(422, 'Read-only presentation must be echoed unchanged')
            mutable = {key: value for key, value in supplied.items() if key in resource.fields}
            validation_values = {key: mutable.get(key, current[key]) for key in resource.fields}
            # Omitted historical descriptions may exceed today's input policy.
            # Validate only submitted descriptions; this copy is never persisted.
            for key in resource.fields:
                if key.startswith('description_') and key not in mutable:
                    validation_values[key] = None
            resource.create.model_validate(validation_values)
            mutable = self.source_context(mutable, current, preserve_echo='watched_at_offset' in supplied)
            if ordering is not None and 'tier' in mutable:
                old_tier = current['tier']
                mutable['tier'], shifted = ordering.move(old_tier, mutable['tier'])
            if mutable:
                cursor.execute(self.statement('catalogue_update.sql', assignments=sql.SQL(', ').join(
                    sql.SQL('{} = %s').format(sql.Identifier(field)) for field in mutable)), (*mutable.values(), record_id))
                current = self.mapped(cursor.fetchone())
            if ordering is not None and 'tier' in mutable:
                ordering.evidence('move', {'id': record_id, 'old_tier': old_tier, 'new_tier': current['tier']}, shifted)
        return current

    def page(self, selection):
        """Combine exact/pattern filters before deterministic ordering/pagination."""
        resource = self.resource
        values = selection.model_dump()
        filters = self.filters(values)
        with self.database.connection() as connection:
            if resource.table in RELATIONSHIPS:
                # The provider's setup transaction is already committed. Set these
                # before the first data SELECT so the page and names share a snapshot.
                connection.isolation_level = IsolationLevel.REPEATABLE_READ
                connection.read_only = True
            result = select_page(connection, resource.table, resource.columns, resource.key, filters,
                values['page'], values['page_size'], values['order_by'], values['order_direction'])
            return enrich_page(connection, resource.table, result) if resource.table in RELATIONSHIPS else result

    def source_context(self, values, current=None, preserve_echo=False):
        """Update watched_at companions together; metadata echoes are not editable."""
        if self.resource.table != 'watch_history':
            return values
        result = dict(values)
        supplied_zone = result.get('watched_at_timezone')
        if 'watched_at' not in result:
            if 'watched_at_timezone' in result and (current is None or supplied_zone != current['watched_at_timezone']):
                raise CatalogueError(422, 'Changing the source zone requires an explicit offset-aware watched_at')
            return result
        if (current and result['watched_at'] is not None and current['watched_at'] is not None
                and utc(result['watched_at']) == utc(current['watched_at'])
                and preserve_echo
                and ('watched_at_timezone' not in result or supplied_zone == current['watched_at_timezone'])):
            result.update(watched_at=current['watched_at'], watched_at_offset=current['watched_at_offset'],
                          watched_at_timezone=current['watched_at_timezone'])
            return result
        if result['watched_at'] is None and current and supplied_zone == current['watched_at_timezone']:
            supplied_zone = None
        try:
            canonical, offset, zone = source_values(result['watched_at'], supplied_zone)
        except ValueError:
            raise CatalogueError(422, 'watched_at requires a valid offset and a matching explicit IANA timezone, if supplied') from None
        result.update(watched_at=canonical, watched_at_offset=offset, watched_at_timezone=zone)
        return result

    def filters(self, values):
        """Use the identical predicate contract for collection and bulk operations."""
        resource = self.resource
        filters = [(name, 'ILIKE' if name in resource.pattern_fields else '=', values.get(name)) for name in resource.columns]
        filters = [(name, '@>', [value]) if name == 'platform_access_types' and value is not None else (name, operator, value)
                   for name, operator, value in filters]
        filters += date_predicates(values, [field for field in ('created_at', 'added_at', 'watched_at') if field in resource.columns])
        return filters

    def bulk(self, actor, selection, payload=None):
        """Preview or atomically mutate every matching row, without page limits.

        SQL validates complete resulting rows. Updated count includes targeted
        rows whose submitted values were already equal. No rows are returned.
        """
        resource = self.resource
        values = selection.model_dump()
        changes = self.source_context(payload.model_dump(exclude_unset=True)) if payload is not None else None
        bulk_context(resource.table, {key:value for key,value in values.items() if key not in ('confirm','dry_run') and value is not None}, changes)
        state = audit_context.get()
        if state is not None:
            state.mutation_details['dry_run'] = values['dry_run']
        predicate, parameters = where_clause(resource.columns, self.filters(values))
        try:
            with self.database.connection() as connection, connection.cursor() as cursor:
                lock_catalogue_actor(cursor, actor, administrator=True)
                ordering = ClassificationOrdering(cursor) if resource.table == 'work_classifications' else None
                if values['dry_run']:
                    cursor.execute(sql.SQL('SELECT count(*) FROM public.{} WHERE {}').format(sql.Identifier(resource.table), predicate), parameters)
                    matched, applied = cursor.fetchone()[0], 0
                else:
                    if state is not None and state.audit_id is None:
                        raise AuditUnavailable('Mandatory audit unavailable')
                    filename = 'catalogue_bulk_update.sql' if changes is not None else 'catalogue_bulk_delete.sql'
                    parts = {'where': predicate}
                    if changes is not None:
                        parts['assignments'] = sql.SQL(', ').join(sql.SQL('{} = %s').format(sql.Identifier(field)) for field in changes)
                    cursor.execute(self.statement(filename, **parts), (*parameters, *changes.values()) if changes is not None else parameters)
                    matched, applied = cursor.fetchone()
                    if ordering is not None and changes is None:
                        shifted = ordering.compact()
                        ordering.evidence('bulk_delete', None, shifted, primary_count=applied)
                operation_evidence(cursor, resource.table, {'matched_count':matched, 'applied_count':applied}, 'preview' if values['dry_run'] else 'committed')
        except (errors.ForeignKeyViolation, errors.UniqueViolation):
            raise CatalogueError(409, 'A dependency or relationship conflict rolled back the complete bulk operation') from None
        except (errors.CheckViolation, errors.NotNullViolation, errors.GeneratedAlways, errors.NumericValueOutOfRange):
            raise CatalogueError(422, 'A resulting record violates field or relationship rules; the complete bulk operation was rolled back') from None
        result = dict(matched_count=matched, dry_run=values['dry_run'],
            summary='Preview only; counts may change before execution.' if values['dry_run'] else 'All matching rows were successfully targeted in one committed transaction.')
        if not values['dry_run']:
            result['updated_count' if changes is not None else 'deleted_count'] = applied
        return result

    def delete(self, actor, record_id=None):
        """Delete atomically without cascades or sequence resets, then return count."""
        with self.writing(actor, administrator=record_id is None) as cursor:
            ordering = ClassificationOrdering(cursor) if self.resource.table == 'work_classifications' else None
            if ordering is not None and record_id is not None:
                cursor.execute(self.statement('catalogue_read.sql', lock=sql.SQL('FOR UPDATE')), (record_id,))
                current = self.mapped(cursor.fetchone())
                if current is None:
                    raise CatalogueError(404, 'Catalogue record not found')
                shifted = ordering.delete(current['tier'])
            cursor.execute(self.statement('catalogue_delete.sql', where=sql.SQL('TRUE') if record_id is None
                else sql.SQL('{} = %s').format(sql.Identifier(self.resource.key))), () if record_id is None else (record_id,))
            # DELETE rowcount is PostgreSQL's actual affected count, not a prior estimate.
            deleted = cursor.rowcount
            if record_id is not None and not deleted:
                raise CatalogueError(404, 'Catalogue record not found')
            if ordering is not None and record_id is not None:
                ordering.evidence('delete', {'id': record_id, 'old_tier': current['tier'], 'new_tier': None}, shifted)
        return deleted
