"""Trust client forwarding only from the configured frontend service address."""
import ipaddress
import socket
import os
import anyio


class FrontendProxyMiddleware:
    def __init__(self, app):
        self.app = app
        self.proxy = os.environ.get('OUROBOROS_BROWSER_PROXY_HOST')

    async def __call__(self, scope, receive, send):
        if scope['type'] == 'http' and self.proxy and scope.get('client') and b'x-forwarded-for' in dict(scope.get('headers', [])):
            try:
                addresses = await anyio.to_thread.run_sync(lambda: {item[4][0] for item in socket.getaddrinfo(self.proxy, None)})
            except OSError:
                addresses = set()
            if scope['client'][0] in addresses:
                scope = dict(scope)
                scope['verified_frontend_proxy'] = True
                forwarded = dict(scope.get('headers', [])).get(b'x-forwarded-for')
                if forwarded:
                    try:
                        address = str(ipaddress.ip_address(forwarded.decode('ascii')))
                        scope['client'] = (address, 0)
                    except (ValueError, UnicodeError):
                        scope['verified_frontend_proxy'] = False
        await self.app(scope, receive, send)
