"""Shared CORS configuration for the Flask app.

Used by both ``app.py`` (local dev) and ``vercel_app.py`` (production) so the
allow list and headers stay in lock-step.
"""
from __future__ import annotations

import re
from typing import Iterable

from flask import Flask, make_response, request
from flask_cors import CORS

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


def configure_cors(app: Flask, *, extra_origins: Iterable[str] = ()) -> None:
    """Wire up CORS on the given Flask app.

    Adds ``Flask-CORS`` for the canonical allow list, plus a manual ``after_request``
    handler that handles dynamic origins (Vercel preview URLs and local network IPs)
    that ``Flask-CORS`` regex matching does not handle reliably.
    """
    origins = [*EXPLICIT_ORIGINS, *extra_origins]

    CORS(
        app,
        resources={
            r"/api/*": {
                "origins": origins + [r"https://.*\.vercel\.app"],
                "methods": [m.strip() for m in ALLOW_METHODS.split(",")],
                "allow_headers": [h.strip() for h in ALLOW_HEADERS.split(",")],
                "supports_credentials": True,
            }
        },
    )

    @app.before_request
    def _handle_preflight():
        if request.method != "OPTIONS":
            return None
        origin = request.headers.get("Origin")
        if not is_allowed_origin(origin):
            return None
        resp = make_response()
        resp.headers["Access-Control-Allow-Origin"] = origin
        resp.headers["Access-Control-Allow-Credentials"] = "true"
        resp.headers["Access-Control-Allow-Methods"] = ALLOW_METHODS
        resp.headers["Access-Control-Allow-Headers"] = ALLOW_HEADERS
        return resp

    @app.after_request
    def _cors_after_request(response):
        origin = request.headers.get("Origin")
        if not origin or not request.path.startswith("/api/"):
            return response
        if is_allowed_origin(origin):
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Access-Control-Allow-Methods"] = ALLOW_METHODS
            response.headers["Access-Control-Allow-Headers"] = ALLOW_HEADERS
        return response
