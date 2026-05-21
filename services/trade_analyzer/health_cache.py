"""In-process TTL cache around LLMProvider.health_check.

Cloud providers (Anthropic / Gemini) only check env var presence so the cache is
trivial; Ollama's check actually hits the local daemon, where caching matters
more. Failed checks use a shorter window so a recovered provider is picked up
quickly.
"""
from __future__ import annotations

import os
import time
from typing import Dict, Tuple

from services.trade_analyzer.providers.base import LLMProvider


def _ttl_seconds() -> float:
    try:
        return float(os.getenv("TRADE_ANALYZER_HEALTH_CHECK_TTL_SECONDS", "60"))
    except (TypeError, ValueError):
        return 60.0


def _failure_ttl_seconds() -> float:
    try:
        return float(os.getenv("TRADE_ANALYZER_HEALTH_CHECK_FAILURE_TTL_SECONDS", "5"))
    except (TypeError, ValueError):
        return 5.0


_TTL_SECONDS = _ttl_seconds()
_FAILURE_TTL_SECONDS = _failure_ttl_seconds()

_cache: Dict[str, Tuple[float, Tuple[bool, str]]] = {}


def reset_cache() -> None:
    _cache.clear()


def cached_health_check(provider: LLMProvider) -> Tuple[bool, str]:
    now = time.monotonic()
    key = getattr(provider, "name", type(provider).__name__)
    entry = _cache.get(key)
    if entry and entry[0] > now:
        return entry[1]

    result = provider.health_check()
    ttl = _TTL_SECONDS if result[0] else _FAILURE_TTL_SECONDS
    _cache[key] = (now + ttl, result)
    return result
