import json
from datetime import datetime, UTC
from typing import Dict, Any
from flask_sqlalchemy import SQLAlchemy

from utils import (PLAYER_NAME_KEY, POSITION_KEY,
                   TEAM_KEY, AGE_KEY, ROOKIE_KEY)

# This will be initialized in app.py
db = SQLAlchemy()


class Player(db.Model):
    """
    SQLAlchemy model for KTC player data with Sleeper API integration.

    Stores player rankings and values for different league formats,
    including dynasty and redraft rankings with TEP variations,
    plus additional player data from Sleeper API.
    """
    __tablename__ = 'players'

    # Primary key
    id = db.Column(db.Integer, primary_key=True)

    # Player identification
    player_name = db.Column(db.String(100), nullable=False)
    position = db.Column(db.String(10), nullable=False)
    team = db.Column(db.String(10))
    match_key = db.Column(db.String(150), index=True)  # normalized_name-position for efficient matching

    # KTC data
    ktc_player_id = db.Column(db.Integer)  # KTC playerID field
    age = db.Column(db.Float)
    rookie = db.Column(db.String(5))  # Yes or No

    # Sleeper API data
    sleeper_player_id = db.Column(db.String(20))
    birth_date = db.Column(db.Date)
    height = db.Column(db.String(10))
    weight = db.Column(db.String(10))
    college = db.Column(db.String(100))
    years_exp = db.Column(db.Integer)
    number = db.Column(db.Integer)
    depth_chart_order = db.Column(db.Integer)
    depth_chart_position = db.Column(db.String(10))
    fantasy_positions = db.Column(db.Text)
    hashtag = db.Column(db.String(100))
    search_rank = db.Column(db.Integer)
    high_school = db.Column(db.String(200))
    rookie_year = db.Column(db.Integer)
    injury_status = db.Column(db.String(50))
    injury_start_date = db.Column(db.Date)
    # active = db.Column(db.Boolean) redundant. All saved players are active
    sport = db.Column(db.String(10))
    player_metadata = db.Column(db.Text)  # JSON string for additional metadata

    # Additional Sleeper API fields
    competitions = db.Column(db.Text)  # array of unknown values. currently empty but may have values during season?
    injury_body_part = db.Column(db.String(50))
    injury_notes = db.Column(db.Text)
    team_changed_at = db.Column(db.DateTime)
    practice_participation = db.Column(db.String(50))
    search_first_name = db.Column(db.String(100))
    birth_state = db.Column(db.String(50))
    oddsjam_id = db.Column(db.String(50))
    practice_description = db.Column(db.String(200))
    opta_id = db.Column(db.String(50))
    search_full_name = db.Column(db.String(100))
    espn_id = db.Column(db.String(50))
    team_abbr = db.Column(db.String(10))
    search_last_name = db.Column(db.String(100))
    sportradar_id = db.Column(db.String(100))
    swish_id = db.Column(db.Integer)
    birth_country = db.Column(db.String(50))
    gsis_id = db.Column(db.String(50))
    pandascore_id = db.Column(db.String(50))
    yahoo_id = db.Column(db.String(50))
    fantasy_data_id = db.Column(db.String(50))
    stats_id = db.Column(db.String(50))
    news_updated = db.Column(db.BigInteger)
    birth_city = db.Column(db.String(100))
    rotoworld_id = db.Column(db.String(50))
    rotowire_id = db.Column(db.Integer)
    # first_name = db.Column(db.String(100))  # removed - using player_name and full_name for merging
    # last_name = db.Column(db.String(100))   # removed - using player_name and full_name for merging
    full_name = db.Column(db.String(100))
    status = db.Column(db.String(50))

    # Additional KTC fields
    slug = db.Column(db.String(100))
    positionID = db.Column(db.Integer)
    heightFeet = db.Column(db.Integer)
    heightInches = db.Column(db.Integer)
    seasonsExperience = db.Column(db.Integer)
    pickRound = db.Column(db.Integer)
    pickNum = db.Column(db.Integer)
    isFeatured = db.Column(db.Boolean)
    isStartSitFeatured = db.Column(db.Boolean)
    isTrending = db.Column(db.Boolean)
    isDevyReturningToSchool = db.Column(db.Boolean)
    isDevyYearDecrement = db.Column(db.Boolean)
    teamLongName = db.Column(db.String(100))
    birthday = db.Column(db.String(20))  # timestamp format
    draftYear = db.Column(db.Integer)
    byeWeek = db.Column(db.Integer)
    injury = db.Column(db.Text)  # JSON string with injuryCode

    # Metadata
    last_updated = db.Column(db.DateTime, nullable=False,
                             default=lambda: datetime.now(UTC))

    # Relationships
    oneqb_values = db.relationship(
        'PlayerKTCOneQBValues', backref='player', lazy=True, cascade='all, delete-orphan', uselist=False)
    superflex_values = db.relationship(
        'PlayerKTCSuperflexValues', backref='player', lazy=True, cascade='all, delete-orphan', uselist=False)

    def to_dict(self) -> Dict[str, Any]:
        """Convert player object to dictionary for API responses."""
        # Sleeper-based app: Sleeper fields at top level
        result = {
            'id': self.id,
            # Primary player information (from Sleeper)
            PLAYER_NAME_KEY: self.player_name,
            POSITION_KEY: self.position,
            TEAM_KEY: self.team,
            'sleeper_player_id': self.sleeper_player_id,
            'birth_date': self.birth_date.isoformat() if self.birth_date else None,
            'height': self.height,
            'weight': self.weight,
            'college': self.college,
            'years_exp': self.years_exp,
            'number': self.number,
            'depth_chart_order': self.depth_chart_order,
            'depth_chart_position': self.depth_chart_position,
            'fantasy_positions': self._safe_json_loads(self.fantasy_positions),
            'search_rank': self.search_rank,
            'high_school': self.high_school,
            'rookie_year': self.rookie_year,
            'hashtag': self.hashtag,
            'injury_status': self.injury_status,
            'injury_start_date': self.injury_start_date.isoformat() if self.injury_start_date else None,
            'player_metadata': self._safe_json_loads(self.player_metadata),
            # Additional Sleeper fields
            'competitions': self._safe_json_loads(self.competitions),
            'injury_body_part': self.injury_body_part,
            'injury_notes': self.injury_notes,
            'team_changed_at': self.team_changed_at.isoformat() if self.team_changed_at else None,
            'practice_participation': self.practice_participation,
            'search_first_name': self.search_first_name,
            'birth_state': self.birth_state,
            'oddsjam_id': self.oddsjam_id,
            'practice_description': self.practice_description,
            'opta_id': self.opta_id,
            'search_full_name': self.search_full_name,
            'espn_id': self.espn_id,
            'team_abbr': self.team_abbr,
            'search_last_name': self.search_last_name,
            'sportradar_id': self.sportradar_id,
            'swish_id': self.swish_id,
            'birth_country': self.birth_country,
            'gsis_id': self.gsis_id,
            'pandascore_id': self.pandascore_id,
            'yahoo_id': self.yahoo_id,
            'fantasy_data_id': self.fantasy_data_id,
            'stats_id': self.stats_id,
            'news_updated': self.news_updated,
            'birth_city': self.birth_city,
            'rotoworld_id': self.rotoworld_id,
            'rotowire_id': self.rotowire_id,
            'full_name': self.full_name,
            'status': self.status,
            'last_updated': self.last_updated.isoformat() if self.last_updated else None
        }

        # KTC data nested in ktc object
        ktc_data = {
            'ktc_player_id': self.ktc_player_id,
            AGE_KEY: self.age,
            ROOKIE_KEY: self.rookie,
            # Additional KTC fields
            'slug': self.slug,
            'positionID': self.positionID,
            'heightFeet': self.heightFeet,
            'heightInches': self.heightInches,
            'seasonsExperience': self.seasonsExperience,
            'pickRound': self.pickRound,
            'pickNum': self.pickNum,
            'isFeatured': self.isFeatured,
            'isStartSitFeatured': self.isStartSitFeatured,
            'isTrending': self.isTrending,
            'isDevyReturningToSchool': self.isDevyReturningToSchool,
            'isDevyYearDecrement': self.isDevyYearDecrement,
            'teamLongName': self.teamLongName,
            'birthday': self.birthday,
            'draftYear': self.draftYear,
            'byeWeek': self.byeWeek,
            'injury': self._safe_json_loads(self.injury),
            # OneQB Values
            'oneQBValues': self.oneqb_values.to_dict() if self.oneqb_values else None,
            # Superflex Values
            'superflexValues': self.superflex_values.to_dict() if self.superflex_values else None
        }

        # Add KTC data as nested object
        result['ktc'] = ktc_data

        return result

    def _safe_json_loads(self, json_str):
        """Safely load JSON string, returning None if parsing fails."""
        if not json_str:
            return None
        try:
            return json.loads(json_str)
        except (json.JSONDecodeError, TypeError) as e:
            # Log the error but don't break the entire response
            print(f"JSON parsing error for player {self.player_name}: {e}")
            return None


