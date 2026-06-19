"""POST /api/trade-analyzer/preview — assemble context, no LLM call."""
from __future__ import annotations

from fastapi import Body

from services.trade_analyzer import policy as ta_policy
from routes.trade_analyzer.request_schema import (
    RequestValidationError, parse_trade_request,
)
from services.trade_analyzer._load_league import LeagueNotFound, load_league_bundle
from services.trade_analyzer.context import build_context
from services.trade_analyzer.prompt import SYSTEM_PROMPT, build_user_prompt
from services.trade_analyzer.tokens import estimate_prompt_tokens
from web.errors import ApiError

from . import router


@router.post("/preview")
def preview_trade(body: dict | None = Body(default=None)):
    try:
        req = parse_trade_request(body)
    except RequestValidationError as exc:
        raise ApiError(str(exc), 400)

    deny = ta_policy.environment_provider_error(req.get("provider"))
    if deny:
        raise ApiError(deny, 400)

    provider, model = ta_policy.resolved_provider_and_model(
        body_provider=req.get("provider"),
        body_model=req.get("model"),
    )

    try:
        league_data = load_league_bundle(
            req["league_id"],
            req["ktc"]["league_format"],
            req["ktc"].get("tep_level") or "",
            season=req["season"],
            is_redraft=bool(req["ktc"].get("is_redraft")),
        )
    except LeagueNotFound as exc:
        raise ApiError("League not found", 404, details=str(exc), league_id=req["league_id"])

    try:
        context = build_context(req, league_data=league_data)
    except ValueError as exc:
        raise ApiError(str(exc), 400)

    user_prompt = build_user_prompt(context, req.get("additional_context"))
    token_usage = estimate_prompt_tokens(SYSTEM_PROMPT, user_prompt)

    return {
        "context": context,
        "system_prompt": SYSTEM_PROMPT,
        "user_prompt": user_prompt,
        "estimated_tokens": token_usage["prompt_tokens_estimated"],
        "token_usage": token_usage,
        "provider_used": provider,
        "model_used": model,
    }
