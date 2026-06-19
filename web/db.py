"""Request-scoped SQLAlchemy session dependency for FastAPI routes.

During the migration to explicit sessions this yields the same scoped session the
legacy global ``models.extensions.db.session`` resolves to (its scope is set per
request by ``web.middleware.DbSessionScopeMiddleware``), so handlers using
``session = Depends(get_db)`` and code still using the global ``db.session`` share
one session/transaction per request. Session removal is owned by the middleware,
so this dependency intentionally does NOT remove/close the session.
"""
from collections.abc import Iterator

from sqlalchemy.orm import Session

from models.extensions import db


def get_db() -> Iterator[Session]:
    yield db.session
