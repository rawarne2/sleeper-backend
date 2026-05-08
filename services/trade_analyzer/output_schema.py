"""JSON Schema for Ollama structured outputs (trade analyzer response shape).

Ollama ``format`` accepts this dict to constrain decoding to the API contract.
See https://docs.ollama.com/capabilities/structured-outputs
"""
from __future__ import annotations

from typing import Any, Dict

# Nested side objects stay loosely typed so the model can follow SYSTEM_PROMPT detail;
# required top-level keys fix the common failure mode where the model emits only
# ad-hoc keys like trade_details.
TRADE_ANALYZER_JSON_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "fairness_score": {"type": "integer"},
        "winner": {
            "type": "string",
            "enum": ["side_a", "side_b", "even"],
        },
        "summary_bullets": {
            "type": "array",
            "items": {"type": "string"},
        },
        "side_a": {"type": "object"},
        "side_b": {"type": "object"},
        "context_summary": {"type": "object"},
    },
    "required": [
        "fairness_score",
        "winner",
        "summary_bullets",
        "side_a",
        "side_b",
    ],
}
