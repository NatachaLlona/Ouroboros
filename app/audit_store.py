"""Independent request entry/finalization; database triggers own mutation evidence."""
import re
from psycopg.types.json import Jsonb
from app.datetimes import utcnow


class AuditStore:
    """Use short transactions outside business work; never hold an entry row lock.

    Entry commits before endpoint execution. Business triggers update that row in
    the business transaction. Finalization runs afterward and never overwrites
    committed mutation evidence or differences.
    """
    def __init__(self, database):
        self.database = database

    def begin(self, state, started_at, method, path, query, query_flags):
        with self.database.connection() as connection, connection.cursor() as cursor:
            cursor.execute('''INSERT INTO public.api_audit_logs
                (interaction_id,started_at,method,path,request_query,capture)
                VALUES (%s,%s,%s,%s,%s,%s) RETURNING id_api_audit_logs''',
                (state.interaction_id, started_at, method, path, Jsonb(query), Jsonb({'query': query_flags})))
            row = cursor.fetchone()
            if not row or not isinstance(row[0], str) or not re.fullmatch(r'AL[0-9]{7,}', row[0]):
                raise RuntimeError('Audit entry was not persisted')
            audit_id = row[0]
        return audit_id

    def finish(self, state, *, duration, status, http_status, response_started, matched_route,
               request_body, response_body, capture, summary, outcome):
        """Finalize transport only, preserving any evidence already committed by SQL."""
        with self.database.connection() as connection, connection.cursor() as cursor:
            cursor.execute('''UPDATE public.api_audit_logs SET finished_at=%s,duration_ms=%s,
                status=%s,http_status=%s,response_started=%s,error_code=%s,matched_route=%s,
                actor_id=coalesce(actor_id,%s),actor_username=coalesce(actor_username,%s),actor_role=coalesce(actor_role,%s),
                request_body=%s,response_body=%s,capture=capture || %s,
                resource=coalesce(resource,%s),target_id=coalesce(target_id,%s),
                operation_summary=CASE WHEN business_outcome='committed' THEN operation_summary ELSE %s END,
                business_outcome=CASE WHEN business_outcome='committed' THEN business_outcome ELSE %s END,
                mutation_details=coalesce(mutation_details,%s)
                WHERE id_api_audit_logs=%s''',
                (utcnow(), duration, status, http_status, response_started, state.error_code, matched_route,
                 state.actor_id, state.actor_username, state.actor_role, Jsonb(request_body), Jsonb(response_body),
                 Jsonb(capture), state.resource, state.target_id, summary, outcome, Jsonb(state.mutation_details), state.audit_id))
            if cursor.rowcount != 1:
                raise RuntimeError('Audit completion was not persisted')
