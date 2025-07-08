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
