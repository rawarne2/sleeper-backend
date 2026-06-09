"""Build the LLM-ready analysis context."""
from __future__ import annotations

import os
from typing import Any, Dict, List, Set

from data_types.trade_analyzer_types import TradeRequest
from managers.sleeper_picks import compute_owned_picks
from routes.dashboard_league import _load_ownership_and_meta, _research_league_type_label
from services.trade_analyzer.picks import (
    PickIdError, parse_pick_id, resolve_pick_to_ktc,
)
from services.trade_analyzer.team_needs import (
    _starter_slots,
    compute_post_trade_snapshot,
    compute_team_needs,
    compute_trade_impact,
)
from utils.constants import PLAYER_NAME_KEY

_OWNED_PICK_HORIZON_SEASONS = 2

# Sleeper injury_status values treated as healthy; IR/PUP/Sus/etc. stay as injury signals.
_HEALTHY_SLEEPER_INJURY_STATUSES = frozenset({"", "Active", "Healthy", "healthy"})
# Roster status omitted when player has no injury signal from either source.
_NEUTRAL_ROSTER_STATUSES = frozenset({None, "", "Active"})

_KTC_INJURY_DETAIL_KEYS = (
    "injuryName",
    "injuryArea",
    "injuryReturn",
    "injuryNotes",
    "summary",
)

# KTC value subkeys to surface alongside the trade asset, minus the top-level duplicates
# already on the player block (value -> ktc_value, positionalRank -> positional_rank,
# overallTrend -> trend). overallTrendFormatted is dropped because the LLM can format itself.
_KTC_VALUE_EXTRA_KEYS = (
    "rank",
    "overallTier",
    "positionalTier",
    "positionalTrend",
    "overall7DayTrend",
    "positional7DayTrend",
    "startSitValue",
    "kept",
    "traded",
    "cut",
    "diff",
    "isOutThisWeek",
    "rawLiquidity",
    "stdLiquidity",
    "tradeCount",
)

_KTC_FLAG_KEYS = ("pickRound", "pickNum", "isTrending", "draftYear", "byeWeek")

_NAME_KEYS = (PLAYER_NAME_KEY, "player_name", "full_name", "name")


def _display_name(player: Dict[str, Any]) -> str | None:
    for key in _NAME_KEYS:
        value = player.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def _trade_player_ids_from_request(req: TradeRequest) -> Set[str]:
    ids: Set[str] = set()
    for side_key in ("side_a", "side_b"):
        for pid in (req[side_key].get("player_ids") or []):
            s = str(pid).strip()
            if s:
                ids.add(s)
    return ids


def _roster_player_in_trade(
    player: Dict[str, Any],
    roster_pid: str,
    trade_player_ids: Set[str],
) -> bool:
    if str(roster_pid).strip() in trade_player_ids:
        return True
    sid = player.get("sleeper_player_id")
    return sid is not None and str(sid).strip() in trade_player_ids


def _put_if_populated(out: Dict[str, Any], key: str, value: Any) -> None:
    """Single-pass write: skips None/empty and the games_played/avg_points zero sentinel."""
    if value is None or value == "":
        return
    if value in (0, 0.0) and key in ("games_played", "avg_points"):
        return
    out[key] = value


def _sleeper_injury_status_meaningful(status: Any) -> bool:
    if status is None:
        return False
    return str(status).strip() not in _HEALTHY_SLEEPER_INJURY_STATUSES


def _meaningful_ktc_injury(injury: Any) -> bool:
    """KTC ``Player.injury`` JSON — omit healthy-only ``injuryCode`` 1 blobs."""
    if not isinstance(injury, dict) or not injury:
        return False
    if any(injury.get(k) for k in _KTC_INJURY_DETAIL_KEYS):
        return True
    code = injury.get("injuryCode")
    try:
        return int(code) != 1
    except (TypeError, ValueError):
        return code not in (None, "", 1, "1")


