"""The FastAPI app must boot and serve existing Flask routes through the WSGI bridge."""
from starlette.testclient import TestClient

from app import app  # FastAPI app after Task 2


def test_health_served_through_bridge():
    client = TestClient(app)
    resp = client.get("/api/ktc/health")
    assert resp.status_code in (200, 500)
    body = resp.json()
    assert body["status"] in ("healthy", "unhealthy")


def test_openapi_docs_available():
    client = TestClient(app)
    assert client.get("/openapi.json").status_code == 200
    assert client.get("/docs").status_code == 200
