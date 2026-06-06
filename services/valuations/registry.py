# services/valuations/registry.py
from __future__ import annotations
from typing import Callable, Dict
from services.valuations.base import ValuationSource, SourceUnavailable

_FACTORIES: Dict[str, Callable[[], ValuationSource]] = {}


def register(name: str, factory: Callable[[], ValuationSource]) -> None:
    _FACTORIES[name] = factory


def known_sources() -> list[str]:
    return sorted(_FACTORIES.keys())


def get_source(name: str) -> ValuationSource:
    factory = _FACTORIES.get(name)
    if factory is None:
        raise SourceUnavailable(f"Unknown valuation source: {name!r}")
    return factory()
