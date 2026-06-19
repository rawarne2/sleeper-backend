"""POST /api/trade-analyzer/analyze."""
from __future__ import annotations

import os

from fastapi import Body
from fastapi.responses import JSONResponse
from starlette.requests import Request

from cache.rate_limiter import get_rate_limiter
from services.trade_analyzer import policy as ta_policy
from routes.trade_analyzer.request_schema import (
    RequestValidationError, parse_trade_request,
)
from services.trade_analyzer.analyzer import run_analysis
from web.errors import ApiError

from . import router


def _enabled() -> bool:
    return (os.getenv("TRADE_ANALYZER_ENABLED", "true").strip().lower()
            not in ("0", "false", "no"))


def _timeout_for(provider: str) -> int:
    env_key = f"TRADE_ANALYZER_{provider.upper()}_TIMEOUT_SECONDS"
    fallback = {"ollama": 120, "anthropic": 60,
                "gemini": 60, "groq": 30}.get(provider, 30)
    return int(os.getenv(env_key, str(fallback)))


def _rate_limit_key(req, request: Request) -> str:
    mode = os.getenv("TRADE_ANALYZER_RATE_LIMIT_KEY", "ip").strip().lower()
    if mode == "league_id":
        return f"trade_analyzer:rl:v1:league:{req['league_id']}"
    ip = (request.headers.get("X-Forwarded-For")
          or (request.client.host if request.client else None)
          or "0.0.0.0").split(",")[0].strip()
    return f"trade_analyzer:rl:v1:ip:{ip}"


@router.post("/analyze")
def analyze_trade(request: Request, body: dict | None = Body(default=None)):
    if not _enabled():
        raise ApiError(
            "Trade Analyzer is disabled", 503,
            details="Set TRADE_ANALYZER_ENABLED=true to re-enable",
        )

    try:
        req = parse_trade_request(body)
    except RequestValidationError as exc:
        raise ApiError(str(exc), 400)

    deny = ta_policy.environment_provider_error(req.get("provider"))
    if deny:
        raise ApiError(deny, 400)

    limiter = get_rate_limiter(
        limit=int(os.getenv("TRADE_ANALYZER_RATE_LIMIT_PER_HOUR", "20")),
        window_s=int(
            os.getenv("TRADE_ANALYZER_RATE_LIMIT_WINDOW_SECONDS", "3600")),
    )
    allowed, retry_after = limiter.check_and_record(_rate_limit_key(req, request))
    if not allowed:
        raise ApiError(
            "Rate limit exceeded", 429,
            details=f"Try again in {retry_after} seconds",
            retry_after_seconds=retry_after,
        )

    provider_name, model = ta_policy.resolved_provider_and_model(
        body_provider=req.get("provider"),
        body_model=req.get("model"),
    )
    timeout_s = _timeout_for(provider_name)
    outcome = run_analysis(req, provider_name=provider_name,
                           model=model, timeout_s=timeout_s)
    return JSONResponse(outcome.body, status_code=outcome.status_code)
