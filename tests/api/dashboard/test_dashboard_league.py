"""Tests for GET /api/dashboard/league/:id."""
import json
from unittest.mock import patch


def test_dashboard_defaults_season_from_league(client):
    """Omitting season uses the league row's season from the database snapshot."""

    def fake_league(_league_id):
        return {
            "status": "success",
            "league": {
                "league_id": "1210364682523656192",
                "name": "Test",
                "season": "2025",
                "status": "in_season",
            },
            "rosters": [
                {
                    "roster_id": 1,
                    "owner_id": "u1",
                    "players": ["p1"],
                    "starters": ["p1"],
                    "reserve": [],
                    "taxi": [],
                    "settings": {},
                }
            ],
            "users": [{"user_id": "u1", "display_name": "A"}],
        }

    with patch(
        "routes.dashboard_league.DatabaseManager.get_league_data",
        side_effect=fake_league,
    ):
        with patch(
            "routes.dashboard_league._ktc_players_for_roster",
            return_value=([], None),
        ):
            with patch(
                "routes.dashboard_league._load_ownership_and_meta",
                return_value=({}, {"season": "2025", "week": None, "league_type": 2, "last_updated": None}),
            ):
                r = client.get(
                    "/api/dashboard/league/1210364682523656192"
                    "?league_format=superflex&is_redraft=false&tep_level=tep"
                )
    assert r.status_code == 200
    data = json.loads(r.data)
    assert data.get("status") == "success"
    assert data.get("data", {}).get("league", {}).get("season") == "2025"


def test_dashboard_invalid_explicit_season(client):
    r = client.get(
        "/api/dashboard/league/123?season=25&league_format=superflex&is_redraft=false"
    )
    assert r.status_code == 400


def test_dashboard_league_missing_from_db(client):
    r = client.get(
        "/api/dashboard/league/9999999999999999999"
        "?season=2025&league_format=superflex&is_redraft=false&tep_level=tep"
    )
    assert r.status_code == 404


def test_dashboard_falls_back_season_when_league_row_missing_season(client):
    """No query param + null season in DB uses current calendar year (warning logged)."""

    def fake_league(_league_id):
        return {
            "status": "success",
            "league": {"league_id": "1", "season": None},
            "rosters": [],
            "users": [],
        }

    with patch(
        "routes.dashboard_league.DatabaseManager.get_league_data",
        side_effect=fake_league,
    ):
        with patch(
            "routes.dashboard_league._ktc_players_for_roster",
            return_value=([], None),
        ):
            with patch(
                "routes.dashboard_league._load_ownership_and_meta",
                return_value=({}, {"season": "2099", "week": None, "league_type": 2, "last_updated": None}),
            ) as load_mock:
                r = client.get(
                    "/api/dashboard/league/1?league_format=superflex&is_redraft=false"
                )
    assert r.status_code == 200
    load_mock.assert_called_once()
    call_season = load_mock.call_args[0][0]
    assert len(call_season) == 4 and call_season.isdigit()


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
