"""Bounded runtime SQL connections; verify registry before serving requests."""
from contextlib import contextmanager
import threading
from decimal import Decimal
import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from fastapi import HTTPException
from database.model import render
from database.settings import mapping
from api.service.config import effective


class Store:
    def __init__(self,document,settings,connection_arguments):
        self.document,self.settings,self.arguments=document,settings,connection_arguments
        self.names=mapping(document)
        self.capacity=threading.BoundedSemaphore(settings['max_connections'])

    @contextmanager
    def transaction(self):
        if not self.capacity.acquire(timeout=self.settings['connection_acquire_timeout_seconds']):
            raise HTTPException(503,'Database connection capacity exhausted')
        try:
            with psycopg.connect(**self.arguments,connect_timeout=self.settings['connect_timeout_seconds'],
                                 options='-c timezone=UTC -c search_path=pg_catalog',row_factory=dict_row) as connection:
                connection.execute("SELECT set_config('statement_timeout',%s,true)",(str(self.settings['statement_timeout_ms']),))
                yield Session(self,connection)
        finally:
            self.capacity.release()


class Session:
    def __init__(self,store,connection):
        self.store,self.connection=store,connection

    def execute(self,query,parameters=()):
        return self.connection.execute(render(query,self.store.document) if isinstance(query,str) else query,parameters)

    def function(self,name,*parameters):
        allowed={'api_can','api_credential','api_credential_current','api_create_account','api_assign_role',
                 'api_issue_client','api_revoke_client','api_set_setting','api_add_rule','api_set_active',
                 'api_remove_rule','api_set_permissions','api_rbac','change_plan'}
        if name not in allowed:
            raise ValueError('Unknown SQL capability')
        query=sql.SQL('SELECT * FROM {}.{}({})').format(sql.Identifier(self.store.document['schema']),sql.Identifier(name),sql.SQL(',').join(sql.Placeholder() for _ in parameters))
        return self.execute(query,parameters)

    def limits(self):
        return effective(self.store.settings,self.execute('SELECT name,minimum_value,maximum_value,current_value FROM {operator_setting}').fetchall())

    def canonical(self,row):
        if row is None:
            return None
        result={key:str(value) if isinstance(value,Decimal) else value for key,value in row.items()}
        for logical,physical in self.store.names.items():
            for prefix in ('id_','sequence_','prefix_','fantasy_name_'):
                if prefix+physical in result and physical!=logical:
                    result[prefix+logical]=result.pop(prefix+physical)
        return result

    def table(self,resource):
        return sql.SQL('{}.{}').format(sql.Identifier(self.store.document['schema']),sql.Identifier(self.store.names[resource]))

    def column(self,field):
        return sql.Identifier(render(field,self.store.document))
