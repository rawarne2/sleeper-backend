"""Shared FastAPI application factory used by app.py and vercel_app.py."""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.middleware.wsgi import WSGIMiddleware
from starlette.routing import Mount

import models.entities  # noqa: F401 -- register ORM mappers
from flask_bridge import build_flask_bridge
from web.middleware import DbSessionScopeMiddleware


def create_app(db_url: str, engine_options: dict[str, Any] | None = None) -> FastAPI:
    app = FastAPI(title="Sleeper Backend API", version="1.0.0")
    app.add_middleware(DbSessionScopeMiddleware)

    # Migrated FastAPI routers are registered here in later tasks, e.g.:
    #   from routes.health import router as health_router
    #   app.include_router(health_router)

    # Mount the remaining Flask blueprints LAST so FastAPI routes/docs win and
    # everything else falls through to the bridge. Removed entirely in a later task.
    app.router.routes.append(Mount("/", app=WSGIMiddleware(build_flask_bridge())))
    return app
