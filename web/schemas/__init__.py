"""Pydantic v2 response schemas for the core public endpoints.

These models document the OpenAPI schema for routes that serialize responses by
hand (pre-built dicts / pre-serialized ``Response`` bytes). They are the source of
truth for the dashboard's generated TypeScript types and are enforced against the
real route responses by ``tests/api/test_response_contracts.py``.
"""
from web.schemas.dashboard import (
    DashboardLeagueBundle,
    DashboardLeagueResponse,
    DashboardPick,
    DashboardPlayer,
    DataSource,
    InjuryReport,
    KtcPlayerBlock,
    KtcTierValues,
    KtcValuesBlock,
    LeagueInfo,
    NewsItem,
    OwnershipEntry,
    PlayersAllResponse,
    ProjectionBlock,
    ResearchLatest,
    ResearchMeta,
    RosterInfo,
    SeasonStats,
    SourceValue,
    UsageBlock,
    UserInfo,
    ValuesBlock,
)
from web.schemas.ktc import (
    KtcRefreshAccepted,
    KtcRefreshJobStatus,
    KtcRefreshJobSummary,
)

__all__ = [
    "DashboardLeagueResponse",
    "DashboardLeagueBundle",
    "DashboardPlayer",
    "DashboardPick",
    "DataSource",
    "InjuryReport",
    "KtcPlayerBlock",
    "KtcTierValues",
    "KtcValuesBlock",
    "LeagueInfo",
    "NewsItem",
    "OwnershipEntry",
    "PlayersAllResponse",
    "ProjectionBlock",
    "ResearchLatest",
    "ResearchMeta",
    "RosterInfo",
    "SeasonStats",
    "SourceValue",
    "UsageBlock",
    "UserInfo",
    "ValuesBlock",
    "KtcRefreshAccepted",
    "KtcRefreshJobStatus",
    "KtcRefreshJobSummary",
]
