"""Season stats and trajectory for trade-analyzer player payloads."""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, Set

from sqlalchemy import func

from models.entities import SleeperWeeklyData
from models.extensions import db
from routes.dashboard_league import _load_player_stats
from utils.constants import (
    SLEEPER_STATS_AGGREGATE_WEEK_MAX,
    SLEEPER_STATS_AGGREGATE_WEEK_MIN,
)


def _latest_starter_flags(
    season: str,
    research_lt: str,
    player_ids: Set[str],
    *,
    max_week: int,
) -> Dict[str, bool]:
    """Most recent ``is_starter`` per player within the regular-season window."""
    if not player_ids or max_week < SLEEPER_STATS_AGGREGATE_WEEK_MIN:
        return {}
    id_list = [x for x in player_ids if x]
    if not id_list:
        return {}
    rows = (
        db.session.query(
            SleeperWeeklyData.player_id,
            SleeperWeeklyData.week,
            SleeperWeeklyData.is_starter,
        )
        .filter(
            SleeperWeeklyData.season == season,
            SleeperWeeklyData.league_type == research_lt,
            SleeperWeeklyData.week.between(
                SLEEPER_STATS_AGGREGATE_WEEK_MIN,
                max_week,
            ),
            SleeperWeeklyData.player_id.in_(id_list),
            SleeperWeeklyData.points.isnot(None),
        )
        .order_by(SleeperWeeklyData.player_id, SleeperWeeklyData.week.desc())
        .all()
    )
    out: Dict[str, bool] = {}
    for row in rows:
        pid = str(row.player_id)
        if pid in out:
            continue
        out[pid] = bool(row.is_starter)
    return out


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


def _last_three_week_avgs(
    season: str,
    research_lt: str,
    player_ids: Set[str],
    *,
    max_week: int,
) -> Dict[str, float]:
    if max_week < SLEEPER_STATS_AGGREGATE_WEEK_MIN or not player_ids:
        return {}

    week_lo = max(SLEEPER_STATS_AGGREGATE_WEEK_MIN, max_week - 2)
    id_list = [x for x in player_ids if x]
    rows = (
        db.session.query(
            SleeperWeeklyData.player_id,
            SleeperWeeklyData.week,
            SleeperWeeklyData.points,
        )
        .filter(
            SleeperWeeklyData.season == season,
            SleeperWeeklyData.league_type == research_lt,
            SleeperWeeklyData.week.between(week_lo, max_week),
            SleeperWeeklyData.player_id.in_(id_list),
        )
        .order_by(SleeperWeeklyData.player_id, SleeperWeeklyData.week)
        .all()
    )

    by_player: Dict[str, list[float]] = defaultdict(list)
    for row in rows:
        by_player[str(row.player_id)].append(float(row.points or 0))

    out: Dict[str, float] = {}
    for pid, points in by_player.items():
        if len(points) < 3:
            continue
        recent = points[-3:]
        out[pid] = round(sum(recent) / 3, 2)
    return out


def load_stats_with_trajectory(
    season: str,
    research_lt: str,
    player_ids: Set[str],
    *,
    max_week: int | None = None,
) -> Dict[str, Dict[str, Any]]:
    """Season aggregates + ``trajectory`` (last-3-week avg vs season) + ``is_starter_latest``.

    ``max_week`` may be supplied by the caller to skip the SELECT max(week) query
    when that value is already known (e.g. when ownership was loaded from the same
    SleeperWeeklyData table).
    """
    stats = _load_player_stats(season, research_lt, player_ids)
    if not stats:
        return stats

    if max_week is None:
        max_week = _max_stats_week(season, research_lt)
    if max_week is None:
        for block in stats.values():
            block["trajectory"] = None
            block.setdefault("is_starter_latest", None)
        return stats

    last3 = _last_three_week_avgs(season, research_lt, player_ids, max_week=max_week)
    starter_flags = _latest_starter_flags(
        season, research_lt, player_ids, max_week=max_week
    )
    for pid, block in stats.items():
        season_avg = block.get("average_points")
        if pid not in last3 or season_avg is None:
            block["trajectory"] = None
        else:
            delta = round(last3[pid] - float(season_avg), 1)
            block["trajectory"] = f"{delta:+.1f} vs season"
        block["is_starter_latest"] = starter_flags.get(pid)
    return stats
