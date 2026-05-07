"""TypedDicts for the trade analyzer."""
from __future__ import annotations

from typing import List, Literal, Optional, TypedDict


class KTCConfig(TypedDict, total=False):
    league_format: Literal["1qb", "superflex"]
    is_redraft: bool
    tep_level: Optional[Literal["", "tep", "tepp", "teppp"]]


class TradeSide(TypedDict):
    roster_id: int
    player_ids: List[str]
    pick_ids: List[str]


class TradeRequest(TypedDict, total=False):
    league_id: str
    season: str
    ktc: KTCConfig
    side_a: TradeSide
    side_b: TradeSide
    additional_context: Optional[str]
    provider: Optional[str]
    model: Optional[str]


class OwnedPick(TypedDict):
    season: str
    round: int
    original_roster_id: int
    slot_bucket: str
    pick_id: str
    ktc_value: Optional[int]


class ProviderInfo(TypedDict):
    name: str
    default_model: str
    available: bool
    detail: str
