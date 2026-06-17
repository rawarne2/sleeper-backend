# tests/api/players/test_players_all_enriched.py
"""Tests for season stats + ownership enrichment on GET /api/players/all.

Season points come from the scoring engine over league-agnostic
``NflPlayerWeekStats`` rows; ownership still comes from ``SleeperWeeklyData.research_data``.
"""
import json
from datetime import datetime, UTC

from models.entities import (
    NflPlayerWeekStats,
    Player,
    PlayerKTCSuperflexValues,
    SleeperLeague,
    SleeperWeeklyData,
)
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


def _seed_week_stats(sleeper_id, season, week, stats):
    db.session.add(NflPlayerWeekStats(
        season=season,
        week=week,
        player_id=sleeper_id,
        stats=stats,
        last_updated=datetime.now(UTC),
    ))


def _seed_research(sleeper_id, season, week, research_data, league_type="dynasty"):
    db.session.add(SleeperWeeklyData(
        season=season,
        week=week,
        league_type=league_type,
        player_id=sleeper_id,
        research_data=research_data,
        last_updated=datetime.now(UTC),
    ))


def _seed_league(league_id, scoring, roster_positions):
    db.session.add(SleeperLeague(
        league_id=league_id,
        name="Test League",
        season="2025",
        status="in_season",
        scoring_settings=json.dumps(scoring),
        roster_positions=json.dumps(roster_positions),
        last_updated=datetime.now(UTC),
    ))


class TestPlayersAllEnriched:
    """Season stats + ownership are attached only when a season is supplied."""

    def test_includes_stats_and_ownership_when_season_given(self, client):
        p = _seed_player("Justin Jefferson", "WR", "6794", "justinjefferson-WR")
        _seed_superflex_values(p.id, 8500, 2)
        # Half-PPR baseline (no league_id): rec 0.5, rec_yd 0.1.
        _seed_week_stats("6794", "2025", 1, {"rec": 6.0, "rec_yd": 40.0, "gp": 1.0})  # 7.0
        _seed_week_stats("6794", "2025", 2, {"rec": 8.0, "rec_yd": 90.0, "gp": 1.0})  # 13.0
        _seed_research("6794", "2025", 3, '{"owned": 95.5, "started": 80.0}')
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
        assert player["stats"]["total_points"] == 20.0
        assert player["stats"]["average_points"] == 10.0
        assert player["research_latest"]["owned"] == 95.5
        assert player["research_latest"]["started"] == 80.0
        assert player["research_latest"]["week"] == 3

    def test_points_reflect_league_and_tep(self, client):
        """Universe points use the league's scoring; the TEP override raises only TE points."""
        league_id = "1210364682523656192"
        # League: 0.5 PPR, no base TE premium.
        _seed_league(league_id, {"rec": 0.5, "rec_yd": 0.1, "rec_td": 6.0}, ["QB", "WR", "TE", "SUPER_FLEX"])

        te = _seed_player("Kyle Pitts", "TE", "7553", "kylepitts-TE")
        _seed_superflex_values(te.id, 5000, 40)
        # Rostered TE plays one week.
        _seed_week_stats("7553", "2025", 1, {"rec": 7.0, "rec_yd": 59.0, "bonus_rec_te": 7.0, "gp": 1.0})

        fa = _seed_player("Free Agent WR", "WR", "9999", "freeagentwr-WR")
        _seed_superflex_values(fa.id, 3000, 80)  # not rostered, but still in the universe
        _seed_week_stats("9999", "2025", 1, {"rec": 5.0, "rec_yd": 50.0, "gp": 1.0})
        db.session.commit()

        base = client.get(
            f"/api/players/all?league_format=superflex&season=2025&league_id={league_id}"
        ).get_json()
        te_row = next(p for p in base["players"] if p["sleeper_player_id"] == "7553")
        fa_row = next(p for p in base["players"] if p["sleeper_player_id"] == "9999")
        # Universe coverage: both rostered TE and free-agent WR get points.
        assert te_row["stats"]["total_points"] > 0
        assert fa_row["stats"]["total_points"] > 0
        # No base TE premium → 7*0.5 + 59*0.1 = 9.4
        assert te_row["stats"]["total_points"] == 9.4

        bumped = client.get(
            f"/api/players/all?league_format=superflex&season=2025&league_id={league_id}&tep_level=teppp"
        ).get_json()
        te2 = next(p for p in bumped["players"] if p["sleeper_player_id"] == "7553")
        fa2 = next(p for p in bumped["players"] if p["sleeper_player_id"] == "9999")
        # teppp bonus_rec_te=1.5 → +7*1.5 = +10.5 for the TE; the WR is unaffected.
        assert te2["stats"]["total_points"] > te_row["stats"]["total_points"]
        assert fa2["stats"]["total_points"] == fa_row["stats"]["total_points"]

    def test_without_season_is_unchanged(self, client):
        p = _seed_player("CeeDee Lamb", "WR", "6845", "ceedee-WR")
        _seed_superflex_values(p.id, 8200, 3)
        _seed_week_stats("6845", "2025", 1, {"rec": 5.0, "gp": 1.0})
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
