"""Lazy embedding provider registry."""
from __future__ import annotations

from typing import Callable, Dict

from services.trade_analyzer.rag.config import embedding_model_name, embedding_provider_name
from services.trade_analyzer.rag.embeddings.base import EmbeddingProvider

_FACTORIES: Dict[str, Callable[[], EmbeddingProvider]] = {}


def register(name: str, factory: Callable[[], EmbeddingProvider]) -> None:
    _FACTORIES[name] = factory


def known_providers() -> list[str]:
    return sorted(_FACTORIES.keys())


def get_embedding_provider(name: str | None = None) -> EmbeddingProvider:
    key = (name or embedding_provider_name()).strip().lower()
    factory = _FACTORIES.get(key)
    if factory is None:
        raise ValueError(f"Unknown embedding provider: {key!r}")
    return factory()


def _register_defaults() -> None:
    from services.trade_analyzer.rag.embeddings.ollama import OllamaEmbeddingProvider

    register("ollama", lambda: OllamaEmbeddingProvider(model=embedding_model_name()))


_register_defaults()
