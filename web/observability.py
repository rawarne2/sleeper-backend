"""Sentry init and request-id/timing middleware (pure ASGI, ContextVar-safe)."""
from __future__ import annotations

import logging
import os
import time
import uuid

from utils.request_context import request_id_var

logger = logging.getLogger(__name__)


class RequestContextMiddleware:
    """Generate/propagate X-Request-ID, add X-Response-Time-Ms, log one line per request."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        incoming = dict(scope.get("headers") or []).get(b"x-request-id", b"")
        request_id = incoming.decode("latin-1").strip() or uuid.uuid4().hex
        token = request_id_var.set(request_id)
        start = time.perf_counter()
        status = {"code": None}

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
                headers = message.setdefault("headers", [])
                headers.append((b"x-request-id", request_id.encode("latin-1")))
                elapsed = (time.perf_counter() - start) * 1000
                headers.append((b"x-response-time-ms", f"{elapsed:.1f}".encode("latin-1")))
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            elapsed = (time.perf_counter() - start) * 1000
            logger.info("request method=%s path=%s status=%s ms=%.1f",
                        scope.get("method"), scope.get("path"), status["code"], elapsed)
            request_id_var.reset(token)


def init_sentry() -> bool:
    """Initialize Sentry when SENTRY_DSN is set; safe no-op otherwise."""
    dsn = (os.getenv("SENTRY_DSN") or "").strip()
    if not dsn:
        return False
    import sentry_sdk
    sentry_sdk.init(
        dsn=dsn,
        environment=os.getenv("VERCEL_ENV") or "local",
        traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0")),
        send_default_pii=False,
    )
    logger.info("sentry initialized environment=%s", os.getenv("VERCEL_ENV") or "local")
    return True
