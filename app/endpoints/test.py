"""Protected test-entry endpoints."""
from app.logger import log_event
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Security
from pydantic import BeforeValidator

from app.auth import require_scopes
from app.database_test import insert_entry, page_entries
from app.pagination import Page, pagination
from app.schemas.test import TestCreate, TestEntry, validate_query_id

router = APIRouter()


@router.post("/test", response_model=TestEntry, status_code=201, tags=["test"],
             dependencies=[Security(require_scopes, scopes=["test:write"])])
def create_entry(payload: TestCreate, request: Request):
    """Commit an unchanged value for an authorized test writer.

    Args:
        payload: Strict JSON test value.
        request: Request carrying the database provider.

    Returns:
        The database-generated ID and original value after transaction commit.
    """
    log_event("DEBUG", "Request validation completed")
    with request.app.state.database.connection() as connection:
        entry_id = insert_entry(connection, payload.value)
    log_event("INFO", "Test entry created", {"entry_id": entry_id})
    return {"id": entry_id, "value": payload.value}


@router.get("/test", response_model=Page[TestEntry], tags=["test"],
            dependencies=[Security(require_scopes, scopes=["test:read"])])
def get_entries(request: Request,
                paging: Annotated[dict, Depends(pagination)],
                id: Annotated[int | None, BeforeValidator(validate_query_id), Query(gt=0, le=9223372036854775807, description="Optional exact record ID; combined with value using AND before counting and pagination.", examples=[1])] = None,
                value: Annotated[str | None, Query(description="Optional case-insensitive ILIKE pattern: % matches any sequence, _ one character. Backslash escapes literal %, _ and backslash. No wildcards are added. Omitted disables filtering; empty matches empty values. Enter raw patterns in Swagger; URL-encode % as %25 and backslash as %5C in direct URLs.", examples=["%Ouroboros%", r"literal\%\_\\"])] = None):
    """Read a filtered SQL page and count from one statement snapshot.

    Args:
        request: Request carrying the database provider.
        paging: Shared validated page/page_size settings.
        id: Optional exact positive BIGINT filter.
        value: Optional unmodified case-insensitive SQL pattern.

    Returns:
        The ordered collection envelope, including count on empty pages.
    """
    log_event("DEBUG", "Request validation completed")
    with request.app.state.database.connection() as connection:
        result = page_entries(connection, id, value, **paging)
    log_event("INFO", "Test entries retrieved", {"row_count": len(result["items"]), "count": result["count"]})
    return result
