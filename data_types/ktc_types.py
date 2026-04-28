"""KTC-shaped dataclasses."""
from typing import Dict, List, Optional, Any
from dataclasses import dataclass


@dataclass
class KTCPlayerData:
    """
    Type definition for KTC (Keep Trade Cut) player data.

    This represents the structure of player data coming from KTC website
    to prevent confusion with Sleeper data structures.
    """
    # Core identification (KTC field names)
    playerName: str  # KTC uses 'playerName'
    position: str
    team: str
    age: Optional[float] = None  # KTC age includes decimals (more precise)
    rookie: Optional[str] = None  # "Yes" or "No"

    # KTC specific IDs and metadata
    ktc_player_id: Optional[int] = None  # KTC playerID
    slug: Optional[str] = None
    positionID: Optional[int] = None

    # Physical attributes (KTC format)
    weight: Optional[str] = None  # KTC weight format

    # Career/draft info
    seasonsExperience: Optional[int] = None
    pickRound: Optional[int] = None
    pickNum: Optional[int] = None
    draftYear: Optional[int] = None

    # KTC flags and features
    isFeatured: Optional[bool] = None
    isStartSitFeatured: Optional[bool] = None
    isTrending: Optional[bool] = None
    isDevyReturningToSchool: Optional[bool] = None
    isDevyYearDecrement: Optional[bool] = None

    # Team info
    teamLongName: Optional[str] = None
    byeWeek: Optional[int] = None

    # Additional KTC fields
    ktc_number: Optional[int] = None  # KTC's number field
    injury: Optional[str] = None  # JSON string with injury data
    fantasy_positions: Optional[str] = None  # JSON string with fantasy positions

    # KTC values (these contain the ranking data)
    oneqb_values: Optional[Dict[str, Any]] = None
    superflex_values: Optional[Dict[str, Any]] = None


@dataclass
class KTCValuesData:
    """
    Type definition for KTC ranking values (oneQB or superflex).
    """
    # Base ranking values
    value: Optional[int] = None
    rank: Optional[int] = None
    positional_rank: Optional[int] = None
    overall_tier: Optional[int] = None
    positional_tier: Optional[int] = None

    # Trend data
    overall_trend: Optional[int] = None
    positional_trend: Optional[int] = None
    overall_7day_trend: Optional[int] = None
    positional_7day_trend: Optional[int] = None

    # Trading data
    start_sit_value: Optional[int] = None
    kept: Optional[int] = None
    traded: Optional[int] = None
    cut: Optional[int] = None
    diff: Optional[int] = None

    # Status flags
    is_out_this_week: Optional[bool] = None

    # Liquidity metrics
    raw_liquidity: Optional[float] = None
    std_liquidity: Optional[float] = None
    trade_count: Optional[int] = None

    # TEP values
    tep_value: Optional[int] = None
    tep_rank: Optional[int] = None
    tep_positional_rank: Optional[int] = None
    tep_overall_tier: Optional[int] = None
    tep_positional_tier: Optional[int] = None

    # TEPP values
    tepp_value: Optional[int] = None
    tepp_rank: Optional[int] = None
    tepp_positional_rank: Optional[int] = None
    tepp_overall_tier: Optional[int] = None
    tepp_positional_tier: Optional[int] = None

    # TEPPP values
    teppp_value: Optional[int] = None
    teppp_rank: Optional[int] = None
    teppp_positional_rank: Optional[int] = None
    teppp_overall_tier: Optional[int] = None
    teppp_positional_tier: Optional[int] = None
