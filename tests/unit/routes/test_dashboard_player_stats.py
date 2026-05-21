"""Dashboard player stats: games_played must ignore research-only weekly rows."""
from __future__ import annotations

import json

from models.entities import SleeperWeeklyData
from models.extensions import db
from routes.dashboard_league import _load_player_stats


def test_games_played_zero_for_research_only_row(app_context):
    db.session.add(
        SleeperWeeklyData(
            season="2026",
            week=1,
            league_type="dynasty",
            player_id="p_research_only",
            research_data=json.dumps({"owned": 50.0, "started": 10.0}),
        )
    )
    db.session.commit()

    stats = _load_player_stats("2026", "dynasty", {"p_research_only"})
    row = stats.get("p_research_only")
    assert row is not None
    assert row["games_played"] == 0
    assert row["average_points"] == 0.0
    assert row["total_points"] == 0.0


def test_games_played_counts_matchup_points_row(app_context):
    db.session.add(
        SleeperWeeklyData(
            season="2026",
            week=3,
            league_type="dynasty",
            player_id="p_with_points",
            points=18.5,
            roster_id=1,
            is_starter=True,
        )
    )
    db.session.commit()

    stats = _load_player_stats("2026", "dynasty", {"p_with_points"})
    row = stats["p_with_points"]
    assert row["games_played"] == 1
    assert row["total_points"] == 18.5
    assert row["average_points"] == 18.5


def test_games_played_research_on_same_row_as_points(app_context):
    db.session.add(
        SleeperWeeklyData(
            season="2026",
            week=5,
            league_type="dynasty",
            player_id="p_both",
            points=12.0,
            research_data=json.dumps({"owned": 80.0, "started": 60.0}),
        )
    )
    db.session.commit()

    stats = _load_player_stats("2026", "dynasty", {"p_both"})
    assert stats["p_both"]["games_played"] == 1
