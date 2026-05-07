"""Orchestrator: validate -> context -> prompt -> provider -> parse.

Phase 1 version: minimal echo end-to-end, no real context, no parser. Tasks 8-10
rebuild this with real context + the robust parser.
"""
from __future__ import annotations

import json
import time
from typing import Any, Dict

from data_types.trade_analyzer_types import TradeRequest
from services.trade_analyzer.providers.base import (
    ProviderError, ProviderTimeout, ProviderUnavailable,
)
from services.trade_analyzer.providers.registry import get_provider


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
            "status": "error", "error": "Provider unavailable",
            "details": detail, "provider_used": provider_name,
        })

    system_prompt = "stub"
    user_prompt = json.dumps({"req": req}, default=str)

    try:
        raw = provider.generate(system_prompt, user_prompt, model=model, timeout_s=timeout_s)
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
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
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
    return AnalyzerOutcome(status_code=200, body=body)