def _ktc_block_slim(
    values: Dict[str, Any] | None,
    ktc_flags: Dict[str, Any],
) -> Dict[str, Any] | None:
    """KTC extras for trade assets — no tep/tepp/teppp nests; the top-level
    ktc_value / positional_rank / trend already mirror values.value /
    positionalRank / overallTrend, so those keys are intentionally omitted here.
    """
    if not values and not ktc_flags:
        return None
    out: Dict[str, Any] = {}
    if isinstance(values, dict):
        for k in _KTC_VALUE_EXTRA_KEYS:
            v = values.get(k)
            if v is not None:
                out[k] = v
    for flag in _KTC_FLAG_KEYS:
        v = ktc_flags.get(flag)
        if v is not None:
            out[flag] = v
    injury = ktc_flags.get("injury")
    if _meaningful_ktc_injury(injury):
        out["injury"] = injury
    return out or None


def _injury_block(player: Dict[str, Any]) -> Dict[str, Any] | None:
    """Sleeper injury columns — only when at least one field is populated."""
    out: Dict[str, Any] = {}
    status = player.get("injury_status")
    if _sleeper_injury_status_meaningful(status):
        out["status"] = status
    for src_key, out_key in (
        ("injury_body_part", "body_part"),
        ("injury_notes", "notes"),
        ("injury_start_date", "start_date"),
    ):
        v = player.get(src_key)
        if v not in (None, ""):
            out[out_key] = v
    return out or None


def _has_injury_signal(player: Dict[str, Any], ktc_flags: Dict[str, Any]) -> bool:
    return _sleeper_injury_status_meaningful(player.get("injury_status")) or _meaningful_ktc_injury(
        ktc_flags.get("injury")
    )


def _headline_injury_status(player: Dict[str, Any], ktc_flags: Dict[str, Any]) -> str | None:
    """Single injury label: Sleeper status first, else KTC injuryName."""
    status = player.get("injury_status")
    if _sleeper_injury_status_meaningful(status):
        return str(status).strip()
    ktc_inj = ktc_flags.get("injury")
    if isinstance(ktc_inj, dict):
        name = ktc_inj.get("injuryName")
        if name:
            return str(name)
    return None


def _trade_roster_status(player: Dict[str, Any], ktc_flags: Dict[str, Any]) -> str | None:
    """Sleeper roster status (e.g. Inactive) — omit Active when there is no injury signal."""
    status = player.get("status")
    if status in _NEUTRAL_ROSTER_STATUSES:
        return None
    if not _has_injury_signal(player, ktc_flags):
        return None
    return status


def _practice_block(player: Dict[str, Any]) -> Dict[str, Any] | None:
    out: Dict[str, Any] = {}
    for src_key, out_key in (
        ("practice_participation", "participation"),
        ("practice_description", "description"),
    ):
        v = player.get(src_key)
        if v not in (None, ""):
            out[out_key] = v
    return out or None


def _ktc_injury_payload(ktc_flags: Dict[str, Any]) -> Dict[str, Any] | None:
    injury = ktc_flags.get("injury")
    if not _meaningful_ktc_injury(injury):
        return None
    return dict(injury) if isinstance(injury, dict) else None


def _values_for_format(ktc: Dict[str, Any], league_format: str) -> Dict[str, Any]:
    if league_format == "superflex":
        return ktc.get("superflexValues") or {}
    return ktc.get("oneQBValues") or {}


def _positional_tier_label(pos_upper: str | None, positional_rank: Any) -> str | None:
    if positional_rank is None:
        return None
    try:
        rank = int(positional_rank)
    except (TypeError, ValueError):
        return None
    return f"{pos_upper or 'UNK'}{rank}"


def _ownership_pct(
    player: Dict[str, Any],
    ownership: Dict[str, Dict[str, Any]] | None,
) -> Dict[str, Any]:
    if not ownership:
        return {}
    sid = player.get("sleeper_player_id")
    if sid is None:
        return {}
    return ownership.get(str(sid)) or {}


