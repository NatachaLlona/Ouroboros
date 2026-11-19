"""Trusted scalar ordering shared by all paginated collections."""
from typing import Annotated, Literal
from fastapi import Query
from psycopg import sql

Direction = Literal['asc', 'desc']
TestOrder = Literal['id', 'value', 'created_at', 'created_at_timezone']
UserOrder = Literal['id', 'username', 'role', 'is_active', 'created_at']
OrderDirection = Annotated[Direction, Query(description='Sort direction; NULL values always appear last. Ties use the unique ID ascending.', examples=['asc', 'desc'])]


def clause(fields, selected, direction, key, alias=None):
    """Compose only whitelisted identifiers and fixed direction tokens.

    Args:
        fields: Trusted public scalar names, never private database columns.
        selected: Requested field, checked even for internal callers.
        direction: Validated asc or desc.
        key: Unique deterministic tie-breaker field.
        alias: Optional trusted SQL relation alias.

    Returns:
        A composable ORDER BY expression with consistent NULLS LAST.
    """
    if selected not in fields or direction not in ('asc', 'desc'):
        raise ValueError('Invalid ordering selection')
    def identifier(name):
        return sql.Identifier(alias, name) if alias else sql.Identifier(name)
    result = sql.SQL('{} {} NULLS LAST').format(identifier(selected), sql.SQL('ASC' if direction == 'asc' else 'DESC'))
    if selected != key:
        result += sql.SQL(', {} ASC').format(identifier(key))
    return result
