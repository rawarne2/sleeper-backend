"""Shared FastAPI application factory used by app.py and vercel_app.py."""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.wsgi import WSGIMiddleware
from starlette.routing import Mount
from starlette_compress import CompressMiddleware

import models.entities  # noqa: F401 -- register ORM mappers
from flask_bridge import build_flask_bridge
from utils.cors import EXPLICIT_ORIGINS
from web.errors import register_exception_handlers
from web.middleware import DbSessionScopeMiddleware

_CORS_ORIGIN_REGEX = (
    r"^https://.*\.vercel\.app$"
    r"|^http://(192\.168\.\d{1,3}\.\d{1,3}|10\.\d{1,3}\.\d{1,3}\.\d{1,3}"
    r"|172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})(:\d+)?$"
)


def create_app(db_url: str, engine_options: dict[str, Any] | None = None) -> FastAPI:
    app = FastAPI(title="Sleeper Backend API", version="1.0.0")
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

    # Migrated FastAPI routers. IMPORTANT: every app.include_router(...) MUST go
    # ABOVE the bridge mount below. The catch-all Mount("/") matches every path, so
    # any router appended after it is silently shadowed by the Flask bridge.
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

    # Mount the remaining Flask blueprints LAST so FastAPI routes/docs win and
    # everything else falls through to the bridge. Removed entirely in a later task.
    # Do not append any route after this line.
    app.router.routes.append(Mount("/", app=WSGIMiddleware(build_flask_bridge())))
    return app
