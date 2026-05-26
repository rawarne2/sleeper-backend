"""Vercel-compatible Flask application with Supabase integration."""
import os
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import sqlalchemy.exc
from dotenv import load_dotenv
from sqlalchemy.pool import NullPool

from app_factory import create_app
from models.extensions import db
from utils.helpers import setup_logging

load_dotenv()
logger = setup_logging()


def _resolve_vercel_db_url() -> str:
    """Resolve and normalize the database URL for Vercel/Supabase."""
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
    return database_uri


database_uri = _resolve_vercel_db_url()

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

app = create_app(
    db_url=database_uri,
    engine_options=engine_options,
    swagger_host="sleeper-backend.vercel.app",
    swagger_schemes=["https"],
)


def initialize_database() -> bool:
    """Initialize the database tables with proper error handling."""
    from sqlalchemy import inspect
    try:
        with app.app_context():
            db.create_all()
            logger.info("Database tables initialized successfully")
            inspector = inspect(db.engine)
            tables = inspector.get_table_names()
            logger.info("Available tables: %s", tables)
            return True
    except (sqlalchemy.exc.SQLAlchemyError, ConnectionError, OSError) as e:
        logger.error("Database initialization failed: %s", e)
        return False


if not initialize_database():
    logger.error("Application will continue but database operations may fail")
