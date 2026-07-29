"""Shared FastAPI application factory used by app.py and vercel_app.py."""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from starlette_compress import CompressMiddleware

import models.entities  # noqa: F401 -- register ORM mappers
import services.valuations.sources  # noqa: F401 -- register default valuation sources
from utils.cors import EXPLICIT_ORIGINS
from web.errors import register_exception_handlers
from web.middleware import DbSessionScopeMiddleware
from web.observability import RequestContextMiddleware
from web.openapi import (
    OPENAPI_DESCRIPTION,
    OPENAPI_TAGS,
    OPENAPI_TITLE,
    OPENAPI_VERSION,
)

_CORS_ORIGIN_REGEX = (
    r"^https://.*\.vercel\.app$"
    r"|^http://(192\.168\.\d{1,3}\.\d{1,3}|10\.\d{1,3}\.\d{1,3}\.\d{1,3}"
    r"|172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})(:\d+)?$"
)


def create_app(db_url: str, engine_options: dict[str, Any] | None = None) -> FastAPI:
    app = FastAPI(
        title=OPENAPI_TITLE,
        version=OPENAPI_VERSION,
        description=OPENAPI_DESCRIPTION,
        openapi_tags=OPENAPI_TAGS,
    )
    app.add_middleware(DbSessionScopeMiddleware)
    register_exception_handlers(app)

    app.add_middleware(CompressMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(EXPLICIT_ORIGINS),
        allow_origin_regex=_CORS_ORIGIN_REGEX,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "X-Requested-With", "Accept", "Origin"],
    )
    # Added last so it is the outermost middleware: its request-id ContextVar,
    # timing header, and per-request log line then wrap CORS/compression and
    # cover every response.
    app.add_middleware(RequestContextMiddleware)

    from routes.health import router as health_router
    from routes.ktc.rankings import router as ktc_rankings_router
    from routes.ktc.bulk import router as ktc_bulk_router
    from routes.sleeper.players import router as sleeper_players_router
    from routes.sleeper.leagues import router as sleeper_leagues_router
    from routes.sleeper.research import router as sleeper_research_router
    from routes.sleeper.stats import router as sleeper_stats_router
    from routes.maintenance import router as maintenance_router
    from routes.dashboard_league import router as dashboard_router
    from routes.players_all import router as players_all_router
    from routes.trade_analyzer import router as trade_analyzer_router
    from routes.valuations import router as valuations_router
    app.include_router(health_router)
    app.include_router(ktc_rankings_router)
    app.include_router(ktc_bulk_router)
    app.include_router(sleeper_players_router)
    app.include_router(sleeper_leagues_router)
    app.include_router(sleeper_research_router)
    app.include_router(sleeper_stats_router)
    app.include_router(maintenance_router)
    app.include_router(dashboard_router)
    app.include_router(players_all_router)
    app.include_router(trade_analyzer_router)
    app.include_router(valuations_router)

    @app.get("/", include_in_schema=False)
    def index():
        return RedirectResponse(url="/docs")

    return app
