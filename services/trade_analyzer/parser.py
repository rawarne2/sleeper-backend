"""Defensive JSON parser for LLM responses."""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_REQUIRED_KEYS = ("fairness_score", "winner", "summary_bullets", "side_a", "side_b")
_FENCE = re.compile(r"^```(?:json)?\s*|\s*```\s*$", re.MULTILINE)


class ParseError(Exception):
    def __init__(self, message: str, *, raw: str = "") -> None:
        super().__init__(message)
        self.raw = raw


def _slice_outermost_object(s: str) -> str:
    start = s.find("{")
    end = s.rfind("}")
    if start < 0 or end <= start:
        raise ParseError("No JSON object found in response", raw=s)
    return s[start:end + 1]


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
    s = _FENCE.sub("", raw.strip())
    candidate = _slice_outermost_object(s)
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise ParseError(f"JSON decode failed: {exc}", raw=raw) from exc

    if not isinstance(parsed, dict):
        raise ParseError("Response is not a JSON object", raw=raw)

    missing = [k for k in _REQUIRED_KEYS if k not in parsed]
    if missing:
        raise ParseError(f"Missing required keys: {missing}", raw=raw)

    parsed["fairness_score"] = _coerce_score(parsed.get("fairness_score"))
    parsed["winner"] = _coerce_winner(parsed.get("winner"), parsed["fairness_score"])

    _check_drift(parsed, expected_totals)
    return parsed
