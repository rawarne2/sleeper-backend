"""Season stats, trajectory, and usage for trade-analyzer player payloads."""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Set, Tuple

from sqlalchemy import func

from models.entities import NflPlayerWeekStats, SleeperWeeklyData
from models.extensions import db
from routes.dashboard_league import _load_player_stats
from services.scoring.engine import score_stat_line
from utils.constants import (
    SLEEPER_STATS_AGGREGATE_WEEK_MAX,
    SLEEPER_STATS_AGGREGATE_WEEK_MIN,
)


def _max_stats_week(season: str, research_lt: str) -> int | None:
    row = (
        db.session.query(func.max(SleeperWeeklyData.week))
        .filter(
            SleeperWeeklyData.season == season,
            SleeperWeeklyData.league_type == research_lt,
            SleeperWeeklyData.week.between(
                SLEEPER_STATS_AGGREGATE_WEEK_MIN,
                SLEEPER_STATS_AGGREGATE_WEEK_MAX,
            ),
        )
        .scalar()
    )
    return int(row) if row is not None else None


def _load_week_rows(
    season: str,
    player_ids: Set[str],
    *,
    max_week: int,
) -> Dict[str, List[Tuple[int, Dict[str, Any]]]]:
    """Per-player ``(week, raw_stats)`` lists across the regular-season window.

    One query feeds both the trajectory (last-3-week scoring pace) and the usage
    block, so neither re-scans ``nfl_player_week_stats``.
    """
    id_list = [x for x in player_ids if x]
    if not id_list or max_week < SLEEPER_STATS_AGGREGATE_WEEK_MIN:
        return {}
    rows = (
        db.session.query(NflPlayerWeekStats)
        .filter(
            NflPlayerWeekStats.season == season,
            NflPlayerWeekStats.week.between(SLEEPER_STATS_AGGREGATE_WEEK_MIN, max_week),
            NflPlayerWeekStats.player_id.in_(id_list),
        )
        .order_by(NflPlayerWeekStats.player_id, NflPlayerWeekStats.week)
        .all()
    )
    by_player: Dict[str, List[Tuple[int, Dict[str, Any]]]] = defaultdict(list)
    for row in rows:
        by_player[str(row.player_id)].append((int(row.week), row.stats or {}))
    return by_player


def _trajectory(
    weeks: List[Tuple[int, Dict[str, Any]]],
    season_avg: Any,
    scoring_settings: Dict[str, Any],
    *,
    max_week: int,
) -> str | None:
    """Last-3-week scoring average vs season average (e.g. ``"+2.4 vs season"``)."""
    if season_avg is None or not weeks:
        return None
    week_lo = max(SLEEPER_STATS_AGGREGATE_WEEK_MIN, max_week - 2)
    recent = [
        score_stat_line(scoring_settings or {}, s)
        for (w, s) in weeks
        if week_lo <= w <= max_week
    ]
    if len(recent) < 3:
        return None
    avg3 = sum(recent[-3:]) / 3
    return f"{round(avg3 - float(season_avg), 1):+.1f} vs season"


def load_stats_with_trajectory(
    season: str,
    research_lt: str,
    player_ids: Set[str],
    *,
    max_week: int | None = None,
    scoring_settings: Dict[str, Any] | None = None,
) -> Dict[str, Dict[str, Any]]:
    """Season aggregates + ``trajectory`` (last-3-week pace) + ``usage`` (opportunity).

    Season points and the trajectory's weekly averages are computed by the scoring
    engine against the league's ``scoring_settings`` (league-agnostic raw stat lines),
    so the trade analyzer's numbers match the dashboard for the same league. The
    ``usage`` block (snap share, volume, red-zone usage) is attached upstream by
    ``_load_player_stats`` from the same raw rows — see ``services.scoring.usage``.

    ``max_week`` may be supplied by the caller to skip the SELECT max(week) query
    when that value is already known (e.g. when ownership was loaded from the same
    SleeperWeeklyData table).
    """
    scoring_settings = scoring_settings or {}
    stats = _load_player_stats(season, scoring_settings, player_ids)
    if not stats:
        return stats

    if max_week is None:
        max_week = _max_stats_week(season, research_lt)
    if max_week is None:
        for block in stats.values():
            block["trajectory"] = None
        return stats

    rows_by_player = _load_week_rows(season, player_ids, max_week=max_week)
    for pid, block in stats.items():
        block["trajectory"] = _trajectory(
            rows_by_player.get(pid, []),
            block.get("average_points"),
            scoring_settings,
            max_week=max_week,
        )
    return stats
