"""Build the LLM-ready analysis context."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from data_types.trade_analyzer_types import TradeRequest
from managers.sleeper_picks import compute_owned_picks
from services.trade_analyzer.picks import (
    PickIdError, parse_pick_id, resolve_pick_to_ktc,
)
from services.trade_analyzer.team_needs import compute_team_needs


def _picks_for_side(picks_by_roster, roster_id, league_format, tep_level):
    out = []
    for pick in picks_by_roster.get(roster_id, []):
        ktc_value = None
        try:
            resolved = resolve_pick_to_ktc(
                pick["pick_id"], league_format=league_format, tep_level=tep_level)
            if resolved is not None:
                _, ktc_value = resolved
        except PickIdError:
            pass
        out.append({"pick_id": pick["pick_id"], "ktc_value": ktc_value})
    return out


def _trade_picks(pick_ids, league_format, tep_level):
    out = []
    for pid in pick_ids:
        try:
            resolved = resolve_pick_to_ktc(pid, league_format=league_format, tep_level=tep_level)
        except PickIdError as exc:
            raise ValueError(str(exc))
        ktc_value = resolved[1] if resolved else None
        out.append({"pick_id": pid, "kind": "pick", "ktc_value": ktc_value})
    return out

_PLAYER_KEYS = (
    "name", "age", "years_exp", "ktc_value",
    "positional_rank", "games_played", "avg_points",
    "trajectory", "trend",
)


def _ktc_block(player: Dict[str, Any], league_format: str) -> Optional[Dict[str, Any]]:
    ktc = player.get("ktc") or {}
    if league_format == "superflex":
        return ktc.get("superflexValues") or None
    return ktc.get("oneQBValues") or None


def _player_min(player: Dict[str, Any], league_format: str) -> Dict[str, Any]:
    ktc = player.get("ktc") or {}
    values = _ktc_block(player, league_format) or {}
    stats = player.get("stats") or {}
    out = {
        "name": player.get("playerName") or player.get("full_name"),
        "age": ktc.get("age"),
        "years_exp": player.get("years_exp"),
        "ktc_value": values.get("value"),
        "positional_rank": values.get("positionalRank"),
        "games_played": stats.get("games_played"),
        "avg_points": stats.get("average_points"),
        "trajectory": stats.get("trajectory"),
        "trend": values.get("overallTrend"),
    }
    return {k: out[k] for k in _PLAYER_KEYS}


def _scoring_summary(scoring: Dict[str, Any]) -> str:
    if not isinstance(scoring, dict):
        return "(unknown)"
    pieces = []
    rec = scoring.get("rec")
    if isinstance(rec, (int, float)):
        if rec >= 1.0:
            pieces.append("Full PPR")
        elif rec > 0:
            pieces.append(f"{rec} PPR")
        else:
            pieces.append("Standard")
    bonus_te = scoring.get("bonus_rec_te")
    if isinstance(bonus_te, (int, float)) and bonus_te > 0:
        pieces.append(f"+{bonus_te} TE premium")
    return " + ".join(pieces) if pieces else "(unknown)"


def _index_users(users: List[Dict[str, Any]]) -> Dict[str, str]:
    return {u["user_id"]: u.get("display_name") or u.get("username") or u["user_id"]
            for u in users if u.get("user_id")}


def _find_roster(rosters: List[Dict[str, Any]], roster_id: int) -> Dict[str, Any]:
    for r in rosters:
        if r.get("roster_id") == roster_id:
            return r
    raise ValueError(f"Unknown roster_id: {roster_id}")


def _index_players(players: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {p["sleeper_player_id"]: p for p in players if p.get("sleeper_player_id")}


def _roster_by_position(roster_player_ids: List[str], idx: Dict[str, Dict[str, Any]],
                        league_format: str) -> Dict[str, List[Dict[str, Any]]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for pid in roster_player_ids:
        p = idx.get(str(pid))
        if not p:
            continue
        pos = (p.get("position") or "UNK").upper()
        grouped.setdefault(pos, []).append(_player_min(p, league_format))
    return grouped


def _trade_assets(player_ids: List[str], idx: Dict[str, Dict[str, Any]],
                  league_format: str) -> List[Dict[str, Any]]:
    out = []
    for pid in player_ids:
        p = idx.get(str(pid))
        if not p:
            raise ValueError(f"Unknown player_id: {pid}")
        values = _ktc_block(p, league_format) or {}
        out.append({
            "name": p.get("playerName") or p.get("full_name"),
            "kind": "player",
            "ktc_value": values.get("value"),
        })
    return out


def build_context(req: TradeRequest, *, league_data: Dict[str, Any]) -> Dict[str, Any]:
    league = league_data["league"]
    rosters = league_data.get("rosters") or []
    users = league_data.get("users") or []
    players = league_data.get("players") or []

    user_by_id = _index_users(users)
    player_index = _index_players(players)
    league_format = req["ktc"]["league_format"]
    picks_by_roster = compute_owned_picks(req["league_id"])
    tep = req["ktc"].get("tep_level") or ""

    def _build_side(side_key: str) -> Dict[str, Any]:
        side = req[side_key]
        roster = _find_roster(rosters, side["roster_id"])
        roster_players_full = []
        for pid in roster.get("players") or []:
            p = player_index.get(str(pid))
            if not p:
                continue
            ktc_block = p.get("ktc") or {}
            roster_players_full.append({
                "name": p.get("playerName") or p.get("full_name"),
                "position": (p.get("position") or "").upper(),
                "age": ktc_block.get("age"),
            })
        return {
            "manager": user_by_id.get(roster.get("owner_id"), "(unknown)"),
            "roster_id": side["roster_id"],
            "record": (roster.get("settings") or {}),
            "roster_by_position": _roster_by_position(
                roster.get("players") or [], player_index, league_format
            ),
            "owned_picks": _picks_for_side(picks_by_roster, side["roster_id"], league_format, tep),
            "team_needs_signals": compute_team_needs(
                roster_players_full,
                roster_positions=league.get("roster_positions") or [],
            ),
        }

    side_a = _build_side("side_a")
    side_b = _build_side("side_b")

    a_out = _trade_assets(req["side_a"]["player_ids"], player_index, league_format)
    b_out = _trade_assets(req["side_b"]["player_ids"], player_index, league_format)
    a_out_picks = _trade_picks(req["side_a"].get("pick_ids") or [], league_format, tep)
    b_out_picks = _trade_picks(req["side_b"].get("pick_ids") or [], league_format, tep)

    a_out = a_out + a_out_picks
    b_out = b_out + b_out_picks
    a_in = b_out
    b_in = a_out

    def _sum(items): return sum(int(x.get("ktc_value") or 0) for x in items)

    return {
        "league": {
            "league_id": league.get("league_id"),
            "season": req["season"],
            "name": league.get("name"),
            "roster_positions": league.get("roster_positions") or [],
            "scoring_format_summary": _scoring_summary(league.get("scoring_settings") or {}),
            "ktc": req["ktc"],
            "current_week": league.get("current_week"),
        },
        "side_a": side_a,
        "side_b": side_b,
        "trade": {
            "side_a_outgoing": a_out,
            "side_a_incoming": a_in,
            "side_b_outgoing": b_out,
            "side_b_incoming": b_in,
            "ktc_totals": {
                "side_a": {"out": _sum(a_out), "in": _sum(a_in), "net": _sum(a_in) - _sum(a_out)},
                "side_b": {"out": _sum(b_out), "in": _sum(b_in), "net": _sum(b_in) - _sum(b_out)},
            },
        },
        "additional_context": req.get("additional_context"),
    }
