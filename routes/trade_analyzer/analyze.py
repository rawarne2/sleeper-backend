"""POST /api/trade-analyzer/analyze."""
from __future__ import annotations

import logging
import os

from flask import jsonify, request

from cache.rate_limiter import get_rate_limiter
from routes.helpers import json_api_error, with_error_handling
from routes.trade_analyzer.request_schema import (
    RequestValidationError, parse_trade_request,
)
from services.trade_analyzer.analyzer import run_analysis

from . import trade_analyzer_bp

logger = logging.getLogger(__name__)


def _enabled() -> bool:
    return (os.getenv("TRADE_ANALYZER_ENABLED", "true").strip().lower()
            not in ("0", "false", "no"))


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


def _timeout_for(provider: str) -> int:
    env_key = f"TRADE_ANALYZER_{provider.upper()}_TIMEOUT_SECONDS"
    fallback = {"ollama": 120, "anthropic": 60, "gemini": 60, "groq": 30}.get(provider, 30)
    return int(os.getenv(env_key, str(fallback)))


def _rate_limit_key(req) -> str:
    mode = os.getenv("TRADE_ANALYZER_RATE_LIMIT_KEY", "ip").strip().lower()
    if mode == "league_id":
        return f"trade_analyzer:rl:v1:league:{req['league_id']}"
    ip = (request.headers.get("X-Forwarded-For") or request.remote_addr or "0.0.0.0").split(",")[0].strip()
    return f"trade_analyzer:rl:v1:ip:{ip}"


@trade_analyzer_bp.route("/analyze", methods=["POST"])
@with_error_handling
def analyze_trade():
    if not _enabled():
        return json_api_error(
            "Trade Analyzer is disabled", 503,
            details="Set TRADE_ANALYZER_ENABLED=true to re-enable",
        )

    try:
        req = parse_trade_request(request.get_json(silent=True))
    except RequestValidationError as exc:
        return json_api_error(str(exc), 400)

    limiter = get_rate_limiter(
        limit=int(os.getenv("TRADE_ANALYZER_RATE_LIMIT_PER_HOUR", "20")),
        window_s=int(os.getenv("TRADE_ANALYZER_RATE_LIMIT_WINDOW_SECONDS", "3600")),
    )
    allowed, retry_after = limiter.check_and_record(_rate_limit_key(req))
    if not allowed:
        return json_api_error(
            "Rate limit exceeded", 429,
            details=f"Try again in {retry_after} seconds",
            retry_after_seconds=retry_after,
        )

    provider_name = req.get("provider") or _default_provider()
    model = req.get("model") or _default_model_for(provider_name)
    timeout_s = _timeout_for(provider_name)

    outcome = run_analysis(req, provider_name=provider_name, model=model, timeout_s=timeout_s)
    return jsonify(outcome.body), outcome.status_code