class SleeperLeague(db.Model):
    """
    SQLAlchemy model for Sleeper league data.

    Stores basic league information and metadata.
    """
    __tablename__ = 'sleeper_leagues'

    # Primary key
    id = db.Column(db.Integer, primary_key=True)

    # League identification
    league_id = db.Column(db.String(20), nullable=False,
                          unique=True, index=True)
    name = db.Column(db.String(200))
    season = db.Column(db.String(4))
    # sport = db.Column(db.String(10), default='nfl')

    # League configuration
    total_rosters = db.Column(db.Integer)
    roster_positions = db.Column(db.Text)  # JSON string
    scoring_settings = db.Column(db.Text)  # JSON string
    league_settings = db.Column(db.Text)  # JSON string

    # League status
    status = db.Column(db.String(20))
    draft_id = db.Column(db.String(20))
    avatar = db.Column(db.String(100))

    # Metadata
    last_updated = db.Column(db.DateTime, nullable=False,
                             default=lambda: datetime.now(UTC))
    last_refreshed = db.Column(db.DateTime)

    # Relationships
    rosters = db.relationship(
        'SleeperRoster', backref='league', lazy=True, cascade='all, delete-orphan')
    users = db.relationship('SleeperUser', backref='league',
                            lazy=True, cascade='all, delete-orphan')

    def to_dict(self) -> Dict[str, Any]:
        """Convert league object to dictionary for API responses."""
        return {
            'id': self.id,
            'league_id': self.league_id,
            'name': self.name,
            'season': self.season,
            'total_rosters': self.total_rosters,
            'roster_positions': json.loads(self.roster_positions) if self.roster_positions else None,
            'scoring_settings': json.loads(self.scoring_settings) if self.scoring_settings else None,
            'league_settings': json.loads(self.league_settings) if self.league_settings else None,
            'status': self.status,
            'draft_id': self.draft_id,
            'avatar': self.avatar,
            'last_updated': self.last_updated.isoformat() if self.last_updated else None,
            'last_refreshed': self.last_refreshed.isoformat() if self.last_refreshed else None
        }


