"""Merged KTC + Sleeper dataclasses."""
from typing import Optional
from dataclasses import dataclass
from datetime import date

from data_types.ktc_types import KTCValuesData


@dataclass
class MergedPlayerData:
    """
    Type definition for merged player data (KTC + Sleeper).

    This represents the final merged data structure that combines
    both KTC and Sleeper data for database storage.
    """
    # Core identification (prefer Sleeper's normalized names)
    player_name: str  # From Sleeper full_name or KTC playerName
    position: str
    team: Optional[str] = None

    # Age (prefer KTC's more precise age)
    age: Optional[float] = None  # KTC age with decimals
    rookie: Optional[str] = None  # From KTC

    # Sleeper data
    sleeper_player_id: Optional[str] = None
    search_full_name: Optional[str] = None  # Key field for matching
    birth_date: Optional[date] = None
    height: Optional[str] = None
    weight: Optional[str] = None
    college: Optional[str] = None
    years_exp: Optional[int] = None
    number: Optional[int] = None
    depth_chart_order: Optional[int] = None
    depth_chart_position: Optional[str] = None
    fantasy_positions: Optional[str] = None
    hashtag: Optional[str] = None
    search_rank: Optional[int] = None
    high_school: Optional[str] = None
    rookie_year: Optional[int] = None
    injury_status: Optional[str] = None
    injury_start_date: Optional[date] = None
    full_name: Optional[str] = None
    status: Optional[str] = None
    player_metadata: Optional[str] = None

    # Additional Sleeper fields
    competitions: Optional[str] = None
    injury_body_part: Optional[str] = None
    injury_notes: Optional[str] = None
    team_changed_at: Optional[str] = None
    practice_participation: Optional[str] = None
    search_first_name: Optional[str] = None
    birth_state: Optional[str] = None
    oddsjam_id: Optional[str] = None
    practice_description: Optional[str] = None
    opta_id: Optional[str] = None
    espn_id: Optional[str] = None
    team_abbr: Optional[str] = None
    search_last_name: Optional[str] = None
    sportradar_id: Optional[str] = None
    swish_id: Optional[int] = None
    birth_country: Optional[str] = None
    gsis_id: Optional[str] = None
    pandascore_id: Optional[str] = None
    yahoo_id: Optional[str] = None
    fantasy_data_id: Optional[str] = None
    stats_id: Optional[str] = None
    news_updated: Optional[int] = None
    birth_city: Optional[str] = None
    rotoworld_id: Optional[str] = None
    rotowire_id: Optional[int] = None

    # KTC data
    ktc_player_id: Optional[int] = None
    slug: Optional[str] = None
    positionID: Optional[int] = None
    seasonsExperience: Optional[int] = None
    pickRound: Optional[int] = None
    pickNum: Optional[int] = None
    isFeatured: Optional[bool] = None
    isStartSitFeatured: Optional[bool] = None
    isTrending: Optional[bool] = None
    isDevyReturningToSchool: Optional[bool] = None
    isDevyYearDecrement: Optional[bool] = None
    teamLongName: Optional[str] = None
    draftYear: Optional[int] = None
    byeWeek: Optional[int] = None
    injury: Optional[str] = None

    # KTC values
    oneqb_values: Optional[KTCValuesData] = None
    superflex_values: Optional[KTCValuesData] = None
