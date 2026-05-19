"""Compute starter scarcity, depth, and age signals for a roster."""
from __future__ import annotations

from typing import Any, Dict, List

_PRIMARY_POSITIONS = ("QB", "RB", "WR", "TE")
_OLD_THRESHOLDS = {"QB": 33, "RB": 30, "WR": 30, "TE": 30}
_YOUNG_THRESHOLD = 24
_SKIP_SLOTS = {"BN", "TAXI", "IR"}


def _starter_slots(roster_positions: List[str]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for slot in roster_positions or []:
        s = (slot or "").upper()
        if s in _SKIP_SLOTS:
            continue
        counts[s] = counts.get(s, 0) + 1
    return counts


def _starter_eligible_count(players: List[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for p in players or []:
        pos = (p.get("position") or "").upper()
        if pos in _PRIMARY_POSITIONS:
            counts[pos] = counts.get(pos, 0) + 1
    return counts


def _scarcity_signals(slots: Dict[str, int], counts: Dict[str, int]) -> List[str]:
    signals = []
    for pos in _PRIMARY_POSITIONS:
        required = slots.get(pos, 0)
        owned = counts.get(pos, 0)
        if required >= 1 and owned <= required:
            signals.append(
                f"{pos}: only {owned} starter-eligible vs {required} starter slot — no real depth"
            )
    return signals


def _age_profile(players: List[Dict[str, Any]]) -> Dict[str, Any]:
    ages = [p.get("age") for p in players if isinstance(p.get("age"), (int, float))]
    if not ages:
        return {
            "avg_starter_age": 0.0,
            "young_starters_count": 0,
            "old_starters_count": 0,
            "contention_window": "rebuild",
        }
    avg = round(sum(ages) / len(ages), 1)
    young = sum(1 for p in players if (p.get("age") or 99) < _YOUNG_THRESHOLD)
    old = 0
    for p in players:
        threshold = _OLD_THRESHOLDS.get((p.get("position") or "").upper())
        if threshold is None:
            continue
        if (p.get("age") or 0) > threshold:
            old += 1
    if avg < 25 and old == 0:
        window = "rebuild"
    elif 25 <= avg <= 28:
        window = "now"
    else:
        window = "transition"
    return {
        "avg_starter_age": avg,
        "young_starters_count": young,
        "old_starters_count": old,
        "contention_window": window,
    }


def compute_team_needs(
    players: List[Dict[str, Any]],
    *,
    roster_positions: List[str],
) -> Dict[str, Any]:
    slots = _starter_slots(roster_positions)
    counts = _starter_eligible_count(players)
    return {
        "starter_slots_required": slots,
        "starter_eligible_count": counts,
        "scarcity_signals": _scarcity_signals(slots, counts),
        "age_profile": _age_profile(players),
    }


def compute_post_trade_snapshot(
    players: List[Dict[str, Any]],
    *,
    roster_positions: List[str],
) -> Dict[str, Any]:
    """Post-trade starter depth and scarcity (same shape as key team-needs fields)."""
    slots = _starter_slots(roster_positions)
    counts = _starter_eligible_count(players)
    return {
        "starter_eligible_count": counts,
        "scarcity_signals": _scarcity_signals(slots, counts),
    }


def compute_trade_impact(
    before: List[Dict[str, Any]],
    after: List[Dict[str, Any]],
    *,
    side_label: str,
) -> List[str]:
    """Human-readable deltas in starter-eligible counts per position."""
    before_counts = _starter_eligible_count(before)
    after_counts = _starter_eligible_count(after)
    signals: List[str] = []
    for pos in _PRIMARY_POSITIONS:
        b = before_counts.get(pos, 0)
        a = after_counts.get(pos, 0)
        if a > b:
            signals.append(f"{side_label} gains {pos} depth ({b} -> {a} starter-eligible)")
        elif a < b:
            signals.append(f"{side_label} loses {pos} depth ({b} -> {a} starter-eligible)")
    if not signals:
        signals.append(f"{side_label}: no change in QB/RB/WR/TE starter-eligible counts")
    return signals
