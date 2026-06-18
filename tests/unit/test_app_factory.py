"""Tests for the shared app factory (now a FastAPI factory)."""
from fastapi import FastAPI
from starlette.testclient import TestClient


def test_create_app_returns_fastapi_app():
    """Factory returns a configured FastAPI application."""
    from app_factory import create_app
    app = create_app("sqlite:///:memory:")
    assert isinstance(app, FastAPI)


def test_create_app_accepts_engine_options():
    """Engine options are accepted without error (resolution happens in db.configure)."""
    from app_factory import create_app
    app = create_app("sqlite:///:memory:", engine_options={"pool_pre_ping": True})
    assert isinstance(app, FastAPI)


def test_factory_serves_openapi_docs():
    """FastAPI owns the OpenAPI schema and Swagger UI."""
    from app_factory import create_app
    client = TestClient(create_app("sqlite:///:memory:"))
    assert client.get("/openapi.json").status_code == 200
    assert client.get("/docs").status_code == 200


def test_factory_bridges_legacy_flask_routes():
    """Unmigrated routes fall through the WSGI bridge to the Flask blueprints."""
    from app_factory import create_app
    client = TestClient(create_app("sqlite:///:memory:"))
    # /api/maintenance/health is still a Flask blueprint (KTC/health is now native).
    resp = client.get("/api/maintenance/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
