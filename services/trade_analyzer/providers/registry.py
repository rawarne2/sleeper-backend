"""Lazy provider registry."""
from __future__ import annotations

from typing import Callable, Dict

from .base import LLMProvider, ProviderUnavailable

_FACTORIES: Dict[str, Callable[[], LLMProvider]] = {}


def register(name: str, factory: Callable[[], LLMProvider]) -> None:
    _FACTORIES[name] = factory


def known_providers() -> list[str]:
    return sorted(_FACTORIES.keys())


def get_provider(name: str) -> LLMProvider:
    factory = _FACTORIES.get(name)
    if factory is None:
        raise ProviderUnavailable(f"Unknown provider: {name!r}")
    return factory()


def _register_defaults() -> None:
    from .echo import EchoProvider

    register("echo", EchoProvider)


_register_defaults()
