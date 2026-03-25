"""Tests for GET /api/dashboard/league/:id."""
import json
from unittest.mock import patch


def test_dashboard_requires_season(client):
    r = client.get("/api/dashboard/league/123")
    assert r.status_code == 400
    data = json.loads(r.data)
    assert data.get("status") == "error"


def test_dashboard_invalid_season_length(client):
    r = client.get("/api/dashboard/league/123?season=25")
    assert r.status_code == 400


def test_dashboard_league_missing_from_db(client):
    r = client.get(
        "/api/dashboard/league/9999999999999999999"
        "?season=2025&league_format=superflex&is_redraft=false&tep_level=tep"
    )
    assert r.status_code == 404


def test_nightly_sync_unauthorized_without_secret(client, monkeypatch):
    monkeypatch.delenv("CRON_SECRET", raising=False)
    r = client.get("/api/maintenance/nightly-sync")
    assert r.status_code == 401


def test_nightly_sync_with_bearer(client, monkeypatch):
    monkeypatch.setenv("CRON_SECRET", "test-cron-secret")
    with patch("routes.maintenance.run_daily_refresh", return_value={"steps": "ok"}):
        with patch("routes.maintenance.invalidate_rankings_cache"):
            r = client.get(
                "/api/maintenance/nightly-sync",
                headers={"Authorization": "Bearer test-cron-secret"},
            )
    assert r.status_code == 200
    data = json.loads(r.data)
    assert data.get("status") == "success"
