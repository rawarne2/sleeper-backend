"""Tests for the native FastAPI maintenance routes."""


def test_maintenance_health_ok(client):
    resp = client.get("/api/maintenance/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_nightly_sync_requires_auth_get(client, monkeypatch):
    monkeypatch.delenv("CRON_SECRET", raising=False)
    monkeypatch.delenv("VERCEL_ENV", raising=False)
    resp = client.get("/api/maintenance/nightly-sync")
    assert resp.status_code == 401
    assert resp.json()["status"] == "error"


def test_nightly_sync_requires_auth_post(client, monkeypatch):
    monkeypatch.delenv("CRON_SECRET", raising=False)
    monkeypatch.delenv("VERCEL_ENV", raising=False)
    resp = client.post("/api/maintenance/nightly-sync")
    assert resp.status_code == 401
    assert resp.json()["status"] == "error"


def test_nightly_sync_401_has_hint(client, monkeypatch):
    monkeypatch.delenv("CRON_SECRET", raising=False)
    monkeypatch.delenv("VERCEL_ENV", raising=False)
    resp = client.post("/api/maintenance/nightly-sync")
    assert resp.status_code == 401
    body = resp.json()
    assert "hint" in body
    assert "CRON_SECRET" in body["hint"]


def test_prewarm_requires_auth(client, monkeypatch):
    monkeypatch.delenv("CRON_SECRET", raising=False)
    monkeypatch.delenv("VERCEL_ENV", raising=False)
    resp = client.get("/api/maintenance/prewarm")
    assert resp.status_code == 401
    assert resp.json()["status"] == "error"


def test_prewarm_401_has_no_hint(client, monkeypatch):
    monkeypatch.delenv("CRON_SECRET", raising=False)
    monkeypatch.delenv("VERCEL_ENV", raising=False)
    resp = client.get("/api/maintenance/prewarm")
    assert resp.status_code == 401
    body = resp.json()
    # prewarm raises ApiError("Unauthorized", 401) with NO hint kwarg
    assert "hint" not in body
