"""Parameterized queries for public.test; callers own transactions."""
from app.logger import log_event
from app.config import PROJECT_ROOT

QUERY_DIRECTORY = PROJECT_ROOT / "sql" / "queries"


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


def page_entries(connection, entry_id=None, value=None, page=1, page_size=50):
    """Read a count and SQL-bounded page in one statement snapshot.

    Args:
        connection: Caller-owned transaction connection.
        entry_id: Optional exact ID filter.
        value: Optional unmodified ILIKE pattern.
        page: Validated one-based page number.
        page_size: Validated page size, from 10 through 50.

    Returns:
        A pagination envelope preserving the filtered count on empty pages.
    """
    offset = min((page - 1) * page_size, 9223372036854775807)
    with connection.cursor() as cursor:
        cursor.execute(query("page_test.sql"), (entry_id, entry_id, value, value, page_size, offset))
        rows = cursor.fetchall()
    return {"count": rows[0][0], "page": page, "page_size": page_size,
            "items": [{"id": row[1], "value": row[2]} for row in rows if row[1] is not None]}
