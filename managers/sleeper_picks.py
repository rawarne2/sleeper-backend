"""compute_owned_picks: derive owned draft picks per roster."""
from __future__ import annotations

import json
import logging
import os
from typing import Dict, List, Optional

from data_types.trade_analyzer_types import OwnedPick
from models.entities import SleeperLeague, SleeperRoster

logger = logging.getLogger(__name__)


def _horizon_years() -> int:
    return int(os.getenv("TRADE_ANALYZER_PICK_HORIZON_YEARS", "3"))


def _safe_load(blob: Optional[str]) -> object:
    if not blob:
        return None
    try:
        return json.loads(blob)
    except json.JSONDecodeError:
        return None


def _draft_rounds(league: SleeperLeague) -> int:
    settings = _safe_load(league.league_settings) or {}
    if isinstance(settings, dict):
        try:
            return int(settings.get("draft_rounds") or 4)
        except (TypeError, ValueError):
            pass
    return 4


def _current_season(league: SleeperLeague) -> int:
    try:
        return int(league.season)
    except (TypeError, ValueError):
        return 0


def _horizon_lo(league: SleeperLeague) -> int:
    current = _current_season(league)
    if (league.status or "").strip().lower() in {"in_season", "complete"}:
        return current + 1
    return current


def _slot_bucket(rank: int, league_size: int) -> str:
    third = max(1, league_size // 3)
    if rank <= third:
        return "early"
    if rank <= 2 * third:
        return "mid"
    return "late"


def _rank_by_record(rosters: List[SleeperRoster]) -> Dict[int, int]:
    """Return {roster_id: rank} where rank 1 = worst (wins asc, fpts asc)."""
    parsed = []
    for r in rosters:
        settings = _safe_load(r.settings) or {}
        wins = int(settings.get("wins") or 0)
        fpts = float(settings.get("fpts") or 0.0)
        parsed.append((wins, fpts, r.roster_id))
    parsed.sort()
    return {rid: i + 1 for i, (_, _, rid) in enumerate(parsed)}


def _has_real_standings(rosters: List[SleeperRoster]) -> bool:
    for r in rosters:
        s = _safe_load(r.settings) or {}
        if (s.get("wins") or 0) or (s.get("fpts") or 0):
            return True
    return False


def compute_owned_picks(league_id: str) -> Dict[int, List[OwnedPick]]:
    league = SleeperLeague.query.filter_by(league_id=league_id).first()
    if league is None:
        return {}

    rosters = SleeperRoster.query.filter_by(league_id=league_id).all()
    if not rosters:
        return {}

    league_size = len(rosters)
    rounds = _draft_rounds(league)
    current = _current_season(league)
    horizon_hi = current + _horizon_years()
    horizon_lo = _horizon_lo(league)
    seasons = [str(y) for y in range(horizon_lo, horizon_hi + 1)]

    rank_by_id = _rank_by_record(rosters)
    standings_real = _has_real_standings(rosters)

    ownership: Dict[tuple, int] = {
        (rid, season, rd): rid
        for rid in rank_by_id
        for season in seasons
        for rd in range(1, rounds + 1)
    }

    traded = _safe_load(league.traded_picks) or []
    if isinstance(traded, list):
        for row in traded:
            if not isinstance(row, dict):
                continue
            try:
                season = str(row["season"])
                rd = int(row["round"])
                original = int(row["roster_id"])
                current_owner = int(row["owner_id"])
            except (KeyError, TypeError, ValueError):
                continue
            if season not in seasons:
                continue
            ownership[(original, season, rd)] = current_owner

    by_roster: Dict[int, List[OwnedPick]] = {rid: [] for rid in rank_by_id}
    for (original, season, rd), owner in ownership.items():
        rank = rank_by_id.get(original, league_size // 2 + 1)
        if str(current) != season or not standings_real:
            slot = "mid"
        else:
            slot = _slot_bucket(rank, league_size)
        pick_id = f"{season}-r{rd}-{slot}"
        by_roster.setdefault(owner, []).append({
            "season": season, "round": rd, "original_roster_id": original,
            "slot_bucket": slot, "pick_id": pick_id, "ktc_value": None,
        })

    for picks in by_roster.values():
        picks.sort(key=lambda p: (p["season"], p["round"], p["original_roster_id"]))
    return by_roster
