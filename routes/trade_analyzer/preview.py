"""POST /api/trade-analyzer/preview — assemble context, no LLM call."""
from __future__ import annotations

import os

from flask import jsonify, request

from routes.helpers import json_api_error, with_error_handling
from routes.trade_analyzer.request_schema import (
    RequestValidationError, parse_trade_request,
)
from services.trade_analyzer._load_league import LeagueNotFound, load_league_bundle
from services.trade_analyzer.context import build_context
from services.trade_analyzer.prompt import SYSTEM_PROMPT, build_user_prompt

from . import trade_analyzer_bp


def _default_provider() -> str:
    return os.getenv("TRADE_ANALYZER_DEFAULT_PROVIDER", "ollama").strip().lower()


def _default_model_for(provider: str) -> str:
    env_key = f"TRADE_ANALYZER_{provider.upper()}_MODEL"
    fallback = {
        "ollama": "qwen2.5:14b-instruct",
        "anthropic": "claude-haiku-4-5-20251001",
        "gemini": "gemini-2.5-flash",
        "groq": "llama-3.3-70b-versatile",
        "echo": "echo",
    }.get(provider, "echo")
    return os.getenv(env_key, fallback)


@trade_analyzer_bp.route("/preview", methods=["POST"])
@with_error_handling
def preview_trade():
    try:
        req = parse_trade_request(request.get_json(silent=True))
    except RequestValidationError as exc:
        return json_api_error(str(exc), 400)

    provider = req.get("provider") or _default_provider()
    model = req.get("model") or _default_model_for(provider)

    try:
        league_data = load_league_bundle(
            req["league_id"], req["ktc"]["league_format"], req["ktc"].get("tep_level") or "")
    except LeagueNotFound as exc:
        return json_api_error("League not found", 404, details=str(exc), league_id=req["league_id"])

    try:
        context = build_context(req, league_data=league_data)
    except ValueError as exc:
        return json_api_error(str(exc), 400)

    user_prompt = build_user_prompt(context, req.get("additional_context"))
    estimated_tokens = max(1, (len(SYSTEM_PROMPT) + len(user_prompt)) // 4)

    return jsonify({
        "context": context,
        "system_prompt": SYSTEM_PROMPT,
        "user_prompt": user_prompt,
        "estimated_tokens": estimated_tokens,
        "provider_used": provider,
        "model_used": model,
    })
