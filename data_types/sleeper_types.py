from typing import Dict, List, Optional, Any
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
    # This is the normalized name for matching
    search_full_name: Optional[str] = None
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

