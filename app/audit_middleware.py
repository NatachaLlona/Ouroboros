"""Central request lifecycle with bounded bodies and truthful transport outcomes."""
import asyncio
import time
from urllib.parse import parse_qsl
import anyio

from app.audit_context import AuditContext, audit_context
from app.audit_privacy import BodyCapture, bounded_value, safe_path, sensitive_operation
from app.audit_store import AuditStore
from app.datetimes import utcnow
from app.errors import code_for, error_response, load_error_codes
from app.logger import active_logger
from app.request_context import RequestContext, request_context, create_interaction_id

EXCLUSIONS = frozenset(('/docs', '/docs/oauth2-redirect', '/openapi.json', '/redoc', '/favicon.ico'))
DOMAIN = frozenset(('works','platforms','work_availabilities','tags','tag_categories','tag_category_relationships',
                    'tag_relationships','work_tags','work_classifications','watchlist_entries','watch_history','api_audit_logs'))


class RequestAuditingMiddleware:
    """Create/finalize a request row without holding a business transaction open.

    No response is synthesized after accepted headers or a failed send callback.
    Failed persistence produces a bounded safe file event, not a recursive audit.
    """
    def __init__(self, app, database, logger, config, store=None, codes=None):
        self.app, self.logger, self.config = app, logger, config
        self.store = store if store is not None else AuditStore(database)
        self.codes = codes if codes is not None else load_error_codes()

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope['path'].rstrip('/') in EXCLUSIONS:
            return await self.app(scope, receive, send)
        identity = create_interaction_id()
        scope.setdefault('state', {})['interaction_id'] = identity
        started, clock = utcnow(), time.perf_counter()
        settings = self.config.get('audit', {})
        limit = lambda name: settings.get(name, 8192)
        state = AuditContext(identity, self.config.get('application_timezone', 'Europe/Lisbon'),
                             sensitive=sensitive_operation(scope['path']), mutation_limit=limit('mutation_max_bytes'))
        path = safe_path(scope['path'])
        context_token = request_context.set(RequestContext(identity, scope['method'], path))
        logger_token = active_logger.set(self.logger)
        audit_token = audit_context.set(state)
        request_capture = BodyCapture(limit('request_body_max_bytes'), 'sensitive_operation' if state.sensitive else None)
        response_capture = BodyCapture(limit('response_body_max_bytes'),
            'sensitive_operation' if state.sensitive else 'audit_read' if path.split('/')[1:2] == ['api_audit_logs'] else None)
        request_capture.content_type = dict(scope.get('headers', ())).get(b'content-type', b'').decode('latin1')
        sent, http_status, send_failed, cancelled, unexpected = False, None, False, False, False

        async def fallback(phase):
            try:
                await anyio.to_thread.run_sync(lambda: self.logger.log({'level':'ERROR', 'message':'API audit persistence failed',
                    'context':{'phase':phase, 'error_code':'AUDIT_UNAVAILABLE', 'audit_persisted':False}}))
            except Exception:
                # There is no further safe durable sink; never retry recursively.
                pass

        async def receive_once():
            message = await receive()
            if message['type'] == 'http.request':
                request_capture.feed(message.get('body', b''), not message.get('more_body', False))
            return message

        async def send_once(message):
            nonlocal sent, http_status, send_failed
            if message['type'] == 'http.response.start':
                headers = [(key,value) for key,value in message.get('headers', ()) if key.lower() != b'x-interaction-id']
                message = {**message, 'headers': headers + [(b'x-interaction-id', identity.encode())]}
                response_capture.content_type = dict(message['headers']).get(b'content-type', b'').decode('latin1')
            try:
                await send(message)
            except BaseException:
                send_failed = True
                state.error_code = 'TRANSPORT_FAILURE'
                raise
            if message['type'] == 'http.response.start':
                sent, http_status = True, message['status']
            elif message['type'] == 'http.response.body':
                response_capture.feed(message.get('body', b''), not message.get('more_body', False))

        try:
            raw_query = scope.get('query_string', b'')
            if len(raw_query) > limit('query_max_bytes'):
                query, query_flags = None, dict(omitted=True, truncated=True, reason='capture_limit')
            else:
                try:
                    parsed = parse_qsl(raw_query.decode('utf-8'), keep_blank_values=True, max_num_fields=256)
                    values = {}
                    for key, value in parsed:
                        if key in values:
                            previous = values[key]
                            values[key] = previous + [value] if isinstance(previous, list) else [previous, value]
                        else:
                            values[key] = value
                    query, query_flags = bounded_value(values, limit('query_max_bytes'))
                except (ValueError, UnicodeError):
                    query, query_flags = None, dict(omitted=True, truncated=False, reason='invalid_query')
            try:
                state.audit_id = await anyio.to_thread.run_sync(lambda: self.store.begin(state, started, scope['method'], path, query, query_flags))
            except Exception:
                await fallback('entry')
            try:
                await self.app(scope, receive_once, send_once)
            except asyncio.CancelledError:
                cancelled = True
                state.error_code = 'REQUEST_CANCELLED'
                raise
            except Exception:
                unexpected = True
                if state.error_code is None:
                    state.error_code = 'TRANSPORT_FAILURE' if send_failed else 'INTERNAL_ERROR'
                if not sent and not send_failed:
                    await error_response(self.codes, state.error_code)(scope, receive_once, send_once)
                else:
                    # The inner technical middleware already suppresses private text.
                    from app.main import ResponseStartedError
                    raise ResponseStartedError('Response transmission failed; inspect safe application diagnostics') from None
        except asyncio.CancelledError:
            cancelled = True
            state.error_code = 'REQUEST_CANCELLED'
            raise
        finally:
            try:
                with anyio.CancelScope(shield=True):
                    if http_status is not None and http_status >= 400 and state.error_code is None:
                        state.error_code = code_for(http_status, path=path)
                    failed = cancelled or unexpected or send_failed or state.error_code is not None or not response_capture.complete
                    status = 'failure' if failed else 'success'
                    route = getattr(scope.get('route'), 'path', None)
                    resource = (route or path).split('/')[1:2]
                    if state.resource is None and resource:
                        state.resource = {'users':'api_users','test':'test'}.get(resource[0], resource[0] if resource[0] in DOMAIN else None)
                    target = scope.get('path_params', {}).get('id')
                    if target is not None:
                        state.target_id = safe_path(str(target))
                    body, request_flags = request_capture.result()
                    response, response_flags = response_capture.result()
                    business = 'preview' if state.bulk and state.mutation_details.get('dry_run') else (
                        'rolled_back' if state.error_code is not None and scope['method'] in ('POST','PUT','PATCH','DELETE') and path.split('/')[1:2] != ['token']
                        else 'read_only')
                    if state.audit_id is not None:
                        try:
                            await anyio.to_thread.run_sync(lambda: self.store.finish(state,
                                duration=round((time.perf_counter()-clock)*1000,3), status=status, http_status=http_status,
                                response_started=sent, matched_route=route, request_body=body, response_body=response,
                                capture={'request':request_flags,'response':response_flags},
                                summary=f'{scope["method"]} {route or path}: {status}' + (
                                    f'; returned {state.mutation_details["returned_count"]}' if 'returned_count' in state.mutation_details else ''), outcome=business))
                        except Exception:
                            await fallback('finalization')
                    elif state.error_code is not None:
                        await fallback('missing_entry')
            finally:
                request_capture.clear()
                response_capture.clear()
                audit_context.reset(audit_token)
                active_logger.reset(logger_token)
                request_context.reset(context_token)
