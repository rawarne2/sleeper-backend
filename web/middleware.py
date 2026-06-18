"""Pure-ASGI middleware that scopes the shim's db.session to one request.

Implemented as raw ASGI (not BaseHTTPMiddleware) so the ContextVar set here
propagates into the threadpool worker that runs sync endpoints / the WSGI bridge,
and the matching db.session.remove() in `finally` targets the same scope key
regardless of thread.
"""
from models.extensions import clear_request_scope, db, set_request_scope


class DbSessionScopeMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        token = set_request_scope()
        try:
            await self.app(scope, receive, send)
        finally:
            db.session.remove()
            clear_request_scope(token)
