"""Application factory, safe request logging, and connection shutdown."""
import time
import asyncio
import logging
import anyio
from contextlib import asynccontextmanager

import psycopg
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError

from app.database import DatabaseError
from app.api_users import UserManagementError
from app.cleanup import cleanup_actions, ResourceCleanupError
from app.logger import active_logger
from app.request_context import RequestContext, request_context, create_interaction_id
from app.log_safety import body_preview, error_details
from starlette.exceptions import HTTPException as StarletteHTTPException
from app.endpoints import health, test, token, users
from app.endpoints import catalogue
from app.endpoints import audit
from app.catalogue_repository import CatalogueError
from app.errors import AuditUnavailable, ERROR_RESPONSES, code_for, error_response, load_error_codes
from app.audit_context import audit_context
from app.audit_privacy import safe_path, sensitive_operation


class ResponseStartedError(RuntimeError):
    """Propagate a broken response without exposing the original exception text."""


class RequestLoggingMiddleware:
    """Isolate metadata and inspect bounded JSON without consuming the endpoint stream."""
    def __init__(self, app, logger):
        self.app = app
        self.logger = logger

    async def __call__(self, scope, receive, send):
        """Bind request context and forward one ASGI response safely.

        Args:
            scope: Server-supplied ASGI request metadata.
            receive: Incoming request-message callback.
            send: Outgoing response-message callback.

        Raises:
            ResponseStartedError: If downstream fails after sending headers.
            asyncio.CancelledError: On cancellation, after context cleanup.

        Before headers, unexpected failures become a safe 500. After headers,
        failure is propagated with a safe message and no second response.
        """
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        interaction = scope.get('state', {}).get('interaction_id') or create_interaction_id()
        scope.setdefault("state", {})["interaction_id"] = interaction
        context_token = request_context.set(RequestContext(interaction, scope["method"], safe_path(scope["path"])))
        logger_token = active_logger.set(self.logger)
        started = time.perf_counter()
        status, sent = None, False
        send_failed = False
        outcome = "completed"
        captured = bytearray()
        inspected = False
        overflow = False
        path = scope["path"].rstrip("/")
        inspect_json = (self.logger.logger.isEnabledFor(logging.DEBUG)
                        and not sensitive_operation(path)
                        and dict(scope.get("headers", [])).get(b"content-type", b"").split(b";")[0].strip() == b"application/json")

        async def event(level, message, context=None):
            await anyio.to_thread.run_sync(lambda: self.logger.log({"level": level, "message": message, "context": context or {}}))

        async def receive_body():
            nonlocal inspected, overflow
            message = await receive()
            if inspect_json and message["type"] == "http.request" and not inspected:
                data = message.get("body", b"")
                if len(captured) + len(data) <= 1048576 and not overflow:
                    captured.extend(data)
                else:
                    overflow = True
                    captured.clear()
                if not message.get("more_body", False):
                    inspected = True
                    if overflow:
                        preview = {"body_preview": "[omitted: inspection limit exceeded]", "truncated": True}
                    else:
                        preview = await anyio.to_thread.run_sync(body_preview, bytes(captured), self.logger.config["body_max_chars"])
                    captured.clear()
                    await event("DEBUG", "Request JSON body received", preview)
                    await event("DEBUG", "Body validation started")
            return message

        async def send_response(message):
            nonlocal status, sent, send_failed
            if message["type"] == "http.response.start":
                headers = [(key, value) for key, value in message.get("headers", []) if key.lower() != b"x-interaction-id"]
                message = {**message, "headers": headers + [(b"x-interaction-id", interaction.encode())]}
            try:
                await send(message)
            except BaseException:
                send_failed = True
                raise
            if message["type"] == "http.response.start":
                status, sent = message["status"], True
        try:
            await event("INFO", "HTTP request received")
            await event("DEBUG", "Request validation started")
            await self.app(scope, receive_body, send_response)
        except asyncio.CancelledError:
            outcome = "cancelled"
            if audit_context.get() is not None:
                audit_context.get().error_code = 'REQUEST_CANCELLED'
            raise
        except Exception as error:
            outcome = "failed"
            code = 'TRANSPORT_FAILURE' if send_failed else 'INTERNAL_ERROR'
            if audit_context.get() is not None:
                audit_context.get().error_code = code
            await event("ERROR", "Unhandled request failure", {**error_details(error), 'error_code': code})
            if not sent and not send_failed:
                try:
                    await error_response(load_error_codes(), 'INTERNAL_ERROR')(scope, receive, send_response)
                except asyncio.CancelledError:
                    outcome = "cancelled"
                    raise
                except Exception:
                    raise ResponseStartedError("Response transmission failed; inspect safe application diagnostics") from None
            else:
                # Uvicorn may format propagated exceptions. Keep its message safe;
                # the original category/frames have already been logged once.
                raise ResponseStartedError("Response transmission failed; inspect safe application diagnostics") from None
        finally:
            try:
                with anyio.CancelScope(shield=True):
                    await event("INFO", "HTTP request finished", {"status": status, "response_started": sent,
                                "error_code": audit_context.get().error_code if audit_context.get() is not None else None,
                                "outcome": outcome, "duration_ms": round((time.perf_counter() - started) * 1000, 3)})
            finally:
                captured.clear()
                active_logger.reset(logger_token)
                request_context.reset(context_token)