def _player_trade(
    player: Dict[str, Any],
    league_format: str,
    ownership: Dict[str, Dict[str, Any]] | None,
) -> Dict[str, Any]:
    ktc = player.get("ktc") or {}
    values = _values_for_format(ktc, league_format)
    stats = player.get("stats") or {}
    position = player.get("position")
    pos_upper = position.upper() if position else None
    pr = values.get("positionalRank")
    own = _ownership_pct(player, ownership)

    out: Dict[str, Any] = {}
    _put_if_populated(out, "name", _display_name(player))
    _put_if_populated(out, "position", pos_upper)
    _put_if_populated(out, "team", player.get("team"))
    _put_if_populated(out, "age", ktc.get("age"))
    _put_if_populated(out, "years_exp", player.get("years_exp"))
    _put_if_populated(out, "ktc_value", values.get("value"))
    _put_if_populated(out, "blended_value", (player.get("values") or {}).get("blended"))
    _put_if_populated(out, "positional_rank", pr)
    _put_if_populated(out, "positional_tier", _positional_tier_label(pos_upper, pr))
    _put_if_populated(out, "trend", values.get("overallTrend"))
    _put_if_populated(out, "trajectory", stats.get("trajectory"))
    _put_if_populated(out, "games_played", stats.get("games_played"))
    _put_if_populated(out, "avg_points", stats.get("average_points"))
    _put_if_populated(out, "market_owned_pct", own.get("owned"))
    _put_if_populated(out, "market_started_pct", own.get("started"))
    _put_if_populated(out, "injury_status", _headline_injury_status(player, ktc))
    _put_if_populated(out, "status", _trade_roster_status(player, ktc))
    _put_if_populated(out, "ktc", _ktc_block_slim(values, ktc))
    _put_if_populated(out, "injury", _injury_block(player))
    _put_if_populated(out, "practice", _practice_block(player))
    _put_if_populated(out, "is_starter_latest", stats.get("is_starter_latest"))
    return out


def _player_roster(
    player: Dict[str, Any],
    league_format: str,
    ownership: Dict[str, Dict[str, Any]] | None,
    *,
    include_name: bool = False,
) -> Dict[str, Any]:
    ktc = player.get("ktc") or {}
    values = _values_for_format(ktc, league_format)
    own = _ownership_pct(player, ownership)

    out: Dict[str, Any] = {}
    _put_if_populated(out, "ktc_value", values.get("value"))
    _put_if_populated(out, "positional_rank", values.get("positionalRank"))
    _put_if_populated(out, "age", ktc.get("age"))
    _put_if_populated(out, "injury_status", _headline_injury_status(player, ktc))
    _put_if_populated(out, "injury", _injury_block(player))
    _put_if_populated(out, "ktc_injury", _ktc_injury_payload(ktc))
    _put_if_populated(out, "market_owned_pct", own.get("owned"))
    _put_if_populated(out, "market_started_pct", own.get("started"))
    if include_name:
        _put_if_populated(out, "name", _display_name(player))
    return out


def _pick_label(parsed: Dict[str, Any]) -> str:
    rnd = parsed["round"]
    ordinal = {1: "1st", 2: "2nd", 3: "3rd"}.get(rnd, f"{rnd}th")
    slot = parsed["slot"]
    if slot.startswith("pick"):
        return f"{parsed['season']} Round {rnd} (pick {slot[4:]})"
    return f"{parsed['season']} {slot.title()} {ordinal}"


