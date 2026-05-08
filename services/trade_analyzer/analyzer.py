"""Orchestrator: validate -> context -> prompt -> provider -> parse."""
from __future__ import annotations

import json as _json
import logging
import time
from typing import Any, Dict

from data_types.trade_analyzer_types import TradeRequest
from services.trade_analyzer._load_league import LeagueNotFound, load_league_bundle
from services.trade_analyzer.context import build_context
from services.trade_analyzer.prompt import SYSTEM_PROMPT, build_user_prompt
from services.trade_analyzer.providers.base import (
    ProviderError, ProviderTimeout, ProviderUnavailable,
)
from services.trade_analyzer.providers.registry import get_provider

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

    available, detail = provider.health_check()
    if not available:
        return AnalyzerOutcome(status_code=503, body={
            "status": "error", "error": "Provider unavailable", "details": detail,
            "provider_used": provider_name,
        })

    try:
        league_data = load_league_bundle(
            req["league_id"], req["ktc"]["league_format"], req["ktc"].get("tep_level") or "")
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

    user_prompt = build_user_prompt(context, req.get("additional_context"))

    try:
        raw = provider.generate(SYSTEM_PROMPT, user_prompt, model=model, timeout_s=timeout_s)
    except ProviderTimeout as exc:
        return AnalyzerOutcome(status_code=504, body={
            "status": "error", "error": "Provider timeout", "details": str(exc),
            "provider_used": provider_name, "model_used": model,
        })
    except ProviderError as exc:
        return AnalyzerOutcome(status_code=503, body={
            "status": "error", "error": "Provider failure", "details": str(exc),
            "provider_used": provider_name, "model_used": model,
        })

    try:
        parsed = _json.loads(raw)
    except _json.JSONDecodeError as exc:
        return AnalyzerOutcome(status_code=502, body={
            "status": "error", "error": "LLM returned invalid JSON",
            "details": str(exc), "provider_used": provider_name,
            "model_used": model, "raw_response": raw[:4096],
        })

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    body = dict(parsed)
    body["provider_used"] = provider_name
    body["model_used"] = model
    body["elapsed_ms"] = elapsed_ms
    logger.info(
        "trade_analyzer call provider=%s model=%s league_id=%s elapsed_ms=%s parse_ok=true",
        provider_name, model, req["league_id"], elapsed_ms,
    )
    return AnalyzerOutcome(status_code=200, body=body)
