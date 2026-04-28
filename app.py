import os

from dotenv import load_dotenv
from flask import Flask
from flask_compress import Compress

import models.entities  # noqa: F401 — register ORM mappers
from models.extensions import db
from routes.registry import register_blueprints
from routes.swagger_config import add_documentation_routes, setup_swagger
from utils.constants import DATABASE_URI
from utils.cors import configure_cors
from utils.helpers import setup_logging

load_dotenv()
logger = setup_logging()

app = Flask(__name__)

database_uri = os.getenv("TEST_DATABASE_URI", DATABASE_URI)

engine_options: dict = {}
if not database_uri.startswith("sqlite://"):
    engine_options = {
        "pool_pre_ping": True,
        "pool_recycle": 3600,
        "pool_size": 10,
        "max_overflow": 20,
        "connect_args": {"options": "-c timezone=UTC"},
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

swagger = setup_swagger(app, host="localhost:5001", schemes=["http", "https"])

register_blueprints(app)
add_documentation_routes(app, logger)

# Flask-DebugToolbar: opt-in via ENABLE_DEBUG_TOOLBAR=1; requires SECRET_KEY. Vercel uses vercel_app.
if not os.getenv("VERCEL") and os.getenv("ENABLE_DEBUG_TOOLBAR", "").strip().lower() in (
    "1",
    "true",
    "yes",
):
    secret = os.getenv("SECRET_KEY", "").strip()
    if secret:
        app.config["SECRET_KEY"] = secret
        app.config["DEBUG_TB_ENABLED"] = True
        app.config["DEBUG_TB_INTERCEPT_REDIRECTS"] = False
        from flask_debugtoolbar import DebugToolbarExtension

        DebugToolbarExtension(app)
    else:
        logger.warning(
            "ENABLE_DEBUG_TOOLBAR is set but SECRET_KEY is missing; Flask-DebugToolbar not loaded"
        )


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
    except Exception as e:
        logger.error("Database initialization failed: %s", e)
        return False


@app.cli.command("init_db")
def init_db():
    """Initialize the database tables."""
    if initialize_database():
        logger.info("Database initialized successfully via CLI")
    else:
        logger.error("Database initialization failed via CLI")
        exit(1)


@app.cli.command("create_tables")
def create_tables():
    """Create all database tables including new Sleeper models."""
    initialize_database()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
