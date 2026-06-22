"""Dashboard player stats are computed by the scoring engine over raw stat lines.

``_load_player_stats`` loads ``NflPlayerWeekStats`` rows and dot-products the
league's ``scoring_settings`` against each line. ``games_played`` counts weeks the
player actually played (``gp >= 1``, or any non-empty stat line when ``gp`` is absent).
"""
from __future__ import annotations

from datetime import datetime, UTC

from models.entities import NflPlayerWeekStats
from models.extensions import db
from routes.dashboard_league import _attach_stats, _load_player_stats

SCORING = {"rec": 0.5, "rec_yd": 0.1, "rec_td": 6.0}


def _add_week(player_id: str, week: int, stats: dict) -> None:
    db.session.add(
        NflPlayerWeekStats(
            season="2026",
            week=week,
            player_id=player_id,
            stats=stats,
            last_updated=datetime.now(UTC),
        )
    )


def test_did_not_play_week_is_skipped(app_context):
    """A row marked gp=0 does not count as a game played."""
    _add_week("p_dnp", 1, {"gp": 0.0})
    db.session.commit()

    stats = _load_player_stats("2026", SCORING, {"p_dnp"})
    assert "p_dnp" not in stats


def test_points_computed_from_scoring_settings(app_context):
    """Engine reproduces league points from the raw stat line."""
    _add_week("p_played", 3, {"rec": 7.0, "rec_yd": 59.0, "gp": 1.0})
    db.session.commit()

    stats = _load_player_stats("2026", SCORING, {"p_played"})
    row = stats["p_played"]
    assert row["games_played"] == 1
    # 7*0.5 + 59*0.1 = 3.5 + 5.9 = 9.4
    assert row["total_points"] == 9.4
    assert row["average_points"] == 9.4


def test_aggregates_across_weeks(app_context):
    """Total and average accumulate over multiple played weeks."""
    _add_week("p_multi", 1, {"rec": 4.0, "gp": 1.0})  # 2.0
    _add_week("p_multi", 2, {"rec": 6.0, "gp": 1.0})  # 3.0
    db.session.commit()

    stats = _load_player_stats("2026", SCORING, {"p_multi"})
    row = stats["p_multi"]
    assert row["games_played"] == 2
    assert row["total_points"] == 5.0
    assert row["average_points"] == 2.5


def test_week_18_is_excluded_from_aggregate(app_context):
    """Weeks outside SLEEPER_STATS_AGGREGATE window (e.g. 18) are not loaded."""
    _add_week("p_w18", 18, {"rec": 10.0, "gp": 1.0})
    db.session.commit()

    stats = _load_player_stats("2026", SCORING, {"p_w18"})
    assert "p_w18" not in stats


def test_usage_block_attached_from_snap_and_target_data(app_context):
    """_load_player_stats surfaces a usage block from raw snap/target fields."""
    _add_week("p_usage", 1, {"rec": 5.0, "gp": 1.0, "off_snp": 45, "tm_off_snp": 60, "rec_tgt": 8})
    _add_week("p_usage", 2, {"rec": 6.0, "gp": 1.0, "off_snp": 54, "tm_off_snp": 60, "rec_tgt": 10})
    db.session.commit()

    stats = _load_player_stats("2026", SCORING, {"p_usage"})
    usage = stats["p_usage"]["usage"]
    assert usage["snap_pct"] == 82.5  # mean of 75.0 and 90.0
    assert usage["targets_per_game"] == 9.0


def test_attach_stats_promotes_usage_to_top_level(app_context):
    """_attach_stats moves usage out of the stats block onto the player dict."""
    _add_week("p_top", 1, {"rec": 5.0, "gp": 1.0, "off_snp": 30, "tm_off_snp": 60})
    db.session.commit()

    stats_by_pid = _load_player_stats("2026", SCORING, {"p_top"})
    players = [{"sleeper_player_id": "p_top"}]
    _attach_stats(players, stats_by_pid)

    p = players[0]
    assert p["usage"]["snap_pct"] == 50.0
    assert "usage" not in p["stats"]  # stripped from the season-stats block
    assert "average_points" in p["stats"]
