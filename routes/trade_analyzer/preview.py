"""POST /api/trade-analyzer/preview - assemble context, no LLM call.

Phase 1 returns a STUB context. Task 8/9 replaces _stub_context with the real
build_context() driven from the DB-backed league bundle.
"""
from __future__ import annotations

import json
import os

from flask import jsonify, request

from routes.helpers import json_api_error, with_error_handling
from routes.trade_analyzer.request_schema import (
    RequestValidationError,
    parse_trade_request,
)

from . import trade_analyzer_bp


def _default_provider() -> str:
    return os.getenv("TRADE_ANALYZER_DEFAULT_PROVIDER", "ollama").strip().lower()


def _default_model_for(provider: str) -> str:
    env_key = f"TRADE_ANALYZER_{provider.upper()}_MODEL"
    return os.getenv(env_key, {
        "ollama": "qwen2.5:14b-instruct",
        "anthropic": "claude-haiku-4-5-20251001",
        "gemini": "gemini-2.5-flash",
        "groq": "llama-3.3-70b-versatile",
        "echo": "echo",
    }.get(provider, "echo"))


def _stub_context(req) -> dict:
    return {
        "league": {"league_id": req["league_id"], "season": req["season"], "ktc": req["ktc"]},
        "side_a": {"roster_id": req["side_a"]["roster_id"]},
        "side_b": {"roster_id": req["side_b"]["roster_id"]},
        "trade": {"side_a_outgoing": [], "side_b_outgoing": []},
        "additional_context": req.get("additional_context"),
    }


@trade_analyzer_bp.route("/preview", methods=["POST"])
@with_error_handling
def preview_trade():
    try:
        req = parse_trade_request(request.get_json(silent=True))
    except RequestValidationError as exc:
        return json_api_error(str(exc), 400)

    provider = req.get("provider") or _default_provider()
    model = req.get("model") or _default_model_for(provider)

    context = _stub_context(req)
    system_prompt = "You are a fantasy football trade analyst. (stub)"
    user_prompt = json.dumps(context, separators=(",", ":"))
    estimated_tokens = max(1, (len(system_prompt) + len(user_prompt)) // 4)

    return jsonify({
        "context": context,
        "system_prompt": system_prompt,
        "user_prompt": user_prompt,
        "estimated_tokens": estimated_tokens,
        "provider_used": provider,
        "model_used": model,
    })
