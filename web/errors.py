"""FastAPI exception handlers producing the canonical JSON error envelope.

Body shape: ``status``, ``error``, RFC 3339 ``timestamp``, optional ``details``.
"""
from __future__ import annotations

import json
from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from utils.datetime_serialization import utc_now_rfc3339
from utils.helpers import setup_logging

logger = setup_logging(__name__)


def _detail_to_str(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, default=str)
    return str(value)


def error_body(message: str, *, details: Any = None, **extra: Any) -> dict[str, Any]:
    body: dict[str, Any] = {"status": "error", "error": message,
                            "timestamp": utc_now_rfc3339()}
    if details is not None:
        body["details"] = _detail_to_str(details)
    body.update(extra)
    return body


class ApiError(Exception):
    """Raise from any route to emit the standard error envelope."""

    def __init__(self, message: str, status_code: int = 400, *,
                 details: Any = None, **extra: Any) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.details = details
        self.extra = extra


async def _api_error_handler(_: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse(error_body(exc.message, details=exc.details, **exc.extra),
                        status_code=exc.status_code)


async def _validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    # Map FastAPI's default 422 to the project's 400 envelope (client contract).
    return JSONResponse(error_body("Invalid request parameters",
                                   details=exc.errors()), status_code=400)


async def _http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(error_body(str(exc.detail)), status_code=exc.status_code,
                        headers=exc.headers)


async def _unhandled_handler(_: Request, exc: Exception) -> JSONResponse:
    logger.error("Unexpected error: %s", exc)
    return JSONResponse(error_body("Internal server error", details=str(exc)),
                        status_code=500)


def register_exception_handlers(app) -> None:
    app.add_exception_handler(ApiError, _api_error_handler)
    app.add_exception_handler(RequestValidationError, _validation_handler)
    app.add_exception_handler(HTTPException, _http_exception_handler)
    app.add_exception_handler(Exception, _unhandled_handler)