class SleeperRoster(db.Model):
    """
    SQLAlchemy model for Sleeper roster data.

    Stores roster information for each team in a league.
    """
    __tablename__ = 'sleeper_rosters'

    # Primary key
    id = db.Column(db.Integer, primary_key=True)

    # Foreign key to league
    league_id = db.Column(db.String(20), db.ForeignKey(
        'sleeper_leagues.league_id'), nullable=False, index=True)

    # Roster identification
    roster_id = db.Column(db.Integer, nullable=False)
    owner_id = db.Column(db.String(20))

    # Roster data
    players = db.Column(db.Text)  # JSON string of player IDs
    starters = db.Column(db.Text)  # JSON string of starter player IDs
    reserve = db.Column(db.Text)  # JSON string of reserve player IDs
    taxi = db.Column(db.Text)  # JSON string of taxi squad player IDs

    # Roster settings
    settings = db.Column(db.Text)  # JSON string of roster settings

    # Metadata
    last_updated = db.Column(db.DateTime, nullable=False,
                             default=lambda: datetime.now(UTC))

    # Unique constraint for league_id + roster_id
    __table_args__ = (db.UniqueConstraint(
        'league_id', 'roster_id', name='_league_roster_uc'),)

    def to_dict(self) -> Dict[str, Any]:
        """Convert roster object to dictionary for API responses."""
        return {
            'id': self.id,
            'league_id': self.league_id,
            'roster_id': self.roster_id,
            'owner_id': self.owner_id,
            'players': json.loads(self.players) if self.players else [],
            'starters': json.loads(self.starters) if self.starters else [],
            'reserve': json.loads(self.reserve) if self.reserve else [],
            'taxi': json.loads(self.taxi) if self.taxi else [],
            'settings': json.loads(self.settings) if self.settings else {},
            'last_updated': self.last_updated.isoformat() if self.last_updated else None
        }


