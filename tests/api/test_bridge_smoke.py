"""The FastAPI app must boot and serve existing Flask routes through the WSGI bridge."""
from starlette.testclient import TestClient

from app import app  # FastAPI app after Task 2


def test_legacy_route_served_through_bridge():
    # /api/trade-analyzer/providers is still a Flask blueprint served via the WSGI
    # bridge (dashboard and players/all are now native FastAPI). This proves the
    # bridge still routes unmigrated paths.
    client = TestClient(app)
    resp = client.get("/api/trade-analyzer/providers")
    # The route is live and handled (200 JSON, no external calls in tests) — a
    # non-404 status proves the bridge routes the path rather than the native
    # router returning 404.
    assert resp.status_code == 200


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
