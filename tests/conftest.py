"""
Pytest configuration and shared fixtures.

This file provides shared fixtures and configuration for all test modules.
"""
import os

os.environ.setdefault('TEST_DATABASE_URI', 'sqlite:///:memory:')
from tests.fixtures.players import sample_player_data, sample_player, sample_ktc_player_data
from tests.fixtures.database import client, app_context
from models.extensions import db
from models.entities import Player as PlayerModel
from app import app
import pytest
import json
from datetime import datetime, UTC

# Import fixtures to make them available to all tests


@pytest.fixture(scope="session")
def test_app():
    """Create application for the tests."""
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    return app


@pytest.fixture
def mock_sleeper_players():
    """Mock Sleeper player data for testing."""
    return [
        {
            'sleeper_player_id': '4881',
            'full_name': 'Josh Allen',
            'position': 'QB',
            'team': 'BUF',
            'birth_date': '1996-05-21',
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
            'rookie_year': 2018,
            'status': 'Active',
            'player_metadata': json.dumps({'test': 'data'})
        },
        {
            'sleeper_player_id': '4035',
            'full_name': 'Christian McCaffrey',
            'position': 'RB',
            'team': 'SF',
            'birth_date': '1996-06-07',
            'height': '5\'11"',
            'weight': '205',
            'college': 'Stanford',
            'years_exp': 7,
            'number': 23,
            'depth_chart_order': 1,
            'depth_chart_position': 'RB',
            'fantasy_positions': json.dumps(['RB']),
            'hashtag': '#ChristianMcCaffrey',
            'search_rank': 2,
            'rookie_year': 2017,
            'status': 'Active',
            'player_metadata': json.dumps({'test': 'data'})
        }
    ]


@pytest.fixture
def mock_league_data():
    """Mock league data for testing."""
    return {
        'success': True,
        'league': {
            'league_id': '1210364682523656192',
            'name': 'Test Fantasy League',
            'season': '2024',
            'status': 'in_season',
            'total_rosters': 12,
            'scoring_settings': {
                'pass_yd': 0.04,
                'pass_td': 4,
                'rush_yd': 0.1,
                'rush_td': 6,
                'rec_yd': 0.1,
                'rec_td': 6,
                'rec': 0.5
            }
        },
        'rosters': [
            {
                'roster_id': 1,
                'owner_id': '736083244801474560',
                'players': ['4881', '4035'],
                'starters': ['4881'],
                'settings': {
                    'wins': 10,
                    'losses': 3,
                    'ties': 0,
                    'fpts': 1650.5
                }
            }
        ],
        'users': [
            {
                'user_id': '736083244801474560',
                'username': 'testuser',
                'display_name': 'Test User',
                'avatar': 'test_avatar',
                'team_name': 'Test Team'
            }
        ]
    }


@pytest.fixture
def mock_weekly_stats():
    """Mock weekly stats data for testing."""
    return [
        {
            'player_id': '4881',
            'points': 25.5,
            'roster_id': 1,
            'is_starter': True
        },
        {
            'player_id': '4035',
            'points': 18.2,
            'roster_id': 1,
            'is_starter': True
        }
    ]


# Configure pytest settings
def pytest_configure(config):
    """Configure pytest with custom settings."""
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests"
    )
    config.addinivalue_line(
        "markers", "api: marks tests as API tests"
    )
    config.addinivalue_line(
        "markers", "unit: marks tests as unit tests"
    )


# Test collection configuration
def pytest_collection_modifyitems(config, items):
    """Modify test collection to add markers automatically."""
    for item in items:
        # Add markers based on test file location
        if "integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
        elif "api" in str(item.fspath):
            item.add_marker(pytest.mark.api)
        elif "unit" in str(item.fspath):
            item.add_marker(pytest.mark.unit)
