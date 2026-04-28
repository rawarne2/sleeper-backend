"""Vercel-compatible Flask application with Supabase integration."""
import os
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import sqlalchemy.exc
from dotenv import load_dotenv
from flask import Flask
from flask_compress import Compress
from sqlalchemy.pool import NullPool

import models.entities  # noqa: F401 — register ORM mappers
from models.extensions import db
from routes.registry import register_blueprints
from routes.swagger_config import add_documentation_routes, setup_swagger
from utils.cors import configure_cors
from utils.helpers import setup_logging

load_dotenv()
logger = setup_logging()

app = Flask(__name__)

database_uri = (
    os.getenv("POSTGRES_URL")
    or os.getenv("POSTGRES_PRISMA_URL")
    or os.getenv("DATABASE_URL")
    or os.getenv("POSTGRES_URL_NON_POOLING")
    or os.getenv("TEST_DATABASE_URI", "sqlite:///sleeper_local.db")
)

if database_uri and database_uri.startswith("postgres://"):
    database_uri = database_uri.replace("postgres://", "postgresql://", 1)

if database_uri and database_uri.startswith("postgresql://"):
    try:
        parsed = urlparse(database_uri)
        query_params = parse_qs(parsed.query)
        allowed_params = {
            "sslmode",
            "connect_timeout",
            "application_name",
            "sslcert",
            "sslkey",
            "sslrootcert",
            "sslcrl",
        }
        cleaned_params = {k: v for k, v in query_params.items() if k in allowed_params}
        cleaned_query = urlencode(cleaned_params, doseq=True)
        cleaned_parsed = parsed._replace(query=cleaned_query)
        database_uri = urlunparse(cleaned_parsed)
        logger.info("Cleaned database URI parameters")
    except (ValueError, TypeError) as e:
        logger.warning("Failed to clean database URI: %s", e)

logger.info("Using database connection: %s...", database_uri[:50])

engine_options: dict = {}
if not database_uri.startswith("sqlite://"):
    engine_options = {
        "poolclass": NullPool,
        "connect_args": {
            "sslmode": "require",
            "connect_timeout": 10,
            "options": "-c timezone=UTC -c statement_timeout=15000",
        },
    }

app.config.update(
    {
        "SQLALCHEMY_DATABASE_URI": database_uri,
        "SQLALCHEMY_TRACK_MODIFICATIONS": False,
        "SQLALCHEMY_ENGINE_OPTIONS": engine_options,
    }
)

db.init_app(app)
Compress(app)
configure_cors(app)

swagger = setup_swagger(app, host="sleeper-backend.vercel.app", schemes=["https"])

register_blueprints(app)


def initialize_database() -> bool:
    """Initialize the database tables with proper error handling."""
    try:
        with app.app_context():
            db.create_all()
            logger.info("Database tables initialized successfully")

            from sqlalchemy import inspect

            inspector = inspect(db.engine)
            tables = inspector.get_table_names()
            logger.info("Available tables: %s", tables)
            return True
    except (sqlalchemy.exc.SQLAlchemyError, ConnectionError, OSError) as e:
        logger.error("Database initialization failed: %s", e)
        return False


if not initialize_database():
    logger.error("Application will continue but database operations may fail")

add_documentation_routes(app, logger)
