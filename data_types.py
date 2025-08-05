"""
Data types and interfaces for Sleeper and KTC data to prevent confusion.
"""

from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass
from datetime import date


@dataclass
class SleeperPlayerData:
    """
    Type definition for Sleeper API player data.
    
    This represents the structure of player data coming from Sleeper API
    to prevent confusion with KTC data structures.
    """
    # Core identification
    sleeper_player_id: str
    full_name: str
    position: str
    team: Optional[str] = None
    
    # Normalized search fields (key for matching)
    search_full_name: Optional[str] = None  # This is the normalized name for matching
    search_first_name: Optional[str] = None
    search_last_name: Optional[str] = None
    
    # Physical attributes
    birth_date: Optional[str] = None  # ISO date string
    height: Optional[str] = None
    weight: Optional[str] = None
    age: Optional[int] = None  # Sleeper age is whole number
    
    # Career info
    college: Optional[str] = None
    years_exp: Optional[int] = None
    rookie_year: Optional[int] = None
    
    # Team/roster info
    number: Optional[int] = None
    depth_chart_order: Optional[int] = None
    depth_chart_position: Optional[str] = None
    team_abbr: Optional[str] = None
    
    # Fantasy data
    fantasy_positions: Optional[str] = None  # JSON string
    search_rank: Optional[int] = None
    
    # Injury/status info
    injury_status: Optional[str] = None
    injury_start_date: Optional[str] = None  # ISO date string
    injury_body_part: Optional[str] = None
    injury_notes: Optional[str] = None
    practice_participation: Optional[str] = None
    practice_description: Optional[str] = None
    status: Optional[str] = None
    
    # Additional metadata
    hashtag: Optional[str] = None
    high_school: Optional[str] = None
    player_metadata: Optional[str] = None  # JSON string
    
    # External IDs
    espn_id: Optional[str] = None
    yahoo_id: Optional[str] = None
    fantasy_data_id: Optional[str] = None
    stats_id: Optional[str] = None
    gsis_id: Optional[str] = None
    sportradar_id: Optional[str] = None
    rotowire_id: Optional[int] = None
    rotoworld_id: Optional[str] = None
    swish_id: Optional[int] = None
    oddsjam_id: Optional[str] = None
    opta_id: Optional[str] = None
    pandascore_id: Optional[str] = None
    
    # Location data
    birth_city: Optional[str] = None
    birth_state: Optional[str] = None
    birth_country: Optional[str] = None
    
    # Other fields
    competitions: Optional[str] = None  # JSON string
    team_changed_at: Optional[str] = None
    news_updated: Optional[int] = None


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
    heightFeet: Optional[int] = None
    heightInches: Optional[int] = None
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
    birthday: Optional[str] = None  # KTC timestamp format
    injury: Optional[str] = None  # JSON string with injury data
    
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
    heightFeet: Optional[int] = None
    heightInches: Optional[int] = None
    seasonsExperience: Optional[int] = None
    pickRound: Optional[int] = None
    pickNum: Optional[int] = None
    isFeatured: Optional[bool] = None
    isStartSitFeatured: Optional[bool] = None
    isTrending: Optional[bool] = None
    isDevyReturningToSchool: Optional[bool] = None
    isDevyYearDecrement: Optional[bool] = None
    teamLongName: Optional[str] = None
    birthday: Optional[str] = None
    draftYear: Optional[int] = None
    byeWeek: Optional[int] = None
    injury: Optional[str] = None
    
    # KTC values
    oneqb_values: Optional[KTCValuesData] = None
    superflex_values: Optional[KTCValuesData] = None

def normalize_name_for_matching(name: str) -> str:
    """
    Normalize a player name for matching purposes.
    
    This function mimics Sleeper's search_full_name normalization:
    - Convert to lowercase
    - Remove spaces
    - Remove special characters like apostrophes, periods, etc.
    - Handle Unicode escape sequences like \u0027 (apostrophe)
    
    Args:
        name: Player name to normalize
        
    Returns:
        Normalized name string
    """
    if not name:
        return ''
    
    # First, decode any Unicode escape sequences (like \u0027 for apostrophe)
    try:
        # Handle Unicode escape sequences in the string
        normalized = name.encode().decode('unicode_escape')
    except (UnicodeDecodeError, UnicodeEncodeError):
        # If there's an issue with Unicode decoding, use the original string
        normalized = name
    
    # Convert to lowercase
    normalized = normalized.lower()
    
    # Remove common special characters and spaces
    # This includes regular apostrophes, Unicode apostrophes, and other punctuation
    chars_to_remove = [
        ' ', "'", '"', '.', '-', '_', 
        'jr', 'sr', 'ii', 'iii', 'iv',
        ''', ''',  # Unicode left and right single quotes
        '"', '"',  # Unicode left and right double quotes
        '`',       # Backtick
        '´',       # Acute accent
        '′',       # Prime symbol (sometimes used as apostrophe)
        "'"        # Apostrophe
    ]
    
    for char in chars_to_remove:
        normalized = normalized.replace(char, '')
    
    # Also remove any remaining non-alphanumeric characters except spaces
    # This catches any other Unicode punctuation we might have missed
    import re
    normalized = re.sub(r'[^\w\s]', '', normalized)
    
    # Remove any remaining spaces
    normalized = normalized.replace(' ', '')
    
    return normalized
