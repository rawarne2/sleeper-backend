"""Smoke tests for the pure-FastAPI app (no Flask/WSGI bridge anymore)."""
from starlette.testclient import TestClient

from app import app  # FastAPI app


def test_native_route_responds():
    # A native FastAPI route is wired and handled (not a 404 from a missing
    # router). ktc/health hits the DB, so allow 500 in case the test DB is cold.
    client = TestClient(app)
    resp = client.get("/api/ktc/health")
    assert resp.status_code in (200, 500)
    assert "status" in resp.json()


def test_openapi_docs_available():
    client = TestClient(app)
    assert client.get("/openapi.json").status_code == 200
    assert client.get("/docs").status_code == 200


def test_cors_preflight_allows_vercel_preview():
    client = TestClient(app)
    resp = client.options("/api/ktc/health", headers={
        "Origin": "https://my-preview.vercel.app",
        "Access-Control-Request-Method": "GET",
    })
    assert resp.headers.get("access-control-allow-origin") == "https://my-preview.vercel.app"