def _pick_asset(
    pick_id: str,
    ktc_value: int | None,
    blended_value: float | None = None,
) -> Dict[str, Any]:
    parsed = parse_pick_id(pick_id)
    out: Dict[str, Any] = {"kind": "pick", "label": _pick_label(parsed)}
    if ktc_value is not None:
        out["ktc_value"] = ktc_value
    # blended_value falls back to ktc_value when not explicitly supplied
    effective_blended = blended_value if blended_value is not None else (
        float(ktc_value) if ktc_value is not None else None
    )
    if effective_blended is not None:
        out["blended_value"] = effective_blended
    return out


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
        out: Dict[str, Any] = {"kind": "pick", "label": pick.get("pick_id")}
        if ktc_value is not None:
            out["ktc_value"] = ktc_value
        return out


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

    seen: Set[str] = set()
    out: List[Dict[str, Any]] = []
    for pick in picks:
        pid = pick.get("pick_id")
        if not pid or pid in seen:
            continue
        include = pid in trade_pick_ids
        if not include:
            try:
                parsed = parse_pick_id(pid)
                include = parsed["season"] in allowed_seasons
            except PickIdError:
                include = False
        if include:
            seen.add(pid)
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


def _bench_slot_count(roster_positions: List[str]) -> int:
    return sum(1 for slot in roster_positions or [] if (slot or "").upper() == "BN")


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
    out: Dict[str, Dict[str, Any]] = {}
    for p in players:
        sid = p.get("sleeper_player_id")
        if sid is None:
            continue
        key = str(sid).strip()
        if key:
            out[key] = p
    return out


def _needs_player(player: Dict[str, Any]) -> Dict[str, Any]:
    ktc = player.get("ktc") or {}
    return {
        "name": _display_name(player),
        "position": (player.get("position") or "").upper(),
        "age": ktc.get("age"),
    }


def _trade_includes_players(req: TradeRequest) -> bool:
    return bool(req["side_a"].get("player_ids") or req["side_b"].get("player_ids"))


