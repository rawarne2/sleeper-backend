"""Resolve canonical pick_id strings to KTC RDP rows + values."""
from __future__ import annotations

import re
from typing import Optional, Tuple

from models.entities import Player
from utils.constants import SLEEPER_POSITION_RDP


_PATTERN = re.compile(r"^(?P<season>\d{4})-r(?P<round>\d+)-(?P<slot>early|mid|late|pick\d+)$")


class PickIdError(ValueError):
    """Unparseable pick_id."""


def parse_pick_id(pick_id: str) -> dict:
    if not isinstance(pick_id, str):
        raise PickIdError(f"pick_id must be a string, got {type(pick_id).__name__}")
    m = _PATTERN.match(pick_id.strip())
    if not m:
        raise PickIdError(f"Unparseable pick_id: {pick_id!r}")
    return {"season": m["season"], "round": int(m["round"]), "slot": m["slot"]}


def _round_ordinal(n: int) -> str:
    return {1: "1st", 2: "2nd", 3: "3rd"}.get(n, f"{n}th")


def _candidate_names(parsed: dict) -> list[str]:
    season = parsed["season"]
    rnd = parsed["round"]
    slot = parsed["slot"]
    out = []
    if slot.startswith("pick"):
        try:
            n = int(slot[4:])
            out.append(f"{season} {rnd}.{n:02d}")
        except ValueError:
            pass
    elif slot in ("early", "mid", "late"):
        out.append(f"{season} {slot.title()} {_round_ordinal(rnd)}")
    return out


def _ktc_value(player: Player, league_format: str, tep_level: Optional[str]) -> Optional[int]:
    rel = player.superflex_values if league_format == "superflex" else player.oneqb_values
    if rel is None:
        return None
    tep_field = {
        "tep": rel.tep_value,
        "tepp": rel.tepp_value,
        "teppp": rel.teppp_value,
    }.get(tep_level or "")
    if tep_field is not None:
        return int(tep_field)
    return int(rel.value) if rel.value is not None else None


def resolve_pick_to_ktc(
    pick_id: str, *, league_format: str, tep_level: Optional[str],
) -> Optional[Tuple[Player, Optional[int]]]:
    """Return (Player row, ktc_value) or None when no KTC RDP row matches."""
    parsed = parse_pick_id(pick_id)
    for name in _candidate_names(parsed):
        row = (
            Player.query
            .filter(Player.position == SLEEPER_POSITION_RDP)
            .filter(Player.player_name == name)
            .first()
        )
        if row is not None:
            return row, _ktc_value(row, league_format, tep_level)
    return None
