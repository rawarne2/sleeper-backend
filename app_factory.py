"""Shared FastAPI application factory used by app.py and vercel_app.py."""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.middleware.wsgi import WSGIMiddleware
from starlette.routing import Mount

import models.entities  # noqa: F401 -- register ORM mappers
from flask_bridge import build_flask_bridge
from web.errors import register_exception_handlers
from web.middleware import DbSessionScopeMiddleware


def create_app(db_url: str, engine_options: dict[str, Any] | None = None) -> FastAPI:
    app = FastAPI(title="Sleeper Backend API", version="1.0.0")
    app.add_middleware(DbSessionScopeMiddleware)
    register_exception_handlers(app)

    # Migrated FastAPI routers are registered here in later tasks, e.g.:
    #   from routes.health import router as health_router
    #   app.include_router(health_router)
    # IMPORTANT: every app.include_router(...) MUST go ABOVE the bridge mount
    # below. The catch-all Mount("/") matches every path, so any router appended
    # after it is silently shadowed by the Flask bridge.

    # Mount the remaining Flask blueprints LAST so FastAPI routes/docs win and
    # everything else falls through to the bridge. Removed entirely in a later task.
    # Do not append any route after this line.
    app.router.routes.append(Mount("/", app=WSGIMiddleware(build_flask_bridge())))
    return app
