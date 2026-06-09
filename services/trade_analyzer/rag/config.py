"""RAG feature flags and tuning knobs."""
from __future__ import annotations

import os


def _env_bool(key: str, *, default: bool = False) -> bool:
    raw = os.environ.get(key)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def trade_analyzer_rag_enabled() -> bool:
    return _env_bool("TRADE_ANALYZER_RAG", default=False)


def rag_top_k() -> int:
    return max(1, int(os.environ.get("TRADE_ANALYZER_RAG_TOP_K", "5")))


def rag_min_score() -> float:
    return float(os.environ.get("TRADE_ANALYZER_RAG_MIN_SCORE", "0.55"))


def embedding_provider_name() -> str:
    return os.environ.get("TRADE_ANALYZER_EMBEDDING_PROVIDER", "ollama").strip().lower()


def embedding_model_name() -> str:
    return os.environ.get("TRADE_ANALYZER_EMBEDDING_MODEL", "nomic-embed-text").strip()
