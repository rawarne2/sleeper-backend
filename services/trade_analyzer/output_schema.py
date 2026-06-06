"""Canonical JSON Schema for the trade-analyzer response.

Used by every provider that supports structured output (Gemini ``response_schema``,
Ollama ``format=<schema>``). Keeps payloads uniform and prevents shape drift like
``trade_details`` wrappers that the parser would otherwise have to recover from.
"""
from __future__ import annotations

from typing import Any, Dict

_GRADE_ENUM = [
    "A+", "A", "A-",
    "B+", "B", "B-",
    "C+", "C", "C-",
    "D+", "D", "D-",
    "F+", "F", "F-",
]

_PER_ASSET: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "value": {"type": "integer"},
        "direction": {"type": "string", "enum": ["in", "out"]},
        "sources": {"type": "object"},   # optional per-asset {ktc, fantasycalc}
    },
    "required": ["name", "value", "direction"],
}

_KTC_DELTA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "values_in": {"type": "integer"},
        "values_out": {"type": "integer"},
        "net": {"type": "integer"},
        "per_asset": {"type": "array", "items": _PER_ASSET},
    },
    "required": ["values_in", "values_out", "net", "per_asset"],
}

_SLEEPER_BREAKDOWN: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "stats_trajectory": {"type": "array", "items": {"type": "string"}},
        "positional_impact": {"type": "string"},
        "team_needs_addressed": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["stats_trajectory", "positional_impact", "team_needs_addressed"],
}

_SIDE: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "trade_grade": {"type": "string", "enum": _GRADE_ENUM},
        "pros": {"type": "array", "items": {"type": "string"}},
        "cons": {"type": "array", "items": {"type": "string"}},
        "ktc_delta": _KTC_DELTA,
        "sleeper_breakdown": _SLEEPER_BREAKDOWN,
    },
    "required": ["trade_grade", "pros", "cons", "ktc_delta", "sleeper_breakdown"],
}

_CONTEXT_SUMMARY: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "side_a_team_needs": {"type": "array", "items": {"type": "string"}},
        "side_b_team_needs": {"type": "array", "items": {"type": "string"}},
    },
}

TRADE_ANALYZER_JSON_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "winner": {"type": "string", "enum": ["side_a", "side_b", "even"]},
        "summary_bullets": {"type": "array", "items": {"type": "string"}},
        "side_a": _SIDE,
        "side_b": _SIDE,
        "context_summary": _CONTEXT_SUMMARY,
    },
    "required": ["winner", "summary_bullets", "side_a", "side_b"],
}
