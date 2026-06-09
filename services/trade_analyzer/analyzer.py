"""Orchestrator: validate -> context -> prompt -> provider -> parse."""
from __future__ import annotations

import logging
import time
import uuid
from datetime import UTC, datetime
from typing import Any, Dict

from data_types.trade_analyzer_types import TradeRequest
from services.trade_analyzer._load_league import LeagueNotFound, load_league_bundle
from services.trade_analyzer.context import build_context
from services.trade_analyzer.health_cache import cached_health_check
from services.trade_analyzer.parser import ParseError, parse_llm_response
from services.trade_analyzer.policy import trade_analyzer_debug_log_enabled
from services.trade_analyzer.prompt import SYSTEM_PROMPT, build_user_prompt
from services.trade_analyzer.rag.config import trade_analyzer_rag_enabled
from services.trade_analyzer.tokens import estimate_prompt_tokens
from services.trade_analyzer.providers.base import (
    ProviderError,
    ProviderRateLimited,
    ProviderTimeout,
    ProviderUnavailable,
)
from services.trade_analyzer.providers.registry import get_provider
from services.trade_analyzer.feedback_store import stash_analysis

logger = logging.getLogger(__name__)


class AnalyzerOutcome:
    def __init__(self, *, status_code: int, body: Dict[str, Any]) -> None:
        self.status_code = status_code
        self.body = body


def run_analysis(req: TradeRequest, *, provider_name: str, model: str, timeout_s: int) -> AnalyzerOutcome:
    started = time.perf_counter()

    try:
        provider = get_provider(provider_name)
    except ProviderUnavailable as exc:
        return AnalyzerOutcome(status_code=503, body={
            "status": "error", "error": "Provider unavailable", "details": str(exc),
        })

    available, detail = cached_health_check(provider)
    if not available:
        return AnalyzerOutcome(status_code=503, body={
            "status": "error", "error": "Provider unavailable", "details": detail,
            "provider_used": provider_name,
        })

    try:
        league_data = load_league_bundle(
            req["league_id"],
            req["ktc"]["league_format"],
            req["ktc"].get("tep_level") or "",
            season=req["season"],
            is_redraft=bool(req["ktc"].get("is_redraft")),
        )
    except LeagueNotFound as exc:
        return AnalyzerOutcome(status_code=404, body={
            "status": "error", "error": "League not found",
            "details": str(exc), "league_id": req["league_id"],
        })

    try:
        context = build_context(req, league_data=league_data)
    except ValueError as exc:
        return AnalyzerOutcome(status_code=400, body={
            "status": "error", "error": str(exc),
        })

    retrieved = None
    rag_chunks = 0
    if trade_analyzer_rag_enabled():
        try:
            from services.trade_analyzer.rag.query import build_rag_query
            from services.trade_analyzer.rag.retrieve import retrieve_context

            retrieved = retrieve_context(build_rag_query(context, req))
            rag_chunks = len(retrieved)
        except Exception:
            logger.warning("trade_analyzer rag retrieval failed", exc_info=True)
    user_prompt = build_user_prompt(
        context, req.get("additional_context"), retrieved=retrieved,
    )
    if trade_analyzer_debug_log_enabled():
        logger.info(
            "trade_analyzer debug parsed_request league_id=%s provider=%s model=%s: %s",
            req["league_id"],
            provider_name,
            model,
            req,
        )
        logger.info("trade_analyzer debug system_prompt:\n%s", SYSTEM_PROMPT)
        logger.info("trade_analyzer debug user_prompt:\n%s", user_prompt)
    token_usage = estimate_prompt_tokens(SYSTEM_PROMPT, user_prompt)
    logger.info(
        "trade_analyzer prompt_tokens_estimated=%s system_chars=%s user_chars=%s "
        "rag_chunks_retrieved=%s league_id=%s",
        token_usage["prompt_tokens_estimated"],
        token_usage["system_chars"],
        token_usage["user_chars"],
        rag_chunks,
        req["league_id"],
    )

    try:
        raw = provider.generate(SYSTEM_PROMPT, user_prompt, model=model, timeout_s=timeout_s)
    except ProviderRateLimited as exc:
        retry_after = (
            exc.retry_after_seconds
            if isinstance(exc.retry_after_seconds, int) and exc.retry_after_seconds > 0
            else 60
        )
        return AnalyzerOutcome(status_code=429, body={
            "status": "error",
            "error": str(exc),
            "details": str(exc),
            "provider_used": provider_name,
            "model_used": model,
            "retry_after_seconds": retry_after,
        })
    except ProviderTimeout as exc:
        return AnalyzerOutcome(status_code=504, body={
            "status": "error", "error": str(exc), "details": str(exc),
            "provider_used": provider_name, "model_used": model,
        })
    except ProviderError as exc:
        return AnalyzerOutcome(status_code=503, body={
            "status": "error", "error": str(exc), "details": str(exc),
            "provider_used": provider_name, "model_used": model,
        })

    try:
        parsed = parse_llm_response(
            raw, expected_totals=context["trade"]["consensus_totals"],
        )
    except ParseError as exc:
        return AnalyzerOutcome(status_code=502, body={
            "status": "error", "error": "LLM returned invalid JSON",
            "details": str(exc), "provider_used": provider_name,
            "model_used": model, "raw_response": exc.raw[:4096],
        })

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    body = dict(parsed)
    analysis_id = uuid.uuid4().hex
    body["analysis_id"] = analysis_id
    body["provider_used"] = provider_name
    body["model_used"] = model
    body["elapsed_ms"] = elapsed_ms
    body.update(token_usage)
    logger.info(
        "trade_analyzer call provider=%s model=%s league_id=%s elapsed_ms=%s "
        "prompt_tokens_estimated=%s parse_ok=true",
        provider_name,
        model,
        req["league_id"],
        elapsed_ms,
        token_usage["prompt_tokens_estimated"],
    )
    stash_analysis(analysis_id, {
        "request": req,
        "context": context,
        "response": parsed,
        "provider": provider_name,
        "model": model,
        "league_id": req.get("league_id"),
        "created_at": datetime.now(UTC).isoformat(),
    })
    return AnalyzerOutcome(status_code=200, body=body)
