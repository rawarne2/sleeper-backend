"""Framework-neutral SQLAlchemy access layer (replaces Flask-SQLAlchemy).

Exposes a small ``db`` facade mimicking the subset of the Flask-SQLAlchemy API the
codebase uses (``db.Model``, ``db.session``, ``db.Column`` & friends, ``db.create_all``/
``db.drop_all``/``db.engine``), backed by a plain SQLAlchemy engine + ``scoped_session``.

The session is scoped per logical request via a ContextVar set by the ASGI middleware
(``web/middleware.py``); for background worker threads and scripts (no request context) it
falls back to the current thread id. ``session_scope()`` gives non-request callers
(threads/CLI/scripts) a clean unit-of-work that removes the session on exit.
"""
from __future__ import annotations

import threading
from contextlib import contextmanager
from contextvars import ContextVar

import sqlalchemy as sa
from sqlalchemy import orm
from sqlalchemy.engine import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, scoped_session, sessionmaker

_request_scope: ContextVar[object | None] = ContextVar("db_request_scope", default=None)


def _scope_id() -> object:
    token = _request_scope.get()
    return token if token is not None else threading.get_ident()


def set_request_scope() -> object:
    """Begin a per-request scope; return a reset token for ``clear_request_scope``."""
    return _request_scope.set(object())


def clear_request_scope(token) -> None:
    _request_scope.reset(token)


class _Db:
    def __init__(self) -> None:
        self.Column = sa.Column
        self.Integer = sa.Integer
        self.BigInteger = sa.BigInteger
        self.String = sa.String
        self.Text = sa.Text
        self.DateTime = sa.DateTime
        self.Date = sa.Date
        self.Boolean = sa.Boolean
        self.Numeric = sa.Numeric
        self.Float = sa.Float
        self.ForeignKey = sa.ForeignKey
        self.UniqueConstraint = sa.UniqueConstraint
        self.Index = sa.Index
        self.JSON = sa.JSON
        self.relationship = orm.relationship

        class Base(DeclarativeBase):
            pass

        self.Model = Base
        self._engine: Engine | None = None
        self.session: scoped_session | None = None

    def configure(self, db_url: str, engine_options: dict | None = None) -> Engine:
        """Create the engine + scoped session. Safe to call again (rebinds)."""
        if self._engine is not None:
            self.session.remove()
            self._engine.dispose()
        opts = dict(engine_options or {})
        # In-memory SQLite must share ONE connection across threads (FastAPI runs
        # sync handlers in a threadpool), otherwise each thread sees its own empty
        # DB or hits "objects created in a thread can only be used in that thread".
        # Applied here so every caller (entrypoints, tests, scripts) is thread-safe.
        if db_url.startswith("sqlite") and ":memory:" in db_url:
            from sqlalchemy.pool import StaticPool
            opts.setdefault("poolclass", StaticPool)
            connect_args = dict(opts.get("connect_args") or {})
            connect_args.setdefault("check_same_thread", False)
            opts["connect_args"] = connect_args
        self._engine = create_engine(db_url, future=True, **opts)
        factory = sessionmaker(bind=self._engine, autoflush=False,
                               autocommit=False, future=True)
        self.session = scoped_session(factory, scopefunc=_scope_id)
        # Model.query is intentionally not provided; use db.session + select()
        return self._engine

    @property
    def engine(self) -> Engine:
        assert self._engine is not None, "db.configure() was not called"
        return self._engine

    @property
    def metadata(self):
        return self.Model.metadata

    def create_all(self) -> None:
        self.metadata.create_all(self.engine)

    def drop_all(self) -> None:
        self.metadata.drop_all(self.engine)


db = _Db()


@contextmanager
def session_scope():
    """Per-unit-of-work scope for threads/CLI/scripts; removes the session on exit."""
    token = set_request_scope()
    try:
        yield db.session
    finally:
        db.session.remove()
        clear_request_scope(token)
