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
) -> Dict[str, Dict[str, Any]]:
    """Season aggregates plus ``trajectory`` (last-3-week avg vs season avg)."""
    stats = _load_player_stats(season, research_lt, player_ids)
    if not stats:
        return stats

    max_week = _max_stats_week(season, research_lt)
    if max_week is None:
        for block in stats.values():
            block["trajectory"] = None
        return stats

    last3 = _last_three_week_avgs(season, research_lt, player_ids, max_week=max_week)
    for pid, block in stats.items():
        season_avg = block.get("average_points")
        if pid not in last3 or season_avg is None:
            block["trajectory"] = None
            continue
        delta = round(last3[pid] - float(season_avg), 1)
        block["trajectory"] = f"{delta:+.1f} vs season"
    return stats
