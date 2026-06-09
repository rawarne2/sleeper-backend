"""Build a short retrieval query from trade context."""
from __future__ import annotations

from typing import Any


def _asset_summary(assets: list) -> str:
    parts = []
    for asset in assets or []:
        if not isinstance(asset, dict):
            continue
        pos = asset.get("position") or "?"
        name = asset.get("name") or asset.get("label") or pos
        parts.append(f"{name}({pos})")
    return ", ".join(parts[:6]) if parts else "none"


def _window_label(side: dict) -> str:
    signals = side.get("team_needs_signals") or {}
    age = signals.get("age_profile") or {}
    window = age.get("contention_window") or "unknown"
    posture = side.get("posture") or "contending"
    return f"{window}/{posture}"


def build_rag_query(context: dict[str, Any], request: dict[str, Any] | None = None) -> str:
    request = request or {}
    league = context.get("league") or {}
    ktc = league.get("ktc") or request.get("ktc") or {}
    trade = context.get("trade") or {}
    totals = trade.get("consensus_totals") or {}

    fmt = ktc.get("league_format") or "unknown"
    redraft = bool(ktc.get("is_redraft"))
    tep = ktc.get("tep_level") or ""
    season = request.get("season") or league.get("season") or ""

    side_a = context.get("side_a") or {}
    side_b = context.get("side_b") or {}
    net_a = (totals.get("side_a") or {}).get("net")
    net_b = (totals.get("side_b") or {}).get("net")

    return (
        f"Dynasty trade {season} {fmt} redraft={redraft} tep={tep}. "
        f"side_a gives {_asset_summary(trade.get('side_a_outgoing'))} "
        f"for {_asset_summary(trade.get('side_a_incoming'))} "
        f"(window {_window_label(side_a)}, net {net_a}). "
        f"side_b gives {_asset_summary(trade.get('side_b_outgoing'))} "
        f"for {_asset_summary(trade.get('side_b_incoming'))} "
        f"(window {_window_label(side_b)}, net {net_b})."
    )
