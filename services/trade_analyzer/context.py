"""Build the LLM-ready analysis context."""
from __future__ import annotations

from typing import Any, Dict, List, Set

from data_types.trade_analyzer_types import TradeRequest
from managers.sleeper_picks import compute_owned_picks
from routes.dashboard_league import _load_ownership_and_meta, _research_league_type_label
from services.trade_analyzer.picks import (
    PickIdError, parse_pick_id, resolve_pick_to_ktc,
)
from services.trade_analyzer.team_needs import (
    compute_post_trade_snapshot,
    compute_team_needs,
    compute_trade_impact,
)

_PLAYER_KEYS = (
    "name",
    "position",
    "team",
    "age",
    "years_exp",
    "ktc_value",
    "positional_rank",
    "positional_tier",
    "games_played",
    "avg_points",
    "trajectory",
    "trend",
    "market_owned_pct",
    "market_started_pct",
    "injury_status",
    "status",
)

_OWNED_PICK_HORIZON_SEASONS = 2


def _explicit_nulls(keys: tuple[str, ...], values: Dict[str, Any]) -> Dict[str, Any]:
    return {k: values.get(k) for k in keys}


def _ktc_block(player: Dict[str, Any], league_format: str) -> Dict[str, Any] | None:
    ktc = player.get("ktc") or {}
    if league_format == "superflex":
        return ktc.get("superflexValues") or None
    return ktc.get("oneQBValues") or None


def _positional_tier_label(position: str | None, positional_rank: Any) -> str | None:
    if positional_rank is None:
        return None
    pos = (position or "UNK").upper()
    try:
        rank = int(positional_rank)
    except (TypeError, ValueError):
        return None
    return f"{pos}{rank}"


