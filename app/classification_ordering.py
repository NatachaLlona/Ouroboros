"""Atomic classification positions under one ordered list lock.

The repository owns the transaction and acquires membership/actor locks first.
Deferred uniqueness permits temporary overlaps while set-based shifts execute.
The final primary mutation retains its individual trigger diff; internal shifts
only contribute their count plus a bounded summary to the same request audit.
"""
from psycopg import sql

from app.audit_context import audit_context, operation_evidence


class TierPositionError(ValueError):
    """Safe, application-owned validation guidance without rejected input."""

    def __init__(self, maximum, insertion):
        self.details = [{'loc': ['body', 'tier'], 'type': 'tier_range',
                         'msg': ('Insertion' if insertion else 'Move')
                         + ' tier must be between 1 and ' + str(maximum) + '.'}]
        super().__init__('Classification tier is outside the valid position range')


class ClassificationOrdering:
    """Serialize list edits and record all shifts without copying entire lists."""

    def __init__(self, cursor):
        self.cursor = cursor
        self.size = None
        cursor.execute('SELECT pg_advisory_xact_lock(%s)', (719230819,))
        cursor.execute('SET CONSTRAINTS work_classifications_tier_unique DEFERRED')

    def position(self, requested, insertion=False):
        """Resolve append or validate a requested position against the locked list."""
        if self.size is None:
            self.cursor.execute('SELECT count(*) FROM public.work_classifications')
            self.size = self.cursor.fetchone()[0]
        maximum = self.size + int(insertion)
        target = maximum if requested is None and insertion else requested
        if target is not None and not 1 <= target <= maximum:
            raise TierPositionError(maximum, insertion)
        return target

    def shift(self, predicate, parameters, delta):
        """Shift a trusted tier range, sampling at most twenty identifiers."""
        self.cursor.execute(sql.SQL('''SELECT id_work_classifications, tier, tier + %s,
                count(*) OVER () FROM public.work_classifications WHERE {}
                ORDER BY tier, id_work_classifications LIMIT 20''').format(predicate),
                (delta, *parameters))
        rows = self.cursor.fetchall()
        shifted = self.sample(rows)
        if rows:
            self.cursor.execute("SELECT set_config('ouroboros.audit_bulk', 'true', true)")
            self.cursor.execute(sql.SQL('UPDATE public.work_classifications SET tier = tier + %s WHERE {}').format(predicate),
                                (delta, *parameters))
            self.restore_audit_mode()
        return shifted

    @staticmethod
    def sample(rows):
        """Only immutable IDs and numeric positions enter the bounded sample."""
        return {'shifted_count': rows[0][3] if rows else 0,
                'shifted_records': [{'id': row[0], 'old_tier': row[1], 'new_tier': row[2]} for row in rows],
                'shifted_records_omitted': bool(rows and rows[0][3] > len(rows))}

    def restore_audit_mode(self):
        state = audit_context.get()
        self.cursor.execute("SELECT set_config('ouroboros.audit_bulk', %s, true)",
                            ('true' if state is not None and state.bulk else 'false',))

    def insert(self, requested):
        target = self.position(requested, insertion=True)
        shifted = self.sample([]) if target == self.size + 1 else self.shift(sql.SQL('tier >= %s'), (target,), 1)
        self.size += 1
        return target, shifted

    def move(self, old, target):
        target = old if target is None else self.position(target)
        if target < old:
            shifted = self.shift(sql.SQL('tier >= %s AND tier < %s'), (target, old), 1)
        elif target > old:
            shifted = self.shift(sql.SQL('tier > %s AND tier <= %s'), (old, target), -1)
        else:
            shifted = self.sample([])
        return target, shifted

    def delete(self, old):
        return self.shift(sql.SQL('tier > %s'), (old,), -1)

    def compact(self):
        """Close all bulk-deletion gaps while preserving surviving relative order."""
        self.cursor.execute('''WITH ordered AS (SELECT id_work_classifications, tier,
            row_number() OVER (ORDER BY tier, id_work_classifications) AS new_tier
            FROM public.work_classifications)
            SELECT id_work_classifications, tier, new_tier, count(*) OVER ()
            FROM ordered WHERE tier <> new_tier ORDER BY tier, id_work_classifications LIMIT 20''')
        shifted = self.sample(self.cursor.fetchall())
        if shifted['shifted_count']:
            self.cursor.execute('''WITH ordered AS (SELECT id_work_classifications, tier,
                row_number() OVER (ORDER BY tier, id_work_classifications) AS new_tier
                FROM public.work_classifications)
                UPDATE public.work_classifications AS target SET tier = ordered.new_tier
                FROM ordered WHERE target.id_work_classifications = ordered.id_work_classifications
                AND target.tier <> ordered.new_tier''')
        return shifted

    def evidence(self, action, moved, shifted, primary_count=1):
        """Persist aggregate facts transactionally; capture bounds are applied centrally."""
        state = audit_context.get()
        if state is not None and moved is not None:
            state.target_id = moved['id']
        details = {'reordering': {'action': action, 'moved': moved,
                    'affected_count': primary_count + shifted['shifted_count'], **shifted}}
        operation_evidence(self.cursor, 'work_classifications', details, 'committed')
