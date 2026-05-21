"""Defensive JSON parser for LLM responses."""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_REQUIRED_KEYS = ("winner", "summary_bullets", "side_a", "side_b")
_API_TOP_LEVEL_KEYS = frozenset({*_REQUIRED_KEYS, "context_summary"})
_VALID_GRADES = frozenset(
    {
        "A+",
        "A",
        "A-",
        "B+",
        "B",
        "B-",
        "C+",
        "C",
        "C-",
        "D+",
        "D",
        "D-",
        "F+",
        "F",
        "F-",
    }
)
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
                    yield s[seg_start: i + 1]
                    seg_start = -1
        i += 1


def _infer_winner_from_totals(
    expected_totals: Optional[Dict[str, Dict[str, int]]],
) -> Optional[str]:
    if not expected_totals:
        return None
    net_a = int((expected_totals.get("side_a") or {}).get("net") or 0)
    net_b = int((expected_totals.get("side_b") or {}).get("net") or 0)
    if net_a > net_b:
        return "side_a"
    if net_b > net_a:
        return "side_b"
    if net_a == net_b:
        return "even"
    return None


def _coerce_winner(
    value: Any,
    *,
    expected_totals: Optional[Dict[str, Dict[str, int]]] = None,
) -> str:
    if isinstance(value, str) and value.lower() in {"side_a", "side_b", "even"}:
        return value.lower()
    inferred = _infer_winner_from_totals(expected_totals) or "even"
    logger.warning(
        "trade_analyzer parser: invalid winner=%r, inferred %r", value, inferred)
    return inferred


