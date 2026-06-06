# services/valuations/base.py
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


class SourceError(Exception):
    """Base for valuation-source failures."""


class SourceUnavailable(SourceError):
    """Unknown or unreachable source."""


@dataclass(frozen=True)
class SourceMeta:
    key: str
    display_name: str
    kind: str  # "trade_value" | "projection"
    attribution_url: str = ""


@dataclass
class ValuationRow:
    source_key: str
    external_id: str
    name: str
    position: str
    team: Optional[str]
    metric_key: str            # value|redraft_value|proj_ros|proj_week|trade_frequency|volatility
    metric_value: Optional[float]
    rank: Optional[int] = None
    as_of: Optional[datetime] = None
    raw: dict[str, Any] = field(default_factory=dict)


class ValuationSource(ABC):
    meta: SourceMeta

    @abstractmethod
    def fetch(self, *, season: str, league_format: str,
              league_settings: dict[str, Any]) -> list[ValuationRow]:
        """Return current rows for the given format/settings."""

    @abstractmethod
    def health(self) -> tuple[bool, str]:
        """Return (available, human-readable detail)."""
