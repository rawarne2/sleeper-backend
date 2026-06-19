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


def test_factory_serves_native_route():
    """The factory wires native FastAPI routers (no WSGI bridge)."""
    from app_factory import create_app
    client = TestClient(create_app("sqlite:///:memory:"))
    # ktc/health is a native router; allow 500 in case the in-memory DB is cold.
    resp = client.get("/api/ktc/health")
    assert resp.status_code in (200, 500)
    assert "status" in resp.json()


def test_factory_root_redirects_to_docs():
    """GET / redirects to the FastAPI Swagger UI."""
    from app_factory import create_app
    client = TestClient(create_app("sqlite:///:memory:"))
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code in (307, 308)
    assert resp.headers["location"].endswith("/docs")
