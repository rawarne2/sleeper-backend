"""Shared CORS configuration for the FastAPI app.

``EXPLICIT_ORIGINS`` and the regexes are consumed by ``app_factory.create_app``
so the allow list and headers stay in lock-step across local dev and production.
"""
from __future__ import annotations

import re

EXPLICIT_ORIGINS: tuple[str, ...] = (
    "http://localhost:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:3001",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "https://sleeper-dashboard-xi.vercel.app",
)

ALLOW_HEADERS = "Content-Type, Authorization, X-Requested-With, Accept, Origin"
ALLOW_METHODS = "GET, POST, PUT, DELETE, OPTIONS"

LOCAL_NETWORK_REGEX = re.compile(
    r"^http://(192\.168\.\d{1,3}\.\d{1,3}|10\.\d{1,3}\.\d{1,3}\.\d{1,3}|"
    r"172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})(:\d+)?$"
)
VERCEL_REGEX = re.compile(r"^https://.*\.vercel\.app$")


def is_allowed_origin(origin: str | None) -> bool:
    if not origin:
        return False
    if origin in EXPLICIT_ORIGINS:
        return True
    if LOCAL_NETWORK_REGEX.match(origin):
        return True
    if VERCEL_REGEX.match(origin):
        return True
    return False
