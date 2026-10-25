"""Page-scoped reference loading using one batched SELECT per referenced table."""
from psycopg import sql
from app.schemas.relationships import RELATIONSHIPS, SUMMARY_FIELDS


def enrich_page(connection, table, page):
    """Keep count, ordering, item order and stored IDs intact; never recurse."""
    references = RELATIONSHIPS.get(table, ())
    needed = {}
    for reference in references:
        ids = needed.setdefault(reference.table, set())
        ids.update(row[reference.field] for row in page['items'] if row[reference.field] is not None)
    loaded = {}
    with connection.cursor() as cursor:
        for target, ids in needed.items():
            loaded[target] = {}
            if not ids:
                continue
            fields = SUMMARY_FIELDS[target]
            cursor.execute(sql.SQL('SELECT {} FROM public.{} WHERE {} = ANY(%s)').format(
                sql.SQL(', ').join(map(sql.Identifier, fields)), sql.Identifier(target), sql.Identifier(fields[0])),
                (sorted(ids),))
            loaded[target] = {row[0]: dict(zip(fields, row)) for row in cursor.fetchall()}
    return {**page, 'items': [{**row, 'references': {
        reference.alias: loaded[reference.table].get(row[reference.field]) for reference in references}}
        for row in page['items']]}