class SleeperUser(db.Model):
    """
    SQLAlchemy model for Sleeper user data.

    Stores user information for league participants.
    """
    __tablename__ = 'sleeper_users'

    # Primary key
    id = db.Column(db.Integer, primary_key=True)

    # Foreign key to league
    league_id = db.Column(db.String(20), db.ForeignKey(
        'sleeper_leagues.league_id'), nullable=False, index=True)

    # User identification
    user_id = db.Column(db.String(20), nullable=False)
    username = db.Column(db.String(100))
    display_name = db.Column(db.String(100))

    # User profile
    avatar = db.Column(db.String(100))
    team_name = db.Column(db.String(100))
    user_metadata = db.Column(db.Text)  # JSON string for additional user data

    # Metadata
    last_updated = db.Column(db.DateTime, nullable=False,
                             default=lambda: datetime.now(UTC))

    # Unique constraint for league_id + user_id
    __table_args__ = (db.UniqueConstraint(
        'league_id', 'user_id', name='_league_user_uc'),)

    def to_dict(self) -> Dict[str, Any]:
        """Convert user object to dictionary for API responses."""
        return {
            'id': self.id,
            'league_id': self.league_id,
            'user_id': self.user_id,
            'username': self.username,
            'display_name': self.display_name,
            'avatar': self.avatar,
            'team_name': self.team_name,
            'user_metadata': json.loads(self.user_metadata) if self.user_metadata else {},
            'last_updated': self.last_updated.isoformat() if self.last_updated else None
        }


class SleeperResearch(db.Model):
    """
    SQLAlchemy model for Sleeper player research data.

    Stores player research and rankings data from Sleeper's research endpoint.
    """
    __tablename__ = 'sleeper_research'

    # Primary key
    id = db.Column(db.Integer, primary_key=True)

    # Research identification
    season = db.Column(db.String(4), nullable=False, index=True)
    week = db.Column(db.Integer, nullable=False, default=1)
    league_type = db.Column(db.Integer, nullable=False,
                            default=2)  # 2 for dynasty

    # Player identification
    player_id = db.Column(db.String(20), nullable=False, index=True)

    # Research data
    research_data = db.Column(db.Text)  # JSON string of research metrics

    # Metadata
    last_updated = db.Column(db.DateTime, nullable=False,
                             default=lambda: datetime.now(UTC))

    # Unique constraint for season + week + league_type + player_id
    __table_args__ = (db.UniqueConstraint('season', 'week',
                      'league_type', 'player_id', name='_research_unique_uc'),)

    def to_dict(self) -> Dict[str, Any]:
        """Convert research object to dictionary for API responses."""
        return {
            'id': self.id,
            'season': self.season,
            'week': self.week,
            'league_type': self.league_type,
            'player_id': self.player_id,
            'research_data': json.loads(self.research_data) if self.research_data else {},
            'last_updated': self.last_updated.isoformat() if self.last_updated else None
        }


