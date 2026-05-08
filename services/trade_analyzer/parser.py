"""Defensive JSON parser for LLM responses."""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_REQUIRED_KEYS = ("fairness_score", "winner", "summary_bullets", "side_a", "side_b")
# Models sometimes nest the real payload; unwrap before rejecting.
_WRAPPER_KEYS = (
    "analysis",
    "result",
    "response",
    "data",
    "trade_analysis",
    "output",
    "trade",
    "trade_result",
)
_FENCE = re.compile(r"^```(?:json)?\s*|\s*```\s*$", re.MULTILINE)


class ParseError(Exception):
    def __init__(self, message: str, *, raw: str = "") -> None:
        super().__init__(message)
        self.raw = raw


def _iter_top_level_objects(s: str):
    """Yield each `{...}` span at brace depth zero (skips `{` inside strings)."""
    depth = 0
    seg_start = -1
    i = 0
    in_str = False
    esc = False
    while i < len(s):
        ch = s[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            i += 1
            continue
        if ch == '"':
            in_str = True
            i += 1
            continue
        if ch == "{":
            if depth == 0:
                seg_start = i
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and seg_start >= 0:
                    yield s[seg_start : i + 1]
                    seg_start = -1
        i += 1


def _coerce_score(value: Any) -> int:
    try:
        score = int(value)
    except (TypeError, ValueError):
        return 50
    return max(0, min(100, score))


def _coerce_winner(value: Any, score: int) -> str:
    if isinstance(value, str) and value.lower() in {"side_a", "side_b", "even"}:
        return value.lower()
    inferred = "side_a" if score > 55 else "side_b" if score < 45 else "even"
    logger.warning("trade_analyzer parser: invalid winner=%r, inferred %r", value, inferred)
    return inferred


def _expanded_dict_candidates(
    dict_candidates: list[tuple[int, Dict[str, Any]]],
) -> list[tuple[int, Dict[str, Any]]]:
    """Include inner dicts from common wrapper keys (same parent span length for sorting)."""
    expanded: list[tuple[int, Dict[str, Any]]] = []
    for size, d in dict_candidates:
        expanded.append((size, d))
        for k in _WRAPPER_KEYS:
            inner = d.get(k)
            if isinstance(inner, dict):
                expanded.append((size, inner))
    return expanded


def _side_stub(side_key: str, expected_totals: Optional[Dict[str, Dict[str, int]]]) -> Dict[str, Any]:
    exp = (expected_totals or {}).get(side_key) or {}
    return {
        "pros": [],
        "cons": [],
        "ktc_delta": {
            "values_in": int(exp.get("in") or 0),
            "values_out": int(exp.get("out") or 0),
            "net": int(exp.get("net") or 0),
            "per_asset": [],
        },
        "sleeper_breakdown": {
            "stats_trajectory": [],
            "positional_impact": "",
            "team_needs_addressed": [],
        },
    }


def _recover_trade_details_shape(
    d: Dict[str, Any],
    *,
    expected_totals: Optional[Dict[str, Dict[str, int]]],
) -> Optional[Dict[str, Any]]:
    """Best-effort recovery when the model emits only a trade_details shortcut blob."""
    td = d.get("trade_details")
    if not isinstance(td, dict):
        return None
    ga_raw, gb_raw = td.get("team_a_gain"), td.get("team_b_gain")
    if ga_raw is None or gb_raw is None:
        return None
    try:
        ga_i = int(ga_raw)
        gb_i = int(gb_raw)
    except (TypeError, ValueError):
        return None

    edge = ga_i - gb_i
    fairness_score = _coerce_score(50 + max(-45, min(45, edge // 100)))
    if edge > 0:
        winner = "side_a"
    elif edge < 0:
        winner = "side_b"
    else:
        winner = "even"

    bullets: list[str] = []
    for label, key in (
        ("Side A", "team_a_losing_player"),
        ("Side B", "team_b_losing_player"),
    ):
        v = td.get(key)
        if isinstance(v, str) and v.strip():
            bullets.append(f"{label} loses {v.strip()}.")

    if not bullets:
        bullets.append(
            "Model returned an abbreviated trade_details object; "
            "full narrative fields were synthesized from request totals.",
        )

    out: Dict[str, Any] = {
        "fairness_score": fairness_score,
        "winner": winner,
        "summary_bullets": bullets[:8],
        "side_a": _side_stub("side_a", expected_totals),
        "side_b": _side_stub("side_b", expected_totals),
    }
    cs = d.get("context_summary")
    if isinstance(cs, dict):
        out["context_summary"] = cs
    return out


def _check_drift(parsed: Dict[str, Any], expected_totals: Optional[Dict[str, Dict[str, int]]]) -> None:
    if not expected_totals:
        return
    for side in ("side_a", "side_b"):
        delta = (parsed.get(side) or {}).get("ktc_delta") or {}
        expected = expected_totals.get(side) or {}
        for k_obs, k_exp in (("values_in", "in"), ("values_out", "out"), ("net", "net")):
            obs = delta.get(k_obs)
            exp = expected.get(k_exp)
            if obs is None or exp is None or exp == 0:
                continue
            drift = abs(obs - exp) / max(1, abs(exp))
            if drift > 0.05:
                logger.warning(
                    "trade_analyzer parser: numeric drift on %s.%s observed=%s expected=%s drift=%.2f",
                    side, k_obs, obs, exp, drift,
                )


def parse_llm_response(
    raw: str,
    *,
    expected_totals: Optional[Dict[str, Dict[str, int]]] = None,
) -> Dict[str, Any]:
    if not isinstance(raw, str) or not raw.strip():
        raise ParseError("Empty response", raw=str(raw))
    s = _FENCE.sub("", raw.strip()).lstrip("\ufeff")

    decode_error: Optional[json.JSONDecodeError] = None
    dict_candidates: list[tuple[int, Dict[str, Any]]] = []

    for candidate in _iter_top_level_objects(s):
        try:
            parsed_try = json.loads(candidate)
        except json.JSONDecodeError as exc:
            decode_error = exc
            continue
        if isinstance(parsed_try, dict):
            dict_candidates.append((len(candidate), parsed_try))

    if not dict_candidates:
        if "{" not in s:
            raise ParseError("No JSON object found in response", raw=raw)
        if decode_error is not None:
            raise ParseError(f"JSON decode failed: {decode_error}", raw=raw) from decode_error
        raise ParseError("No JSON objects found in response", raw=raw)

    expanded = _expanded_dict_candidates(dict_candidates)
    best_with_keys = [
        item for item in expanded if all(k in item[1] for k in _REQUIRED_KEYS)
    ]
    if best_with_keys:
        best_with_keys.sort(key=lambda x: x[0], reverse=True)
        parsed: Dict[str, Any] = best_with_keys[0][1]
    else:
        parsed = None
        for _size, cand in sorted(expanded, key=lambda x: -x[0]):
            parsed_try = _recover_trade_details_shape(
                cand, expected_totals=expected_totals,
            )
            if parsed_try:
                parsed = parsed_try
                logger.warning(
                    "trade_analyzer parser: recovered partial LLM shape "
                    "(trade_details); prefer fixing prompts or Ollama schema support",
                )
                break
        if parsed is None:
            widest = max(expanded, key=lambda x: x[0])[1]
            missing = [k for k in _REQUIRED_KEYS if k not in widest]
            raise ParseError(f"Missing required keys: {missing}", raw=raw)

    parsed["fairness_score"] = _coerce_score(parsed.get("fairness_score"))
    parsed["winner"] = _coerce_winner(parsed.get("winner"), parsed["fairness_score"])

    _check_drift(parsed, expected_totals)
    return parsed
