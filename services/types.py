"""Typed shapes for service-layer return values (documentation / static checks)."""
from typing import Any, Dict, List, TypedDict


class DailyRefreshSummary(TypedDict, total=False):
    ktc: Any
    leagues: Any
    research: List[Any]
    errors: List[Any]