def create_app(config, database, auth, logger):
    """Build the API with shared authorization, safe errors and owned cleanup.

    Args:
        config: Validated non-secret API/logging settings.
        database: Short-lived connection provider, closed during lifespan.
        auth: Database-backed authentication service, cleared during lifespan.
        logger: Execution logger; the outer startup coordinator closes it.

    Returns:
        A FastAPI application with public and protected routers.
    """
    @asynccontextmanager
    async def lifespan(app):
        limiter = anyio.to_thread.current_default_thread_limiter()
        previous_limit = limiter.total_tokens
        limiter.total_tokens = 40
        try:
            await anyio.to_thread.run_sync(lambda: logger.log({"message": "API started; one worker and 40 thread-pool slots"}))
            yield
        finally:
            with anyio.CancelScope(shield=True):
                failures = await anyio.to_thread.run_sync(lambda: cleanup_actions([
                    ("database", database.close), ("authentication", auth.close),
                    ("thread_pool_limit", lambda: setattr(limiter, "total_tokens", previous_limit)),
                ]))
                app.state.cleanup_failures.extend(failures)
                message = "API shutdown completed with cleanup errors" if failures else "API stopped; database connections released"
                try:
                    await anyio.to_thread.run_sync(lambda: logger.log({"level": "ERROR" if failures else "INFO", "message": message,
                                                                      "context": {"cleanup_failures": failures} if failures else {}}))
                except BaseException as error:
                    app.state.cleanup_failures.append({"resource": "shutdown_logging", **error_details(error)})


    codes = load_error_codes()
    application = FastAPI(title="Ouroboros", lifespan=lifespan, responses=ERROR_RESPONSES)
    application.state.cleanup_failures = []
    application.state.database = database
    application.state.auth = auth
    application.state.logger = logger
    application.state.config = config
    application.state.error_codes = codes
    from app.creation_limits import CreationBodyLimitMiddleware
    application.add_middleware(CreationBodyLimitMiddleware, config=config, codes=codes)
    application.add_middleware(RequestLoggingMiddleware, logger=logger)
    from app.audit_middleware import RequestAuditingMiddleware
    application.add_middleware(RequestAuditingMiddleware, database=database, logger=logger, config=config, codes=codes)

    @application.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error):
        code = 'CONFIRMATION_REQUIRED' if any(item['type'] == 'confirmation_required' for item in error.errors()) else 'VALIDATION_ERROR'
        await anyio.to_thread.run_sync(lambda: logger.log({"level": "WARNING", "message": "Request validation rejected",
                                                          "context": {"error_count": len(error.errors()), 'error_code':code}}))
        # Return field locations and types, never the rejected input or parser context.
        details = [{"loc": list(item["loc"]), "type": item["type"],
                    "msg": validation_message(item["type"])} for item in error.errors()]
        return error_response(codes, code, None if sensitive_operation(request.url.path) else details)

    async def database_error(request: Request, error):
        await anyio.to_thread.run_sync(lambda: logger.log({"level": "ERROR", "message": "Database request failed",
                                                          "context": {**error_details(error), 'error_code':'DATABASE_UNAVAILABLE'}}))
        return error_response(codes, 'DATABASE_UNAVAILABLE')

    @application.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, error):
        code = code_for(error.status_code, error.detail, request.url.path)
        await anyio.to_thread.run_sync(lambda: logger.log({"level": "WARNING", "message": "Request rejected",
                                                          "context": {"status": error.status_code, 'error_code':code}}))
        return error_response(codes, code, headers=error.headers, status=error.status_code)

    application.add_exception_handler(DatabaseError, database_error)
    @application.exception_handler(UserManagementError)
    async def user_management_error(request: Request, error):
        code = code_for(error.status, source='users')
        await anyio.to_thread.run_sync(lambda: logger.log({"level": "WARNING", "message": "User management rejected",
                                                          "context": {"status": error.status, 'error_code':code}}))
        headers = {"WWW-Authenticate": 'Bearer error="invalid_token"'} if error.status == 401 else None
        return error_response(codes, code, details=getattr(error, 'details', None), headers=headers, status=error.status)

    application.add_exception_handler(psycopg.Error, database_error)
    @application.exception_handler(CatalogueError)
    async def catalogue_error(request: Request, error):
        code = code_for(error.status)
        await anyio.to_thread.run_sync(lambda: logger.log({"level": "WARNING", "message": "Catalogue request rejected",
                                                          "context": {"status": error.status, 'error_code':code}}))
        headers = {"WWW-Authenticate": 'Bearer error="invalid_token"'} if error.status == 401 else None
        return error_response(codes, code, details=getattr(error, 'details', None), headers=headers, status=error.status)

    @application.exception_handler(AuditUnavailable)
    async def audit_error(request: Request, error):
        await anyio.to_thread.run_sync(lambda: logger.log({'level':'ERROR','message':'Required mutation audit unavailable',
            'context':{'error_code':'AUDIT_UNAVAILABLE'}}))
        return error_response(codes, 'AUDIT_UNAVAILABLE')

    for router in (health.router, token.router, test.router, users.router):
        application.include_router(router)
    for router in catalogue.routers:
        application.include_router(router)
    application.include_router(audit.router)
    return application


