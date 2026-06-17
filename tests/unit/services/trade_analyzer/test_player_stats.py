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
         patch.object(player_stats, "_last_three_week_avgs", return_value={"4881": 14.0}), \
         patch.object(player_stats, "_latest_starter_flags", return_value={"4881": True}):
        out = player_stats.load_stats_with_trajectory(
            "2026", "dynasty", {"4881"}, max_week=10
        )

    max_week_query.assert_not_called()
    assert out["4881"]["trajectory"] == "+2.0 vs season"
    assert out["4881"]["is_starter_latest"] is True


def test_load_stats_falls_back_to_query_when_max_week_none():
    """Backwards compatibility: callers that omit max_week still work."""
    with patch.object(player_stats, "_max_stats_week", return_value=None) as max_week_query, \
         patch.object(player_stats, "_load_player_stats", return_value={"4881": {"average_points": 12.0}}):
        out = player_stats.load_stats_with_trajectory("2026", "dynasty", {"4881"})

    max_week_query.assert_called_once()
    # No max_week -> trajectory is None
    assert out["4881"]["trajectory"] is None


def test_last_three_week_avgs_uses_scoring_engine(app_context):
    """Weekly trajectory averages are computed from raw stat lines via the engine."""
    for wk, rec in ((3, 4.0), (4, 6.0), (5, 8.0)):
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

    # 1.0 PPR -> weekly points 4, 6, 8 -> avg 6.0
    out = player_stats._last_three_week_avgs(
        "2025", {"4881"}, max_week=5, scoring_settings={"rec": 1.0}
    )
    assert out["4881"] == 6.0

    # 0.5 PPR -> weekly points 2, 3, 4 -> avg 3.0 (league scoring drives the value)
    out_half = player_stats._last_three_week_avgs(
        "2025", {"4881"}, max_week=5, scoring_settings={"rec": 0.5}
    )
    assert out_half["4881"] == 3.0
