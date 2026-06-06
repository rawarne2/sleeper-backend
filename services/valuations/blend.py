# services/valuations/blend.py
from __future__ import annotations
import os
from typing import Dict, Optional

_SCALE = 10000.0


def default_weights() -> Dict[str, float]:
    """Per-source blend weights (env-overridable). v1: 50/50 KTC/FantasyCalc."""
    return {
        "ktc": float(os.getenv("VALUATION_WEIGHT_KTC", "0.5")),
        "fantasycalc": float(os.getenv("VALUATION_WEIGHT_FANTASYCALC", "0.5")),
    }


def normalize_min_max(values: Dict[str, float]) -> Dict[str, float]:
    """Linearly scale a source's values into [0, _SCALE] across the asset set."""
    if not values:
        return {}
    lo = min(values.values())
    hi = max(values.values())
    if hi == lo:
        return {k: _SCALE / 2 for k in values}
    span = hi - lo
    return {k: (v - lo) / span * _SCALE for k, v in values.items()}


def blend_values(
    per_source: Dict[str, Dict[str, float]],
    weights: Dict[str, float],
) -> Dict[str, Optional[float]]:
    """Normalize each source, then weighted-average per asset over present sources."""
    normed = {s: normalize_min_max(vals) for s, vals in per_source.items()}
    keys: set[str] = set()
    for vals in normed.values():
        keys.update(vals.keys())
    out: Dict[str, Optional[float]] = {}
    for k in keys:
        num = 0.0
        den = 0.0
        for s, vals in normed.items():
            w = weights.get(s, 0.0)
            if w > 0 and k in vals:
                num += w * vals[k]
                den += w
        out[k] = round(num / den, 1) if den else None
    return out