def _player_min(
    player: Dict[str, Any],
    league_format: str,
    ownership: Dict[str, Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    ktc = player.get("ktc") or {}
    values = _ktc_block(player, league_format) or {}
    stats = player.get("stats") or {}
    position = player.get("position")
    pos_upper = position.upper() if position else None
    pr = values.get("positionalRank")
    pid = str(player.get("sleeper_player_id") or "")
    own = (ownership or {}).get(pid) or {}
    values_out = {
        "name": player.get("playerName") or player.get("full_name"),
        "position": pos_upper,
        "team": player.get("team"),
        "age": ktc.get("age"),
        "years_exp": player.get("years_exp"),
        "ktc_value": values.get("value"),
        "positional_rank": pr,
        "positional_tier": _positional_tier_label(pos_upper, pr),
        "games_played": stats.get("games_played"),
        "avg_points": stats.get("average_points"),
        "trajectory": stats.get("trajectory"),
        "trend": values.get("overallTrend"),
        "market_owned_pct": own.get("owned"),
        "market_started_pct": own.get("started"),
        "injury_status": player.get("injury_status"),
        "status": player.get("status"),
    }
    return _explicit_nulls(_PLAYER_KEYS, values_out)


def _pick_label(parsed: Dict[str, Any]) -> str:
    rnd = parsed["round"]
    ordinal = {1: "1st", 2: "2nd", 3: "3rd"}.get(rnd, f"{rnd}th")
    slot = parsed["slot"]
    if slot.startswith("pick"):
        return f"{parsed['season']} Round {rnd} (pick {slot[4:]})"
    return f"{parsed['season']} {slot.title()} {ordinal}"


def _pick_asset(pick_id: str, ktc_value: int | None) -> Dict[str, Any]:
    parsed = parse_pick_id(pick_id)
    return {
        "pick_id": pick_id,
        "kind": "pick",
        "season": parsed["season"],
        "round": parsed["round"],
        "slot": parsed["slot"],
        "label": _pick_label(parsed),
        "ktc_value": ktc_value,
    }


def _pick_owned_entry(
    pick: Dict[str, Any],
    league_format: str,
    tep_level: str,
    *,
    is_redraft: bool = False,
) -> Dict[str, Any]:
    ktc_value = pick.get("ktc_value")
    if ktc_value is None:
        try:
            resolved = resolve_pick_to_ktc(
                pick["pick_id"],
                league_format=league_format,
                tep_level=tep_level,
                is_redraft=is_redraft,
            )
            if resolved is not None:
                _, ktc_value = resolved
        except PickIdError:
            pass
    try:
        return _pick_asset(pick["pick_id"], ktc_value)
    except PickIdError:
        return {
            "pick_id": pick["pick_id"],
            "kind": "pick",
            "season": pick.get("season"),
            "round": pick.get("round"),
            "slot": pick.get("slot_bucket"),
            "label": pick.get("pick_id"),
            "ktc_value": ktc_value,
        }


def _filter_owned_picks(
    picks: List[Dict[str, Any]],
    trade_pick_ids: Set[str],
    base_season: str,
    *,
    league_format: str,
    tep_level: str,
    is_redraft: bool = False,
) -> List[Dict[str, Any]]:
    try:
        base_year = int(base_season)
    except (TypeError, ValueError):
        base_year = 0
    allowed_seasons = {str(base_year + i) for i in range(_OWNED_PICK_HORIZON_SEASONS)}

    out: List[Dict[str, Any]] = []
    for pick in picks:
        pid = pick.get("pick_id")
        if not pid:
            continue
        include = pid in trade_pick_ids
        if not include:
            try:
                parsed = parse_pick_id(pid)
                include = parsed["season"] in allowed_seasons
            except PickIdError:
                include = False
        if include:
            out.append(
                _pick_owned_entry(
                    pick, league_format, tep_level, is_redraft=is_redraft)
            )
    return out


def _trade_picks(
    pick_ids: List[str],
    league_format: str,
    tep_level: str,
    *,
    is_redraft: bool = False,
) -> List[Dict[str, Any]]:
    out = []
    for pid in pick_ids:
        try:
            resolved = resolve_pick_to_ktc(
                pid,
                league_format=league_format,
                tep_level=tep_level,
                is_redraft=is_redraft,
            )
        except PickIdError as exc:
            raise ValueError(str(exc)) from exc
        ktc_value = resolved[1] if resolved else None
        out.append(_pick_asset(pid, ktc_value))
    return out


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


def _trim_record(settings: Any) -> Dict[str, Any]:
    if not isinstance(settings, dict):
        return {"wins": None, "losses": None, "ties": None, "fpts": None}
    return {
        "wins": settings.get("wins"),
        "losses": settings.get("losses"),
        "ties": settings.get("ties"),
        "fpts": settings.get("fpts"),
    }


def _index_users(users: List[Dict[str, Any]]) -> Dict[str, str]:
    return {
        u["user_id"]: u.get("display_name") or u.get("username") or u["user_id"]
        for u in users
        if u.get("user_id")
    }


def _find_roster(rosters: List[Dict[str, Any]], roster_id: int) -> Dict[str, Any]:
    for r in rosters:
        if r.get("roster_id") == roster_id:
            return r
    raise ValueError(f"Unknown roster_id: {roster_id}")


def _index_players(players: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {p["sleeper_player_id"]: p for p in players if p.get("sleeper_player_id")}


def _needs_player(player: Dict[str, Any]) -> Dict[str, Any]:
    ktc = player.get("ktc") or {}
    return {
        "name": player.get("playerName") or player.get("full_name"),
        "position": (player.get("position") or "").upper(),
        "age": ktc.get("age"),
    }


def _roster_by_position(
    roster_player_ids: List[str],
    idx: Dict[str, Dict[str, Any]],
    league_format: str,
    ownership: Dict[str, Dict[str, Any]],
) -> Dict[str, List[Dict[str, Any]]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for pid in roster_player_ids:
        p = idx.get(str(pid))
        if not p:
            continue
        pos = (p.get("position") or "UNK").upper()
        grouped.setdefault(pos, []).append(_player_min(p, league_format, ownership))
    return grouped


def _ownership_player_ids(rosters: List[Dict[str, Any]], req: TradeRequest) -> Set[str]:
    """All roster + traded player ids for research ownership lookup."""
    ids: Set[str] = set()
    for side_key in ("side_a", "side_b"):
        side = req[side_key]
        for pid in side.get("player_ids") or []:
            ids.add(str(pid))
        try:
            roster = _find_roster(rosters, side["roster_id"])
        except ValueError:
            continue
        for pid in roster.get("players") or []:
            ids.add(str(pid))
    return ids


def _players_after_trade(
    roster: Dict[str, Any],
    player_index: Dict[str, Dict[str, Any]],
    outgoing_ids: List[str],
    incoming_ids: List[str],
) -> List[Dict[str, Any]]:
    outgoing = {str(x) for x in outgoing_ids}
    out: List[Dict[str, Any]] = []
    for pid in roster.get("players") or []:
        if str(pid) in outgoing:
            continue
        p = player_index.get(str(pid))
        if p:
            out.append(_needs_player(p))
    for pid in incoming_ids:
        p = player_index.get(str(pid))
        if p:
            out.append(_needs_player(p))
    return out


def _trade_assets(
    player_ids: List[str],
    idx: Dict[str, Dict[str, Any]],
    league_format: str,
    ownership: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    out = []
    for pid in player_ids:
        p = idx.get(str(pid))
        if not p:
            raise ValueError(f"Unknown player_id: {pid}")
        block = _player_min(p, league_format, ownership)
        block["kind"] = "player"
        out.append(block)
    return out


def _asset_summary_label(asset: Dict[str, Any]) -> str:
    if asset.get("kind") == "pick":
        return str(asset.get("label") or asset.get("pick_id"))
    return str(asset.get("name"))


def _sum_ktc(items: List[Dict[str, Any]]) -> int:
    return sum(int(x.get("ktc_value") or 0) for x in items)


def build_context(req: TradeRequest, *, league_data: Dict[str, Any]) -> Dict[str, Any]:
    league = league_data["league"]
    rosters = league_data.get("rosters") or []
    users = league_data.get("users") or []
    players = league_data.get("players") or []

    user_by_id = _index_users(users)
    player_index = _index_players(players)
    league_format = req["ktc"]["league_format"]
    tep = req["ktc"].get("tep_level") or ""
    is_redraft = bool(req["ktc"].get("is_redraft"))
    season = req["season"]
    roster_positions = league.get("roster_positions") or []

    picks_by_roster = compute_owned_picks(req["league_id"])
    research_lt = _research_league_type_label(is_redraft)
    ownership, _ = _load_ownership_and_meta(
        season, research_lt, _ownership_player_ids(rosters, req)
    )

    def _build_side(side_key: str, *, outgoing_ids: List[str], incoming_ids: List[str]) -> Dict[str, Any]:
        side = req[side_key]
        roster = _find_roster(rosters, side["roster_id"])
        before_needs = []
        for pid in roster.get("players") or []:
            p = player_index.get(str(pid))
            if p:
                before_needs.append(_needs_player(p))
        after_needs = _players_after_trade(
            roster, player_index, outgoing_ids, incoming_ids
        )
        owned = _filter_owned_picks(
            picks_by_roster.get(side["roster_id"], []),
            set(side.get("pick_ids") or []),
            season,
            league_format=league_format,
            tep_level=tep,
            is_redraft=is_redraft,
        )
        return {
            "manager": user_by_id.get(roster.get("owner_id"), "(unknown)"),
            "record": _trim_record(roster.get("settings")),
            "roster_by_position": _roster_by_position(
                roster.get("players") or [],
                player_index,
                league_format,
                ownership,
            ),
            "owned_picks": owned,
            "team_needs_signals": compute_team_needs(
                before_needs, roster_positions=roster_positions
            ),
            "after_trade_snapshot": compute_post_trade_snapshot(
                after_needs, roster_positions=roster_positions
            ),
            "trade_impact": compute_trade_impact(
                before_needs, after_needs, side_label=side_key
            ),
        }

    a_out_ids = req["side_a"]["player_ids"]
    b_out_ids = req["side_b"]["player_ids"]
    side_a = _build_side("side_a", outgoing_ids=a_out_ids, incoming_ids=b_out_ids)
    side_b = _build_side("side_b", outgoing_ids=b_out_ids, incoming_ids=a_out_ids)

    a_out = _trade_assets(a_out_ids, player_index, league_format, ownership)
    b_out = _trade_assets(b_out_ids, player_index, league_format, ownership)
    a_out_picks = _trade_picks(
        req["side_a"].get("pick_ids") or [], league_format, tep, is_redraft=is_redraft)
    b_out_picks = _trade_picks(
        req["side_b"].get("pick_ids") or [], league_format, tep, is_redraft=is_redraft)

    a_out = a_out + a_out_picks
    b_out = b_out + b_out_picks
    a_in = b_out
    b_in = a_out

    ktc_totals = {
        "side_a": {
            "out": _sum_ktc(a_out),
            "in": _sum_ktc(a_in),
            "net": _sum_ktc(a_in) - _sum_ktc(a_out),
        },
        "side_b": {
            "out": _sum_ktc(b_out),
            "in": _sum_ktc(b_in),
            "net": _sum_ktc(b_in) - _sum_ktc(b_out),
        },
    }

    return {
        "league": {
            "season": season,
            "name": league.get("name"),
            "roster_positions": roster_positions,
            "scoring_format_summary": _scoring_summary(league.get("scoring_settings") or {}),
            "ktc": req["ktc"],
            "current_week": league.get("current_week"),
            "league_type": research_lt,
            "is_dynasty": not is_redraft,
            "total_rosters": league_data.get("total_rosters"),
        },
        "trade_summary": {
            "side_a_gives": [_asset_summary_label(a) for a in a_out],
            "side_b_gives": [_asset_summary_label(a) for a in b_out],
            "ktc_net": {
                "side_a": ktc_totals["side_a"]["net"],
                "side_b": ktc_totals["side_b"]["net"],
            },
        },
        "side_a": side_a,
        "side_b": side_b,
        "trade": {
            "side_a_outgoing": a_out,
            "side_a_incoming": a_in,
            "side_b_outgoing": b_out,
            "side_b_incoming": b_in,
            "ktc_totals": ktc_totals,
        },
    }
