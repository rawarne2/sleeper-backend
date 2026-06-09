"""Build feedback-corpus documents from trade_feedback rows."""
from __future__ import annotations

import json
from typing import Any, Mapping


def _loads(raw: Any) -> dict:
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {}


def _asset_names(assets: list) -> str:
    names = []
    for asset in assets or []:
        if not isinstance(asset, dict):
            continue
        label = asset.get("name") or asset.get("label") or asset.get("position") or "asset"
        names.append(str(label))
    return ", ".join(names) if names else "(none)"


def _window(side: dict) -> str:
    signals = side.get("team_needs_signals") or {}
    age = signals.get("age_profile") or {}
    return str(age.get("contention_window") or "unknown")


def _posture(side: dict) -> str:
    return str(side.get("posture") or "contending")


def feedback_row_to_document(row: Mapping[str, Any]) -> dict[str, Any]:
    """Synthesize a short narrative for embedding (not full context_json)."""
    request = _loads(row.get("request_json"))
    context = _loads(row.get("context_json"))
    response = _loads(row.get("response_json"))
    trade = context.get("trade") or {}
    ktc = (request.get("ktc") or context.get("league", {}).get("ktc") or {})

    side_a = context.get("side_a") or {}
    side_b = context.get("side_b") or {}
    sa_out = _asset_names(trade.get("side_a_outgoing"))
    sa_in = _asset_names(trade.get("side_a_incoming"))
    sb_out = _asset_names(trade.get("side_b_outgoing"))
    sb_in = _asset_names(trade.get("side_b_incoming"))

    winner = response.get("winner") or "unknown"
    grade_a = (response.get("side_a") or {}).get("trade_grade")
    grade_b = (response.get("side_b") or {}).get("trade_grade")
    net_a = ((response.get("side_a") or {}).get("value_delta") or {}).get("net")
    net_b = ((response.get("side_b") or {}).get("value_delta") or {}).get("net")

    agree = row.get("agree_winner") or "unknown"
    user_grade = row.get("user_grade")
    note = (row.get("note") or "").strip()

    lines = [
        f"Trade: side_a gave {sa_out} for {sa_in}; side_b gave {sb_out} for {sb_in}.",
        (
            f"League: {ktc.get('league_format', 'unknown')} format, "
            f"redraft={bool(ktc.get('is_redraft'))}, tep={ktc.get('tep_level') or ''}."
        ),
        (
            f"Windows: side_a {_window(side_a)}/{_posture(side_a)}, "
            f"side_b {_window(side_b)}/{_posture(side_b)}."
        ),
        (
            f"Analyzer: winner={winner}, grades={grade_a}/{grade_b}, "
            f"value_delta nets={net_a}/{net_b}."
        ),
        f"User feedback: {agree}"
        + (f", grade {user_grade}" if user_grade else "")
        + (f", note: {note}" if note else "")
        + ".",
    ]

    return {
        "corpus": "feedback",
        "source_id": str(row.get("id") or ""),
        "content": " ".join(lines),
        "metadata": {
            "league_id": row.get("league_id"),
            "agree_winner": agree,
            "user_grade": user_grade,
            "league_format": ktc.get("league_format"),
            "season": request.get("season"),
            "provider": row.get("provider"),
        },
    }
