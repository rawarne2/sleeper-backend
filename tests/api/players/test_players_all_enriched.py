# tests/api/players/test_players_all_enriched.py
"""Tests for season stats + ownership enrichment on GET /api/players/all."""
from datetime import datetime, UTC

from models.entities import Player, PlayerKTCSuperflexValues, SleeperWeeklyData
from models.extensions import db


def _seed_player(name, position, sleeper_id, match_key):
    p = Player(
        player_name=name,
        position=position,
        team="TST",
        sleeper_player_id=sleeper_id,
        match_key=match_key,
        last_updated=datetime.now(UTC),
    )
    db.session.add(p)
    db.session.flush()
    return p


def _seed_superflex_values(player_id, value, rank, is_redraft=False):
    db.session.add(PlayerKTCSuperflexValues(
        player_id=player_id, is_redraft=is_redraft, value=value, rank=rank,
    ))


def _seed_weekly(sleeper_id, season, week, league_type="dynasty", points=None, research_data=None):
    db.session.add(SleeperWeeklyData(
        season=season,
        week=week,
        league_type=league_type,
        player_id=sleeper_id,
        points=points,
        research_data=research_data,
        last_updated=datetime.now(UTC),
    ))


class TestPlayersAllEnriched:
    """Season stats + ownership are attached only when a season is supplied."""

    def test_includes_stats_and_ownership_when_season_given(self, client):
        p = _seed_player("Justin Jefferson", "WR", "6794", "justinjefferson-WR")
        _seed_superflex_values(p.id, 8500, 2)
        _seed_weekly("6794", "2025", 1, points=10)
        _seed_weekly("6794", "2025", 2, points=20)
        _seed_weekly("6794", "2025", 3, research_data='{"owned": 95.5, "started": 80.0}')
        db.session.commit()

        resp = client.get("/api/players/all?league_format=superflex&season=2025")
        assert resp.status_code == 200
        body = resp.get_json()

        assert "researchMeta" in body
        assert body["researchMeta"]["season"] == "2025"
        assert body["researchMeta"]["week"] == 3

        player = next((pl for pl in body["players"] if pl.get("sleeper_player_id") == "6794"), None)
        assert player is not None
        assert player["stats"]["games_played"] == 2
        assert player["stats"]["total_points"] == 30.0
        assert player["stats"]["average_points"] == 15.0
        assert player["research_latest"]["owned"] == 95.5
        assert player["research_latest"]["started"] == 80.0
        assert player["research_latest"]["week"] == 3

    def test_without_season_is_unchanged(self, client):
        p = _seed_player("CeeDee Lamb", "WR", "6845", "ceedee-WR")
        _seed_superflex_values(p.id, 8200, 3)
        _seed_weekly("6845", "2025", 1, points=12)
        db.session.commit()

        resp = client.get("/api/players/all?league_format=superflex")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["status"] == "success"
        assert "players" in body
        assert "researchMeta" not in body
        player = next((pl for pl in body["players"] if pl.get("sleeper_player_id") == "6845"), None)
        assert player is not None
        assert "stats" not in player
        assert "research_latest" not in player
