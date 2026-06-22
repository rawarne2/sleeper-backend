"""load_stats_with_trajectory accepts caller-provided max_week."""
from __future__ import annotations

from datetime import datetime, UTC
from unittest.mock import patch

from models.entities import NflPlayerWeekStats
from models.extensions import db
from services.trade_analyzer import player_stats


def test_load_stats_skips_max_week_query_when_provided():
    """When max_week is supplied, do not run a SELECT max(week) query."""
    with patch.object(player_stats, "_max_stats_week") as max_week_query, \
         patch.object(player_stats, "_load_player_stats", return_value={"4881": {"average_points": 12.0}}), \
         patch.object(player_stats, "_load_week_rows", return_value={"4881": [(10, {"rec": 14.0, "gp": 1.0})]}), \
         patch.object(player_stats, "_trajectory", return_value="+2.0 vs season"):
        out = player_stats.load_stats_with_trajectory(
            "2026", "dynasty", {"4881"}, max_week=10
        )

    max_week_query.assert_not_called()
    assert out["4881"]["trajectory"] == "+2.0 vs season"


def test_load_stats_falls_back_to_query_when_max_week_none():
    """Backwards compatibility: callers that omit max_week still work."""
    with patch.object(player_stats, "_max_stats_week", return_value=None) as max_week_query, \
         patch.object(player_stats, "_load_player_stats", return_value={"4881": {"average_points": 12.0}}):
        out = player_stats.load_stats_with_trajectory("2026", "dynasty", {"4881"})

    max_week_query.assert_called_once()
    # No max_week -> trajectory is None
    assert out["4881"]["trajectory"] is None


def test_load_week_rows_returns_ordered_weeks(app_context):
    """One query returns each player's (week, raw_stats) lines in week order."""
    for wk, rec in ((5, 8.0), (3, 4.0), (4, 6.0)):
        db.session.add(
            NflPlayerWeekStats(
                season="2025",
                week=wk,
                player_id="4881",
                stats={"rec": rec, "gp": 1.0},
                last_updated=datetime.now(UTC),
            )
        )
    db.session.commit()

    rows = player_stats._load_week_rows("2025", {"4881"}, max_week=5)
    assert [w for (w, _) in rows["4881"]] == [3, 4, 5]


def test_trajectory_uses_scoring_engine():
    """Trajectory (last-3-week pace vs season) is league-scoring driven."""
    weeks = [(3, {"rec": 4.0, "gp": 1.0}), (4, {"rec": 6.0, "gp": 1.0}), (5, {"rec": 8.0, "gp": 1.0})]
    # 1.0 PPR -> weekly 4, 6, 8 -> avg 6.0 vs season 4.0 -> +2.0
    assert player_stats._trajectory(weeks, 4.0, {"rec": 1.0}, max_week=5) == "+2.0 vs season"
    # 0.5 PPR -> weekly 2, 3, 4 -> avg 3.0 vs season 4.0 -> -1.0
    assert player_stats._trajectory(weeks, 4.0, {"rec": 0.5}, max_week=5) == "-1.0 vs season"
    # fewer than 3 weeks -> no signal
    assert player_stats._trajectory(weeks[:2], 4.0, {"rec": 1.0}, max_week=5) is None
