"""System prompt and user-prompt assembly."""
from __future__ import annotations

import json
from typing import Any, Dict, Optional


SYSTEM_PROMPT = """You are an expert dynasty fantasy football trade analyst. \
Return STRICT JSON only — no prose, no markdown fences, no preamble.

Weighting:
- KTC values are the primary signal for raw asset value. Use the precomputed ktc_totals as your anchor.
- Adjust for positional scarcity, depth, and contention window using each side's team_needs_signals.
- Adjust for age curves vs. contention window: a "rebuild" side prefers picks and young assets;
  a "now" side prefers proven veterans.
- Use stats trajectory: a player trending up over the last 3 weeks rates higher than their season
  average alone.

Score scale: 0-100 where 50 = perfectly even. >50 favors side A; <50 favors side B.
A 5-point swing = slight edge; 15-point = clear winner; 30-point = fleecing.

Return JSON exactly matching this schema (no extra keys):
{ "fairness_score": int, "winner": "side_a"|"side_b"|"even", "summary_bullets": [str],
  "side_a": { "pros": [str], "cons": [str],
              "ktc_delta": { "values_in": int, "values_out": int, "net": int,
                             "per_asset": [{ "name": str, "value": int, "direction": "in"|"out" }] },
              "sleeper_breakdown": { "stats_trajectory": [str], "positional_impact": str,
                                     "team_needs_addressed": [str] } },
  "side_b": { same shape },
  "context_summary": { "side_a_team_needs": [str], "side_b_team_needs": [str] } }
"""


def build_user_prompt(context: Dict[str, Any], additional: Optional[str]) -> str:
    payload = json.dumps(context, separators=(",", ":"))
    extra = additional.strip() if additional and additional.strip() else "(none)"
    return f"{payload}\n\nADDITIONAL USER CONTEXT:\n{extra}"
