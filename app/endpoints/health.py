"""Public database readiness endpoint."""
from app.logger import log_event
from app.log_safety import error_details
from fastapi import APIRouter, Request
from starlette.responses import JSONResponse

router = APIRouter()


@router.get("/health", tags=["health"], responses={503: {"description": "Database unavailable"}})
def health(request: Request):
    try:
        with request.app.state.database.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        log_event("INFO", "Health check completed")
        return {"status": "ok"}
    except Exception as error:
        log_event("ERROR", "Database health check failed", error_details(error), component="health")
        return JSONResponse({"status": "unavailable"}, status_code=503)
