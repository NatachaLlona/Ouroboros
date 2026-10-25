"""Bound creation body bytes before JSON parsing without changing capture budgets."""
from app.errors import error_response

CREATION_PATHS = frozenset(('/test', '/works', '/platforms', '/work_availabilities', '/tags',
    '/tag_categories', '/tag_category_relationships', '/tag_relationships', '/work_classifications',
    '/watchlist_entries', '/watch_history', '/work_tags'))


class CreationBodyLimitMiddleware:
    def __init__(self, app, config, codes):
        self.app, self.codes, self.config = app, codes, config

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope['method'] != 'POST' or scope['path'].rstrip('/') not in CREATION_PATHS:
            return await self.app(scope, receive, send)
        body = bytearray()
        limit = self.config.get('api', {}).get('max_creation_body_bytes', 4 * 1024 * 1024)
        while True:
            message = await receive()
            if message['type'] != 'http.request':
                return
            data = message.get('body', b'')
            if len(body) + len(data) > limit:
                body.clear()
                return await error_response(self.codes, 'VALIDATION_ERROR', details=[{
                    'loc': ['body'], 'type': 'creation_body_too_large',
                    'msg': 'Request exceeds configured api.max_creation_body_bytes.'}])(scope, receive, send)
            body.extend(data)
            if not message.get('more_body', False):
                break
        delivered = False

        async def replay():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {'type': 'http.request', 'body': bytes(body), 'more_body': False}
            return await receive()

        try:
            return await self.app(scope, replay, send)
        finally:
            body.clear()
