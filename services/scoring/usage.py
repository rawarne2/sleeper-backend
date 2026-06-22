"""Opportunity / usage metrics derived from raw Sleeper weekly stat lines.

These keys (``off_snp``, ``tm_off_snp``, ``rec_tgt``, ``rec_rz_tgt``, ``rush_rz_att``,
``rec_air_yd``, ``gs``) are present in ``NflPlayerWeekStats.stats`` but are **not**
fantasy-scoring keys, so ``services.scoring.engine`` ignores them. Opportunity is the
stickiest predictor of fantasy production — snap share leads, with target/carry volume,
red-zone usage, and air yards as supporting role/projection signals. The trade analyzer
surfaces these so the model can tell a secure role from a flukey box score.

True target share and routes-run/TPRR need team-level aggregation / charting data that
the per-player Sleeper line does not carry; those are deferred to the nflverse ingest.
"""
from __future__ import annotations

from typing import Any, Dict, Sequence, Tuple


def _f(stats: Dict[str, Any], key: str) -> float:
    v = stats.get(key)
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _snap_pct(stats: Dict[str, Any]) -> float | None:
    team = _f(stats, "tm_off_snp")
    if team <= 0:
        return None
    return round(_f(stats, "off_snp") / team * 100, 1)


def season_usage(week_stats: Sequence[Tuple[int, Dict[str, Any]]]) -> Dict[str, Any] | None:
    """Aggregate usage across a player's weekly stat lines for one season.

    ``week_stats``: ``(week, stats_dict)`` pairs sorted ascending by week, already
    filtered to the regular-season window. Weeks with ``gp < 1`` are dropped so a
    player's bye / inactive weeks do not deflate per-game rates or snap share.
    Returns ``None`` when the player has no games played in the window.
    """
    played = [(w, s) for (w, s) in week_stats if s and _f(s, "gp") >= 1]
    if not played:
        return None
    games = len(played)

    snaps = [sp for (_, s) in played if (sp := _snap_pct(s)) is not None]
    snap_pct = round(sum(snaps) / len(snaps), 1) if snaps else None
    last3 = snaps[-3:]
    snap_pct_l3 = round(sum(last3) / len(last3), 1) if last3 else None

    targets = sum(_f(s, "rec_tgt") for (_, s) in played)
    carries = sum(_f(s, "rush_att") for (_, s) in played)
    air_yards = sum(_f(s, "rec_air_yd") for (_, s) in played)
    rz_opps = sum(_f(s, "rec_rz_tgt") + _f(s, "rush_rz_att") for (_, s) in played)
    games_started = sum(1 for (_, s) in played if _f(s, "gs") >= 1)

    out: Dict[str, Any] = {"games_started": int(games_started)}
    if snap_pct is not None:
        out["snap_pct"] = snap_pct
    if snap_pct_l3 is not None and snap_pct is not None:
        out["snap_pct_l3"] = snap_pct_l3
        out["snap_trend"] = f"{snap_pct_l3 - snap_pct:+.1f} vs season"
    if targets:
        out["targets_per_game"] = round(targets / games, 1)
    if carries:
        out["carries_per_game"] = round(carries / games, 1)
    if air_yards:
        out["air_yards_per_game"] = round(air_yards / games, 1)
    if rz_opps:
        out["rz_opps"] = int(rz_opps)
    return out
