"""Whitelisted SQL collection snapshots, shared with inherited endpoints."""
from psycopg import sql
from app.config import PROJECT_ROOT
from app.ordering import clause


def template(name):
    """Load a tracked SQL template; callers supply trusted names only."""
    return sql.SQL((PROJECT_ROOT / 'sql/queries' / name).read_text(encoding='utf-8'))


def where_clause(columns, filters):
    """Compose the same AND predicate for GET, bulk preview and bulk execution."""
    conditions, values = [], []
    for name, operator, value in filters:
        if name not in columns or operator not in ('=', 'ILIKE', '>=', '<'):
            raise ValueError('Invalid filter selection')
        if value is not None:
            conditions.append(sql.SQL('{} {} %s').format(sql.Identifier(name), sql.SQL(operator)))
            values.append(value)
    return sql.SQL(' AND ').join(conditions) if conditions else sql.SQL('TRUE'), values


def select_page(connection, table, columns, key, filters, page, page_size, order_by, order_direction):
    """Read bounded rows and unbounded count in one statement snapshot.

    Args:
        connection: Caller-owned database transaction.
        table: Trusted table name.
        columns: Whitelisted public scalar names.
        key: Unique public ID, used to distinguish empty pages.
        filters: Trusted (column, operator, value) tuples; values are parameters.
        page: One-based integer.
        page_size: Bounded page length.
        order_by: Whitelisted scalar field.
        order_direction: asc or desc; NULLS LAST for both directions.

    Returns:
        Public collection envelope, preserving count on empty pages.
    """
    predicate, values = where_clause(columns, filters)
    statement = template('catalogue_page.sql').format(
        columns=sql.SQL(', ').join(map(sql.Identifier, columns)), table=sql.Identifier(table),
        where=predicate,
        ordering=clause(columns, order_by, order_direction, key),
        page_columns=sql.SQL(', ').join(sql.Identifier('p', name) for name in columns),
        page_ordering=clause(columns, order_by, order_direction, key, 'p'))
    with connection.cursor() as cursor:
        cursor.execute(statement, (*values, page_size, min((page - 1) * page_size, 9223372036854775807)))
        rows = cursor.fetchall()
    key_index = columns.index(key) + 1
    return dict(count=rows[0][0], page=page, page_size=page_size,
                items=[dict(zip(columns, row[1:])) for row in rows if row[key_index] is not None])