def validation_message(category):
    """Map parser categories to safe guidance without rejected values/context."""
    if category == "missing":
        return "This field is required"
    if category == "extra_forbidden":
        return "This field is not allowed"
    messages = {
        "creation_shape": "Supply one JSON object or a nonempty array of JSON objects",
        "batch_empty": "Supply at least one JSON object in the array",
        "tier_bulk_update": "Bulk tier changes are not supported; use individual PUT /work_classifications/{id} to reorder classifications",
        "empty_update": "Supply at least one field to update or echo; an empty update object is not allowed",
        "string_type": "Expected a string",
        "int_type": "Expected an integer",
        "int_parsing": "Expected an integer in decimal notation",
        "greater_than": "Value must be greater than the minimum in the field schema",
        "greater_than_equal": "Value must be at least the minimum in the field schema",
        "less_than": "Value must be less than the maximum in the field schema",
        "less_than_equal": "Value must not exceed the maximum in the field schema",
        "too_long": "Value exceeds the maximum length in the field schema",
        "too_short": "Value is shorter than the minimum length in the field schema",
        "string_too_short": "Text is shorter than the minimum length in the field schema",
        "string_too_long": "Text exceeds the maximum length in the field schema",
        "literal_error": "Choose one of the allowed values in the field schema",
    }
    if category in messages:
        return messages[category]
    if category.endswith(("_type", "_parsing")):
        return "Incorrect value type or format"
    if category == "json_invalid":
        return "Request body must contain valid JSON"
    return "Invalid value; check the allowed values in the field schema"


def run_api(application, config):
    import uvicorn
    # Built-in access logs include query strings; the application middleware logs safe fields.
    server = uvicorn.Server(uvicorn.Config(application, host=config["host"], port=config["port"],
                                         access_log=False, log_config=None, workers=1))
    try:
        server.run()
    except KeyboardInterrupt:
        pass
    if application.state.cleanup_failures:
        raise ResourceCleanupError(application.state.cleanup_failures)
    if not server.started:
        raise DatabaseError("API could not start; check the configured host and port")
