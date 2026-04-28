"""Tests for GET /api/dashboard/league/:id."""
import json
from types import SimpleNamespace
from unittest.mock import patch

from routes.dashboard_league import (
    _ktc_values_block_for_dashboard,
    _player_to_dashboard_dict,
)


def test_dashboard_defaults_season_from_league(client):
    """Omitting season uses the league row's season from the database snapshot."""

    def fake_season(_league_id):
        return (True, "2025")

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
        "routes.dashboard_league.DatabaseManager.get_league_season_only",
        side_effect=fake_season,
    ), patch(
        "routes.dashboard_league.DatabaseManager.get_league_data",
        side_effect=fake_league,
    ), patch(
        "routes.dashboard_league._ktc_players_for_roster",
        return_value=([], None),
    ), patch(
        "routes.dashboard_league._load_ownership_and_meta",
        return_value=(
            {},
            {
                "season": "2025",
                "week": None,
                "league_type": 2,
                "last_updated": None,
            },
        ),
    ), patch(
        "routes.dashboard_league._load_player_stats",
        return_value={},
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

    def fake_season(_league_id):
        return (True, None)

    def fake_league(_league_id):
        return {
            "status": "success",
            "league": {"league_id": "1", "season": None},
            "rosters": [],
            "users": [],
        }

    with patch(
        "routes.dashboard_league.DatabaseManager.get_league_season_only",
        side_effect=fake_season,
    ), patch(
        "routes.dashboard_league.DatabaseManager.get_league_data",
        side_effect=fake_league,
    ), patch(
        "routes.dashboard_league._ktc_players_for_roster",
        return_value=([], None),
    ), patch(
        "routes.dashboard_league._load_ownership_and_meta",
        return_value=(
            {},
            {
                "season": "2099",
                "week": None,
                "league_type": 2,
                "last_updated": None,
            },
        ),
    ) as load_mock, patch(
        "routes.dashboard_league._load_player_stats",
        return_value={},
    ):
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
    with patch(
        "routes.maintenance.run_daily_refresh", return_value={"steps": "ok"}
    ), patch(
        "routes.maintenance.invalidate_rankings_cache"
    ), patch(
        "routes.maintenance._prewarm_dashboard_caches",
        return_value={"results": [], "failed": 0, "total": 0},
    ) as prewarm_mock:
        r = client.get(
            "/api/maintenance/nightly-sync",
            headers={"Authorization": "Bearer test-cron-secret"},
        )
    assert r.status_code == 200
    data = json.loads(r.data)
    assert data.get("status") == "success"
    prewarm_mock.assert_called_once()
    assert "prewarm" in (data.get("summary") or {})


def test_nightly_sync_can_skip_prewarm(client, monkeypatch):
    monkeypatch.setenv("CRON_SECRET", "test-cron-secret")
    with patch(
        "routes.maintenance.run_daily_refresh", return_value={"steps": "ok"}
    ), patch(
        "routes.maintenance.invalidate_rankings_cache"
    ), patch(
        "routes.maintenance._prewarm_dashboard_caches"
    ) as prewarm_mock:
        r = client.post(
            "/api/maintenance/nightly-sync",
            headers={"Authorization": "Bearer test-cron-secret"},
            json={"skip_prewarm": True},
        )
    assert r.status_code == 200
    prewarm_mock.assert_not_called()


def _fake_ktc_values():
    """SimpleNamespace mimicking PlayerKTCSuperflexValues attribute access."""
    return SimpleNamespace(
        value=8000, rank=10, positional_rank=2,
        overall_tier=1, positional_tier=1,
        tep_value=8200, tep_rank=8, tep_positional_rank=1,
        tep_overall_tier=1, tep_positional_tier=1,
        tepp_value=8300, tepp_rank=7, tepp_positional_rank=1,
        tepp_overall_tier=1, tepp_positional_tier=1,
        teppp_value=8400, teppp_rank=6, teppp_positional_rank=1,
        teppp_overall_tier=1, teppp_positional_tier=1,
    )


def _fake_player(*, oneqb=None, superflex=None):
    return SimpleNamespace(
        id=42, player_name="Justin Jefferson", position="WR", team="MIN",
        sleeper_player_id="6794", full_name="Justin Jefferson",
        last_updated=None, injury_status=None, status="Active",
        birth_date=None, height="6'1\"", weight="195", college="LSU",
        years_exp=5, number=18, age=25.5,
        oneqb_values=oneqb, superflex_values=superflex,
    )


def test_player_to_dashboard_dict_returns_none_when_no_format_values():
    p = _fake_player(superflex=None, oneqb=None)
    assert _player_to_dashboard_dict(p, "superflex", "tep") is None
    assert _player_to_dashboard_dict(p, "1qb", "") is None


def test_player_to_dashboard_dict_superflex_with_tep_override():
    p = _fake_player(superflex=_fake_ktc_values())
    out = _player_to_dashboard_dict(p, "superflex", "tep")
    assert out is not None
    assert out["sleeper_player_id"] == "6794"
    assert out["ktc"]["age"] == 25.5
    assert out["ktc"]["oneQBValues"] is None
    sf = out["ktc"]["superflexValues"]
    assert sf["value"] == 8200
    assert sf["rank"] == 8
    assert sf["positionalRank"] == 1
    assert sf["tep"]["value"] == 8200


def test_player_to_dashboard_dict_oneqb_no_tep():
    p = _fake_player(oneqb=_fake_ktc_values())
    out = _player_to_dashboard_dict(p, "1qb", "")
    assert out is not None
    assert out["ktc"]["superflexValues"] is None
    oq = out["ktc"]["oneQBValues"]
    assert oq["value"] == 8000
    assert oq["rank"] == 10


def test_ktc_values_block_tepp_override_skips_when_value_missing():
    values = _fake_ktc_values()
    values.tepp_value = None
    block = _ktc_values_block_for_dashboard(values, "tepp")
    assert block["value"] == 8000  # base, unchanged
    assert block["rank"] == 10