def _group_by_position(
    pids: List[str],
    idx: Dict[str, Dict[str, Any]],
    league_format: str,
    ownership: Dict[str, Dict[str, Any]],
    trade_player_ids: Set[str],
) -> Dict[str, List[Dict[str, Any]]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for pid in pids:
        p = idx.get(pid)
        if not p:
            continue
        pos = (p.get("position") or "UNK").upper()
        grouped.setdefault(pos, []).append(
            _player_roster(
                p,
                league_format,
                ownership,
                include_name=_roster_player_in_trade(p, pid, trade_player_ids),
            )
        )
    return grouped


def _roster_slot_groups(
    roster: Dict[str, Any],
    idx: Dict[str, Dict[str, Any]],
    league_format: str,
    ownership: Dict[str, Dict[str, Any]],
    trade_player_ids: Set[str],
    *,
    minimal: bool,
) -> Dict[str, Dict[str, List[Dict[str, Any]]]]:
    starter_set = {str(p) for p in (roster.get("starters") or [])}
    reserve_set = {str(p) for p in (roster.get("reserve") or [])}
    taxi_set = {str(p) for p in (roster.get("taxi") or [])}

    starters: List[str] = []
    bench: List[str] = []
    reserve: List[str] = []
    taxi: List[str] = []
    seen: Set[str] = set()
    for pid in (roster.get("players") or []):
        s = str(pid)
        if s in seen:
            continue
        seen.add(s)
        if s in starter_set:
            starters.append(s)
        elif s in reserve_set:
            reserve.append(s)
        elif s in taxi_set:
            taxi.append(s)
        else:
            bench.append(s)

    if minimal:
        return {
            "starters": _group_by_position(
                starters, idx, league_format, ownership, trade_player_ids
            ),
            "bench": {},
            "reserve": {},
            "taxi": {},
        }
    return {
        "starters": _group_by_position(
            starters, idx, league_format, ownership, trade_player_ids
        ),
        "bench": _group_by_position(
            bench, idx, league_format, ownership, trade_player_ids
        ),
        "reserve": _group_by_position(
            reserve, idx, league_format, ownership, trade_player_ids
        ),
        "taxi": _group_by_position(
            taxi, idx, league_format, ownership, trade_player_ids
        ),
    }


def _ownership_player_ids(rosters: List[Dict[str, Any]], req: TradeRequest) -> Set[str]:
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
        s = str(pid)
        if s in outgoing:
            continue
        p = player_index.get(s)
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
    out: List[Dict[str, Any]] = []
    for pid in player_ids:
        p = idx.get(str(pid))
        if not p:
            raise ValueError(f"Unknown player_id: {pid}")
        block = _player_trade(p, league_format, ownership)
        block["kind"] = "player"
        out.append(block)
    return out


def _sum_ktc(items: List[Dict[str, Any]]) -> int:
    return sum(int(x.get("ktc_value") or 0) for x in items)


def _sum_blended(items: List[Dict[str, Any]]) -> float:
    """Sum each asset's blended_value, falling back to ktc_value when blended is None."""
    total = 0.0
    for x in items:
        v = x.get("blended_value")
        if v is None:
            v = x.get("ktc_value") or 0
        total += float(v)
    return round(total, 1)


def _consensus_totals(a_out: List[Dict[str, Any]], b_out: List[Dict[str, Any]]) -> Dict[str, Any]:
    a = _sum_blended(a_out)
    b = _sum_blended(b_out)
    return {
        "side_a": {"out": a, "in": b, "net": round(b - a, 1)},
        "side_b": {"out": b, "in": a, "net": round(a - b, 1)},
    }


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
    roster_minimal = not _trade_includes_players(req)
    trade_player_ids = _trade_player_ids_from_request(req)

    picks_by_roster = compute_owned_picks(req["league_id"])
    research_lt = _research_league_type_label(is_redraft)
    ownership = league_data.get("ownership")
    research_meta = league_data.get("research_meta")
    if ownership is None or research_meta is None:
        ownership, research_meta = _load_ownership_and_meta(
            season, research_lt, _ownership_player_ids(rosters, req)
        )
    research_week = research_meta.get("week") if isinstance(research_meta, dict) else None

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
        roster_slots = _roster_slot_groups(
            roster,
            player_index,
            league_format,
            ownership,
            trade_player_ids,
            minimal=roster_minimal,
        )
        return {
            "manager": user_by_id.get(roster.get("owner_id"), "(unknown)"),
            "record": _trim_record(roster.get("settings")),
            "posture": "tanking" if side.get("is_tanking") else "contending",
            "roster": roster_slots,
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
    a_out += _trade_picks(
        req["side_a"].get("pick_ids") or [], league_format, tep, is_redraft=is_redraft)
    b_out += _trade_picks(
        req["side_b"].get("pick_ids") or [], league_format, tep, is_redraft=is_redraft)

    a_out_sum = _sum_ktc(a_out)
    b_out_sum = _sum_ktc(b_out)
    ktc_only_totals = {
        "side_a": {"out": a_out_sum, "in": b_out_sum, "net": b_out_sum - a_out_sum},
        "side_b": {"out": b_out_sum, "in": a_out_sum, "net": a_out_sum - b_out_sum},
    }
    anchor = os.getenv("TRADE_ANALYZER_ANCHOR", "blended")
    consensus_totals = (
        ktc_only_totals if anchor == "ktc" else _consensus_totals(a_out, b_out)
    )

    league_block: Dict[str, Any] = {
        "season": season,
        "name": league.get("name"),
        "scoring_format_summary": _scoring_summary(league.get("scoring_settings") or {}),
        "ktc": req["ktc"],
        "league_type": research_lt,
        "total_rosters": league_data.get("total_rosters"),
        "starter_slots_required": _starter_slots(roster_positions),
        "bench_slots": _bench_slot_count(roster_positions),
    }
    current_week = league.get("current_week")
    if current_week is not None:
        league_block["current_week"] = current_week
    if research_week is not None:
        league_block["research_week"] = int(research_week)

    return {
        "league": league_block,
        "side_a": side_a,
        "side_b": side_b,
        "trade": {
            "side_a_outgoing": a_out,
            "side_a_incoming": b_out,
            "side_b_outgoing": b_out,
            "side_b_incoming": a_out,
            "consensus_totals": consensus_totals,
            "anchor": anchor,
        },
    }
