"""Read-only audit queries, independent of domain deletion lifetimes."""
from psycopg import sql
from app.datetimes import date_predicates
from app.collection_queries import select_page
from app.catalogue_repository import CatalogueError
from app.schemas.audit import AUDIT_COLUMNS


class AuditRepository:
    def __init__(self, database):
        self.database = database

    def read(self, audit_id):
        with self.database.connection() as connection, connection.cursor() as cursor:
            cursor.execute(sql.SQL('SELECT {} FROM public.api_audit_logs WHERE id_api_audit_logs=%s').format(
                sql.SQL(', ').join(map(sql.Identifier, AUDIT_COLUMNS))), (audit_id,))
            row = cursor.fetchone()
        if row is None:
            raise CatalogueError(404, 'Audit record not found')
        return dict(zip(AUDIT_COLUMNS, row))

    def page(self, selection):
        values = selection.model_dump()
        filters = [(field, '=', values[field]) for field in ('interaction_id','actor_id','actor_username','method',
            'resource','status','http_status','error_code','target_id')]
        filters += date_predicates(values, ('started_at', 'finished_at'))
        with self.database.connection() as connection:
            return select_page(connection, 'api_audit_logs', AUDIT_COLUMNS, 'id_api_audit_logs', filters,
                values['page'], values['page_size'], values['order_by'], values['order_direction'])