class PlayerKTCOneQBValues(db.Model):
    """KTC OneQB values for a player."""
    __tablename__ = 'player_ktc_oneqb_values'
    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey(
        'players.id'), nullable=False)

    # Base values
    value = db.Column(db.Integer)
    rank = db.Column(db.Integer)
    positional_rank = db.Column(db.Integer)
    overall_tier = db.Column(db.Integer)
    positional_tier = db.Column(db.Integer)
    overall_trend = db.Column(db.Integer)
    positional_trend = db.Column(db.Integer)
    overall_7day_trend = db.Column(db.Integer)
    positional_7day_trend = db.Column(db.Integer)
    start_sit_value = db.Column(db.Integer)
    kept = db.Column(db.Integer)
    traded = db.Column(db.Integer)
    cut = db.Column(db.Integer)
    diff = db.Column(db.Integer)
    is_out_this_week = db.Column(db.Boolean)
    raw_liquidity = db.Column(db.Float)
    std_liquidity = db.Column(db.Float)
    trade_count = db.Column(db.Integer)

    # TEP values
    tep_value = db.Column(db.Integer)
    tep_rank = db.Column(db.Integer)
    tep_positional_rank = db.Column(db.Integer)
    tep_overall_tier = db.Column(db.Integer)
    tep_positional_tier = db.Column(db.Integer)

    tepp_value = db.Column(db.Integer)
    tepp_rank = db.Column(db.Integer)
    tepp_positional_rank = db.Column(db.Integer)
    tepp_overall_tier = db.Column(db.Integer)
    tepp_positional_tier = db.Column(db.Integer)

    teppp_value = db.Column(db.Integer)
    teppp_rank = db.Column(db.Integer)
    teppp_positional_rank = db.Column(db.Integer)
    teppp_overall_tier = db.Column(db.Integer)
    teppp_positional_tier = db.Column(db.Integer)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to KTC oneQBValues format."""
        return {
            'value': self.value,
            'rank': self.rank,
            'positionalRank': self.positional_rank,
            'overallTier': self.overall_tier,
            'positionalTier': self.positional_tier,
            'overallTrend': self.overall_trend,
            'positionalTrend': self.positional_trend,
            'overall7DayTrend': self.overall_7day_trend,
            'positional7DayTrend': self.positional_7day_trend,
            'startSitValue': self.start_sit_value,
            'kept': self.kept,
            'traded': self.traded,
            'cut': self.cut,
            'diff': self.diff,
            'isOutThisWeek': self.is_out_this_week,
            'rawLiquidity': self.raw_liquidity,
            'stdLiquidity': self.std_liquidity,
            'tradeCount': self.trade_count,
            'tep': {
                'value': self.tep_value,
                'rank': self.tep_rank,
                'positionalRank': self.tep_positional_rank,
                'overallTier': self.tep_overall_tier,
                'positionalTier': self.tep_positional_tier
            },
            'tepp': {
                'value': self.tepp_value,
                'rank': self.tepp_rank,
                'positionalRank': self.tepp_positional_rank,
                'overallTier': self.tepp_overall_tier,
                'positionalTier': self.tepp_positional_tier
            },
            'teppp': {
                'value': self.teppp_value,
                'rank': self.teppp_rank,
                'positionalRank': self.teppp_positional_rank,
                'overallTier': self.teppp_overall_tier,
                'positionalTier': self.teppp_positional_tier
            }
        }


class PlayerKTCSuperflexValues(db.Model):
    """KTC Superflex values for a player."""
    __tablename__ = 'player_ktc_superflex_values'
    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey(
        'players.id'), nullable=False)

    # Base values
    value = db.Column(db.Integer)
    rank = db.Column(db.Integer)
    positional_rank = db.Column(db.Integer)
    overall_tier = db.Column(db.Integer)
    positional_tier = db.Column(db.Integer)
    overall_trend = db.Column(db.Integer)
    positional_trend = db.Column(db.Integer)
    overall_7day_trend = db.Column(db.Integer)
    positional_7day_trend = db.Column(db.Integer)
    start_sit_value = db.Column(db.Integer)
    kept = db.Column(db.Integer)
    traded = db.Column(db.Integer)
    cut = db.Column(db.Integer)
    diff = db.Column(db.Integer)
    is_out_this_week = db.Column(db.Boolean)
    raw_liquidity = db.Column(db.Float)
    std_liquidity = db.Column(db.Float)
    trade_count = db.Column(db.Integer)

    # TEP values
    tep_value = db.Column(db.Integer)
    tep_rank = db.Column(db.Integer)
    tep_positional_rank = db.Column(db.Integer)
    tep_overall_tier = db.Column(db.Integer)
    tep_positional_tier = db.Column(db.Integer)

    tepp_value = db.Column(db.Integer)
    tepp_rank = db.Column(db.Integer)
    tepp_positional_rank = db.Column(db.Integer)
    tepp_overall_tier = db.Column(db.Integer)
    tepp_positional_tier = db.Column(db.Integer)

    teppp_value = db.Column(db.Integer)
    teppp_rank = db.Column(db.Integer)
    teppp_positional_rank = db.Column(db.Integer)
    teppp_overall_tier = db.Column(db.Integer)
    teppp_positional_tier = db.Column(db.Integer)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to KTC superflexValues format."""
        return {
            'value': self.value,
            'rank': self.rank,
            'positionalRank': self.positional_rank,
            'overallTier': self.overall_tier,
            'positionalTier': self.positional_tier,
            'overallTrend': self.overall_trend,
            'positionalTrend': self.positional_trend,
            'overall7DayTrend': self.overall_7day_trend,
            'positional7DayTrend': self.positional_7day_trend,
            'startSitValue': self.start_sit_value,
            'kept': self.kept,
            'traded': self.traded,
            'cut': self.cut,
            'diff': self.diff,
            'isOutThisWeek': self.is_out_this_week,
            'rawLiquidity': self.raw_liquidity,
            'stdLiquidity': self.std_liquidity,
            'tradeCount': self.trade_count,
            'tep': {
                'value': self.tep_value,
                'rank': self.tep_rank,
                'positionalRank': self.tep_positional_rank,
                'overallTier': self.tep_overall_tier,
                'positionalTier': self.tep_positional_tier
            },
            'tepp': {
                'value': self.tepp_value,
                'rank': self.tepp_rank,
                'positionalRank': self.tepp_positional_rank,
                'overallTier': self.tepp_overall_tier,
                'positionalTier': self.tepp_positional_tier
            },
            'teppp': {
                'value': self.teppp_value,
                'rank': self.teppp_rank,
                'positionalRank': self.teppp_positional_rank,
                'overallTier': self.teppp_overall_tier,
                'positionalTier': self.teppp_positional_tier
            }
        }
