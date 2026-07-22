"""Response schemas for the dashboard bundle and /api/players/all.

These are docs-only on the ``Response``-returning routes (the routes emit
pre-serialized JSON bytes), and enforced at runtime by
``tests/api/test_response_contracts.py``. ``extra="forbid"`` on owned shapes is the
drift guard: a new serializer field must be added here (and openapi.json + the
dashboard's generated types regenerated) or the contract tests fail.

Every field mirrors ``routes/dashboard_league.py::_player_to_dashboard_dict`` and the
bundle assembly; the Sleeper-snapshot shapes (league/roster/user) use ``extra="allow"``
because their payloads legitimately vary by league type.
"""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict


class KtcTierValues(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: Optional[int] = None
    rank: Optional[int] = None
    positionalRank: Optional[int] = None
    overallTier: Optional[int] = None
    positionalTier: Optional[int] = None


class KtcValuesBlock(KtcTierValues):
    """Base fields plus the three TEP variants (``_ktc_values_block_for_dashboard``)."""
    tep: KtcTierValues
    tepp: KtcTierValues
    teppp: KtcTierValues


class KtcPlayerBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    age: Optional[float] = None
    pickRound: Optional[int] = None
    pickNum: Optional[int] = None
    isTrending: Optional[bool] = None
    draftYear: Optional[int] = None
    byeWeek: Optional[int] = None
    injury: Optional[Dict[str, Any]] = None
    is_redraft: bool
    oneQBValues: Optional[KtcValuesBlock] = None
    superflexValues: Optional[KtcValuesBlock] = None


class SourceValue(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: Optional[float] = None
    rank: Optional[int] = None
    redraft_value: Optional[float] = None
    trade_frequency: Optional[float] = None
    volatility: Optional[float] = None
    trend_30day: Optional[float] = None


class ProjectionBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    proj_ros: Optional[float] = None
    proj_week: Optional[float] = None


class ValuesBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    consensus: Optional[float] = None
    sources: Dict[str, SourceValue]
    projection: ProjectionBlock


class SeasonStats(BaseModel):
    model_config = ConfigDict(extra="forbid")
    average_points: float
    total_points: float
    games_played: int


class UsageBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    games_started: int
    snap_pct: Optional[float] = None
    snap_pct_l3: Optional[float] = None
    snap_trend: Optional[str] = None
    targets_per_game: Optional[float] = None
    carries_per_game: Optional[float] = None
    air_yards_per_game: Optional[float] = None
    rz_opps: Optional[int] = None


class ResearchLatest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    week: int
    owned: Optional[float] = None
    started: Optional[float] = None


class NewsItem(BaseModel):
    """One headline from ``services/news.py::latest_player_news``."""
    model_config = ConfigDict(extra="forbid")
    source: str
    headline: str
    url: str
    image_url: Optional[str] = None
    published_at: str


class InjuryReport(BaseModel):
    """Latest official injury report from ``services/injuries.py::latest_injury_reports``."""
    model_config = ConfigDict(extra="forbid")
    source: str
    season: str
    week: int
    report_status: Optional[str] = None
    report_primary_injury: Optional[str] = None
    report_secondary_injury: Optional[str] = None
    practice_status: Optional[str] = None
    practice_primary_injury: Optional[str] = None


class DashboardPlayer(BaseModel):
    """Shape of ``_player_to_dashboard_dict`` + the stats/usage/research attach helpers."""
    model_config = ConfigDict(extra="forbid")
    id: int
    playerName: Optional[str] = None
    position: Optional[str] = None
    team: Optional[str] = None
    sleeper_player_id: Optional[str] = None
    full_name: Optional[str] = None
    last_updated: Optional[str] = None
    injury_status: Optional[str] = None
    injury_body_part: Optional[str] = None
    injury_notes: Optional[str] = None
    injury_start_date: Optional[str] = None
    practice_participation: Optional[str] = None
    practice_description: Optional[str] = None
    status: Optional[str] = None
    birth_date: Optional[str] = None
    height: Optional[str] = None
    weight: Optional[str] = None
    college: Optional[str] = None
    years_exp: Optional[int] = None
    number: Optional[int] = None
    depth_chart_order: Optional[int] = None
    depth_chart_position: Optional[str] = None
    fantasy_positions: Optional[List[str]] = None
    rookie_year: Optional[Union[int, str]] = None
    birth_city: Optional[str] = None
    birth_state: Optional[str] = None
    high_school: Optional[str] = None
    news_updated: Optional[int] = None
    ktc: KtcPlayerBlock
    values: ValuesBlock
    stats: Optional[SeasonStats] = None
    stats_prev: Optional[SeasonStats] = None
    usage: Optional[UsageBlock] = None
    research_latest: Optional[ResearchLatest] = None
    news: List[NewsItem] = []
    injury_report: Optional[InjuryReport] = None


class OwnershipEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    owned: Optional[float] = None
    started: Optional[float] = None


class ResearchMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")
    season: str
    week: Optional[int] = None
    league_type: int
    last_updated: Optional[str] = None


class DashboardPick(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pick_id: str
    season: str
    round: int
    original_roster_id: int
    slot_bucket: str
    ktc_value: Optional[float] = None
    values: ValuesBlock


class LeagueInfo(BaseModel):
    model_config = ConfigDict(extra="allow")
    league_id: str
    name: Optional[str] = None
    season: Optional[str] = None
    status: Optional[str] = None
    roster_positions: Optional[List[str]] = None
    scoring_settings: Optional[Dict[str, Any]] = None
    league_settings: Optional[Dict[str, Any]] = None


class RosterInfo(BaseModel):
    model_config = ConfigDict(extra="allow")
    roster_id: int
    owner_id: Optional[str] = None
    players: List[str] = []
    starters: List[str] = []
    settings: Dict[str, Any] = {}


class UserInfo(BaseModel):
    model_config = ConfigDict(extra="allow")
    user_id: str
    display_name: Optional[str] = None


class DataSource(BaseModel):
    """Attribution entry from ``services/data_sources.py::data_sources_for_bundle``."""
    model_config = ConfigDict(extra="forbid")
    key: str
    display_name: str
    url: str
    kind: str
    license_note: str
    last_synced_at: Optional[str] = None


class DashboardLeagueBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")
    league: Optional[LeagueInfo] = None
    rosters: List[RosterInfo]
    users: List[UserInfo]
    players: List[DashboardPlayer]
    ownership: Dict[str, OwnershipEntry]
    researchMeta: ResearchMeta
    ktcLastUpdated: Optional[str] = None
    picks_by_roster: Dict[str, List[DashboardPick]]
    bundleSeason: str
    data_sources: List[DataSource]


class DashboardLeagueResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["success"]
    data: DashboardLeagueBundle


class PlayersAllResponse(BaseModel):
    """Flat envelope — deliberately NOT the ``{status, data}`` wrapper."""
    model_config = ConfigDict(extra="forbid")
    status: Literal["success"]
    timestamp: str
    league_format: Literal["1qb", "superflex"]
    is_redraft: bool
    tep_level: Literal["", "tep", "tepp", "teppp"]
    count: int
    players: List[DashboardPlayer]
    data_sources: List[DataSource]
    researchMeta: Optional[ResearchMeta] = None
