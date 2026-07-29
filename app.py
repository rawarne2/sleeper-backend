import os

import sqlalchemy.exc
from dotenv import load_dotenv

from app_factory import create_app
from utils.constants import DATABASE_URI
from utils.helpers import setup_logging

load_dotenv()
logger = setup_logging(__name__)

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

from models.extensions import db
# For in-memory SQLite (tests/local), force a single shared connection so the
# scoped session sees the same DB across threads (FastAPI runs sync handlers in a
# threadpool). Harmless for file/Postgres URLs.
if database_uri.startswith("sqlite") and ":memory:" in database_uri:
    from sqlalchemy.pool import StaticPool
    engine_options = {**engine_options, "poolclass": StaticPool,
                      "connect_args": {**engine_options.get("connect_args", {}),
                                       "check_same_thread": False}}
db.configure(database_uri, engine_options or None)

app = create_app(db_url=database_uri, engine_options=engine_options)


def initialize_database() -> bool:
    """Initialize the database tables with proper error handling."""
    from models.extensions import db
    from sqlalchemy import inspect
    try:
        db.create_all()
        logger.info("Database tables initialized successfully")
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()
        logger.info("Available tables: %s", tables)
        return True
    except (sqlalchemy.exc.SQLAlchemyError, ConnectionError, OSError) as e:
        logger.error("Database initialization failed: %s", e)
        return False


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5001)
