from __future__ import annotations
from typing import Any, Dict, Iterable


def score_stat_line(scoring_settings: Dict[str, Any], stats: Dict[str, Any]) -> float:
    """Reproduce Sleeper's points: dot-product of scoring settings and the raw stat line."""
    total = 0.0
    for key, coeff in scoring_settings.items():
        if not isinstance(coeff, (int, float)):
            continue
        v = stats.get(key)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            total += coeff * v
    return round(total, 2)


def season_points_for_players(
    scoring_settings: Dict[str, Any],
    rows: Iterable[Any],  # objects with .player_id, .week, .stats (dict)
) -> Dict[str, Dict[str, Any]]:
    """Aggregate per-player season points/avg/games from weekly raw stat rows."""
    agg: Dict[str, Dict[str, float]] = {}
    for r in rows:
        pid = str(r.player_id)
        stats = r.stats or {}
        gp = stats.get("gp")
        played = (gp >= 1) if isinstance(gp, (int, float)) else bool(stats)
        if not played:
            continue
        pts = score_stat_line(scoring_settings, stats)
        a = agg.setdefault(pid, {"total": 0.0, "games": 0})
        a["total"] += pts
        a["games"] += 1
    out: Dict[str, Dict[str, Any]] = {}
    for pid, a in agg.items():
        games = a["games"]
        out[pid] = {
            "average_points": round(a["total"] / games, 2) if games else 0.0,
            "total_points": round(a["total"], 2),
            "games_played": games,
        }
    return out
