"""Shared Flask application factory used by app.py and vercel_app.py."""
from __future__ import annotations

import logging
from typing import Any

from flask import Flask
from flask_compress import Compress
from flask_migrate import Migrate

import models.entities  # noqa: F401 — register ORM mappers before create_all
from models.extensions import db
from routes.registry import register_blueprints
from routes.swagger_config import add_documentation_routes, setup_swagger
from utils.cors import configure_cors

logger = logging.getLogger(__name__)


def create_app(
    db_url: str,
    engine_options: dict[str, Any] | None = None,
    swagger_host: str = "localhost:5001",
    swagger_schemes: list[str] | None = None,
) -> Flask:
    """Create and configure a Flask application instance.

    Each entrypoint (app.py, vercel_app.py) is responsible for:
    - Resolving and normalizing db_url
    - Building environment-appropriate engine_options
    - Calling initialize_database() at the right time
    """
    if swagger_schemes is None:
        swagger_schemes = ["http", "https"]

    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = db_url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    if engine_options:
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = engine_options

    db.init_app(app)
    Migrate(app, db)
    Compress(app)
    configure_cors(app)
    setup_swagger(app, host=swagger_host, schemes=swagger_schemes)
    register_blueprints(app)
    add_documentation_routes(app, logger)

    return app
