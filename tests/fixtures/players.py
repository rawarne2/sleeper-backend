"""
Player test fixtures and sample data.
"""
import pytest
import json
from models import Player as PlayerModel, db


@pytest.fixture
def sample_player_data():
    """Sample player data for testing."""
    return {
        'player_name': 'Josh Allen',
        'sleeper_player_id': '4881',
        'full_name': 'Josh Allen',
        'position': 'QB',
        'team': 'BUF',
        'height': '6\'5"',
        'weight': '237',
        'college': 'Wyoming',
        'years_exp': 6,
        'number': 17,
        'depth_chart_order': 1,
        'depth_chart_position': 'QB',
        'fantasy_positions': json.dumps(['QB']),
        'hashtag': '#JoshAllen',
        'search_rank': 1,
        'high_school': 'Reedley High School',
        'rookie_year': 2018,
        'injury_status': None,
        'injury_start_date': None,
        'competitions': None,
        'practice_participation': None,
        'practice_description': None,
        'status': 'Active',
        'age': 28,
        'sport': 'nfl',
        'player_metadata': json.dumps({'some': 'metadata'})
    }


@pytest.fixture
def sample_player(client, sample_player_data):
    """Create a sample player in the database."""
    player = PlayerModel(**sample_player_data)
    db.session.add(player)
    db.session.commit()
    return player


@pytest.fixture
def sample_ktc_player_data():
    """Sample KTC player data for testing."""
    return {
        'playerName': 'Josh Allen',
        'position': 'QB',
        'team': 'BUF',
        'ktc': {
            'superflexValues': {
                'value': 9500,
                'rank': 1,
                'positionalRank': 1,
                'overallTier': 'Tier 1',
                'positionalTier': 'Tier 1',
                'tep': {'value': 9600, 'rank': 1, 'positionalRank': 1},
                'tepp': {'value': 9700, 'rank': 1, 'positionalRank': 1},
                'teppp': {'value': 9800, 'rank': 1, 'positionalRank': 1}
            },
            'oneQBValues': {
                'value': 8500,
                'rank': 5,
                'positionalRank': 3,
                'overallTier': 'Tier 2',
                'positionalTier': 'Tier 1',
                'tep': {'value': 8600, 'rank': 5, 'positionalRank': 3},
                'tepp': {'value': 8700, 'rank': 5, 'positionalRank': 3},
                'teppp': {'value': 8800, 'rank': 5, 'positionalRank': 3}
            }
        }
    }
