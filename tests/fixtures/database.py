"""
Database test fixtures and utilities.
"""
import os
import pytest

os.environ.setdefault('TEST_DATABASE_URI', 'sqlite:///:memory:')

from app import app
from cache import redis_rankings as _redis_rankings
from models.extensions import db


def _disable_redis():
    """
    Force ``get_redis_client()`` to return None during a test so cached
    payloads in any shared Redis instance cannot leak across runs and
    silently short-circuit route logic. Empty REDIS_URL is treated as
    "not configured" by ``cache/redis_rankings.py``.
    """
    os.environ['REDIS_URL'] = ''
    holder = _redis_rankings._redis_holder
    cached = holder[0]
    if cached is not None and not isinstance(cached, float):
        try:
            cached.close()
        except Exception:
            pass
    holder[0] = None


@pytest.fixture
def client():
    """Create test client with in-memory database."""
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    _disable_redis()

    with app.test_client() as client:
        with app.app_context():
            db.create_all()
            yield client
            db.session.remove()
            db.drop_all()


@pytest.fixture
def app_context():
    """Create app context for database operations."""
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    _disable_redis()

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()
