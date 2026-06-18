"""The FastAPI app must boot and serve existing Flask routes through the WSGI bridge."""
from starlette.testclient import TestClient

from app import app  # FastAPI app after Task 2


def test_legacy_route_served_through_bridge():
    # /api/maintenance/health is still a Flask blueprint served via the WSGI bridge
    # (migrated to native FastAPI later). KTC/health is now native, so this proves
    # the bridge still routes unmigrated paths.
    client = TestClient(app)
    resp = client.get("/api/maintenance/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_openapi_docs_available():
    client = TestClient(app)
    assert client.get("/openapi.json").status_code == 200
    assert client.get("/docs").status_code == 200


def test_cors_preflight_allows_vercel_preview():
    from starlette.testclient import TestClient
    client = TestClient(app)
    resp = client.options("/api/ktc/health", headers={
        "Origin": "https://my-preview.vercel.app",
        "Access-Control-Request-Method": "GET",
    })
    assert resp.headers.get("access-control-allow-origin") == "https://my-preview.vercel.app"