def _coerce_grade(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    normalized = value.strip().upper().replace(" ", "")
    if normalized in _VALID_GRADES:
        return normalized
    # Accept lowercase from model (e.g. "b+")
    candidate = value.strip()
    if candidate in _VALID_GRADES:
        return candidate
    return None


def _fallback_grades(winner: str) -> tuple[str, str]:
    """Deterministic grades when the model omits or invalidates trade_grade."""
    if winner == "even":
        return ("C", "C")
    if winner == "side_a":
        return ("B+", "D+")
    if winner == "side_b":
        return ("D+", "B+")
    return ("C", "C")


def _coerce_str_list(value: Any) -> list[str]:
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        if item is None:
            continue
        s = str(item).strip()
        if s:
            out.append(s)
    return out


def _side_looks_like_bare_ktc_delta(side: Dict[str, Any]) -> bool:
    if side.get("ktc_delta") is not None:
        return False
    if any(k in side for k in ("trade_grade", "pros", "cons", "sleeper_breakdown", "sleeper_data")):
        return False
    return any(k in side for k in ("values_in", "values_out", "net", "per_asset"))


def _normalize_side_fields(side: Dict[str, Any]) -> None:
    """Canonical side: trade_grade, pros, cons, ktc_delta, sleeper_breakdown."""
    grades = side.pop("grades", None)
    if isinstance(grades, dict):
        for key, val in grades.items():
            if key not in side or side.get(key) in (None, [], ""):
                side[key] = val

    if _side_looks_like_bare_ktc_delta(side):
        per = side.pop("per_asset", [])
        side["ktc_delta"] = {
            "values_in": int(side.pop("values_in", 0) or 0),
            "values_out": int(side.pop("values_out", 0) or 0),
            "net": int(side.pop("net", 0) or 0),
            "per_asset": per if isinstance(per, list) else [],
        }

    for alt in ("grade", "tradeGrade"):
        if side.get("trade_grade") in (None, "") and alt in side:
            side["trade_grade"] = side.pop(alt)

    delta_raw = side.get("ktc_delta")
    delta = dict(delta_raw) if isinstance(delta_raw, dict) else {}

    for key in ("pros", "cons"):
        if not _coerce_str_list(side.get(key)) and key in delta:
            side[key] = delta[key]
    for alt in ("grade", "trade_grade"):
        if side.get("trade_grade") in (None, "") and alt in delta:
            side["trade_grade"] = delta[alt]

    per_asset = delta.get("per_asset")
    side["ktc_delta"] = {
        "values_in": int(delta.get("values_in") or 0),
        "values_out": int(delta.get("values_out") or 0),
        "net": int(delta.get("net") or 0),
        "per_asset": per_asset if isinstance(per_asset, list) else [],
    }

    if "sleeper_data" in side and "sleeper_breakdown" not in side:
        side["sleeper_breakdown"] = side.pop("sleeper_data")

    side["pros"] = _coerce_str_list(side.get("pros"))
    side["cons"] = _coerce_str_list(side.get("cons"))


def _normalize_side_grades(parsed: Dict[str, Any]) -> None:
    winner = str(parsed.get("winner") or "even")
    fb_a, fb_b = _fallback_grades(winner)
    for side_key, fallback in (("side_a", fb_a), ("side_b", fb_b)):
        side = parsed.get(side_key)
        if not isinstance(side, dict):
            side = {}
            parsed[side_key] = side
        grade = _coerce_grade(side.get("trade_grade"))
        if grade is None:
            if side.get("trade_grade") is not None:
                logger.warning(
                    "trade_analyzer parser: invalid trade_grade=%r on %s, using %s",
                    side.get("trade_grade"),
                    side_key,
                    fallback,
                )
            side["trade_grade"] = fallback
        else:
            side["trade_grade"] = grade


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


def _side_stub(
    side_key: str,
    expected_totals: Optional[Dict[str, Dict[str, int]]],
    *,
    trade_grade: str = "C",
) -> Dict[str, Any]:
    exp = (expected_totals or {}).get(side_key) or {}
    return {
        "trade_grade": trade_grade,
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

    fb_a, fb_b = _fallback_grades(winner)
    out: Dict[str, Any] = {
        "winner": winner,
        "summary_bullets": bullets[:8],
        "side_a": _side_stub("side_a", expected_totals, trade_grade=fb_a),
        "side_b": _side_stub("side_b", expected_totals, trade_grade=fb_b),
    }
    cs = d.get("context_summary")
    if isinstance(cs, dict):
        out["context_summary"] = cs
    return out


def _merge_expected_ktc(
    parsed: Dict[str, Any], expected_totals: Optional[Dict[str, Dict[str, int]]]
) -> None:
    """Fill ktc_delta from request totals when the model omits numeric side blocks."""
    if not expected_totals:
        return
    for side_key in ("side_a", "side_b"):
        side = parsed.get(side_key)
        if not isinstance(side, dict):
            side = {}
            parsed[side_key] = side
        delta = side.get("ktc_delta")
        if not isinstance(delta, dict):
            delta = {}
        exp = expected_totals.get(side_key) or {}
        has_values = any(
            delta.get(k) not in (None, 0)
            for k in ("values_in", "values_out", "net")
        )
        if has_values:
            continue
        side["ktc_delta"] = {
            "values_in": int(exp.get("in") or 0),
            "values_out": int(exp.get("out") or 0),
            "net": int(exp.get("net") or 0),
            "per_asset": delta.get("per_asset") if isinstance(delta.get("per_asset"), list) else [],
        }


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
            raise ParseError(
                f"JSON decode failed: {decode_error}", raw=raw) from decode_error
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

    for key in list(parsed.keys()):
        if key not in _API_TOP_LEVEL_KEYS:
            del parsed[key]
    parsed["winner"] = _coerce_winner(
        parsed.get("winner"), expected_totals=expected_totals)
    for side_key in ("side_a", "side_b"):
        side = parsed.get(side_key)
        if not isinstance(side, dict):
            side = {}
            parsed[side_key] = side
        _normalize_side_fields(side)
    _normalize_side_grades(parsed)
    _merge_expected_ktc(parsed, expected_totals)

    _check_drift(parsed, expected_totals)
    return parsed
