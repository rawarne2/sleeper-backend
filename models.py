import json
from datetime import datetime, UTC
from typing import Dict, Any
from flask_sqlalchemy import SQLAlchemy

from utils import (PLAYER_NAME_KEY, POSITION_KEY, TEAM_KEY, VALUE_KEY, AGE_KEY,
                   ROOKIE_KEY, RANK_KEY, TREND_KEY, TIER_KEY, POSITION_RANK_KEY)

# This will be initialized from app.py
db = SQLAlchemy()


class KTCPlayer(db.Model):
    """
    SQLAlchemy model for KTC player data with Sleeper API integration.

    Stores player rankings and values for different league formats,
    including dynasty and redraft rankings with TEP variations,
    plus additional player data from Sleeper API.
    """
    # Primary key
    id = db.Column(db.Integer, primary_key=True)

    # Player identification
    player_name = db.Column(db.String(100), nullable=False)
    position = db.Column(db.String(10), nullable=False)
    team = db.Column(db.String(10))

    # Player metrics
    value = db.Column(db.Integer)
    age = db.Column(db.Float)
    rookie = db.Column(db.String(5))
    rank = db.Column(db.Integer)
    trend = db.Column(db.String(10))
    tier = db.Column(db.String(10))
    position_rank = db.Column(db.String(10))

    # Configuration
    league_format = db.Column(db.String(10), nullable=False)
    is_redraft = db.Column(db.Boolean, nullable=False)
    tep = db.Column(db.String(10))

    # Sleeper API data
    sleeper_id = db.Column(db.String(20))
    birth_date = db.Column(db.Date)
    height = db.Column(db.String(10))
    weight = db.Column(db.String(10))
    college = db.Column(db.String(100))
    years_exp = db.Column(db.Integer)
    jersey_number = db.Column(db.Integer)
    depth_chart_order = db.Column(db.Integer)
    depth_chart_position = db.Column(db.String(10))
    fantasy_positions = db.Column(db.Text)  # JSON string of fantasy positions
    hashtag = db.Column(db.String(100))
    search_rank = db.Column(db.Integer)
    high_school = db.Column(db.String(200))
    rookie_year = db.Column(db.Integer)

    # Injury data from Sleeper API
    injury_status = db.Column(db.String(50))
    injury_start_date = db.Column(db.Date)

    # Metadata
    last_updated = db.Column(db.DateTime, nullable=False,
                             default=lambda: datetime.now(UTC))

    def to_dict(self) -> Dict[str, Any]:
        """Convert player object to dictionary for API responses."""
        base_dict = {
            'id': self.id,
            RANK_KEY: self.rank,
            VALUE_KEY: self.value,
            PLAYER_NAME_KEY: self.player_name,
            POSITION_RANK_KEY: self.position_rank,
            POSITION_KEY: self.position,
            TEAM_KEY: self.team,
            AGE_KEY: self.age,
            ROOKIE_KEY: self.rookie,
            TREND_KEY: self.trend,
            TIER_KEY: self.tier
        }

        # Add Sleeper data if available
        if self.sleeper_id:
            sleeper_data = {
                'sleeper_id': self.sleeper_id,
                'birth_date': self.birth_date.isoformat() if self.birth_date else None,
                'height': self.height,
                'weight': self.weight,
                'college': self.college,
                'years_exp': self.years_exp,
                'jersey_number': self.jersey_number,
                'depth_chart_order': self.depth_chart_order,
                'depth_chart_position': self.depth_chart_position,
                'fantasy_positions': json.loads(self.fantasy_positions) if self.fantasy_positions else None,
                'hashtag': self.hashtag,
                'search_rank': self.search_rank,
                'high_school': self.high_school,
                'rookie_year': self.rookie_year,
                'injury_status': self.injury_status,
                'injury_start_date': self.injury_start_date.isoformat() if self.injury_start_date else None
            }
            base_dict.update(sleeper_data)

        return base_dict


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
    sport = db.Column(db.String(10), default='nfl')

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
            'sport': self.sport,
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

    # User metadata
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
            'metadata': json.loads(self.user_metadata) if self.user_metadata else {},
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
