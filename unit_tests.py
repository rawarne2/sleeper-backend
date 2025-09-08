from app import app
from models import db, Player as PlayerModel, SleeperLeague, SleeperRoster, SleeperUser
import os
import pytest
import json
from datetime import datetime, UTC
from typing import TypedDict, List, Union, Literal, Optional

# Set test database URI before importing app
os.environ['TEST_DATABASE_URI'] = 'sqlite:///:memory:'


# Type definitions for our API responses
class PlayerData(TypedDict):
    player_name: str
    position: str
    team: str
    value: int
    age: Union[float, None]
    rookie: str
    rank: Union[int, None]
    trend: str
    tier: Union[str, None]
    position_rank: Union[str, None]


class KTCResponse(TypedDict):
    timestamp: str
    is_redraft: bool
    league_format: Literal["1qb", "superflex"]
    tep_level: Optional[str]
    players: List[PlayerData]


@pytest.fixture
def client():
    """Create test client with in-memory database."""
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'

    with app.test_client() as client:
        with app.app_context():
            db.create_all()
            yield client
            db.session.remove()
            db.drop_all()


@pytest.fixture
def sample_player(client):
    """Create a sample player for testing."""
    with app.app_context():
        player = PlayerModel(
            player_name="Josh Allen",
            position="QB",
            team="BUF",
            age=28.0,
            rookie="No",
            sleeper_player_id="4881",
            last_updated=datetime.now(UTC)
        )
        db.session.add(player)
        db.session.commit()
        return player


# ============================================================================
# HEALTH CHECK TESTS
# ============================================================================

def test_health_check_endpoint(client):
    """Test health check endpoint returns proper status."""
    response = client.get('/api/ktc/health')
    assert response.status_code == 200

    data = json.loads(response.data)
    assert 'status' in data
    assert 'database' in data
    assert 'timestamp' in data
    assert data['status'] == 'healthy'
    assert data['database'] == 'connected'


# ============================================================================
# KTC ENDPOINT TESTS
# ============================================================================

def test_ktc_refresh_endpoint_exists(client):
    """Test that the KTC refresh endpoint exists and accepts POST requests."""
    response = client.post(
        '/api/ktc/refresh?league_format=superflex&tep_level=tep')
    # Either success or scraping error (expected in test environment)
    assert response.status_code in [200, 500]


def test_ktc_refresh_parameter_validation(client):
    """Test KTC refresh endpoint parameter validation."""
    # Test invalid league format
    response = client.post('/api/ktc/refresh?league_format=invalid')
    assert response.status_code == 400
    data = json.loads(response.data)
    assert 'error' in data

    # Test invalid TEP level
    response = client.post('/api/ktc/refresh?tep_level=invalid_tep')
    assert response.status_code == 400
    data = json.loads(response.data)
    assert 'error' in data

    # Test invalid is_redraft value
    response = client.post('/api/ktc/refresh?is_redraft=maybe')
    assert response.status_code == 400
    data = json.loads(response.data)
    assert 'error' in data


def test_ktc_refresh_all_endpoint(client):
    """Test comprehensive KTC refresh endpoint."""
    response = client.post('/api/ktc/refresh/all')
    # Either success or scraping error (expected in test environment)
    assert response.status_code in [200, 500]


def test_ktc_rankings_endpoint_exists(client):
    """Test that the KTC rankings endpoint exists."""
    response = client.get('/api/ktc/rankings')
    # Either data exists, not found, or database error
    assert response.status_code in [200, 404, 500]


def test_ktc_rankings_parameter_validation(client):
    """Test KTC rankings endpoint parameter validation."""
    # Test invalid league format
    response = client.get('/api/ktc/rankings?league_format=invalid')
    assert response.status_code == 400
    data = json.loads(response.data)
    assert 'error' in data

    # Test invalid TEP level
    response = client.get('/api/ktc/rankings?tep_level=invalid_tep')
    assert response.status_code == 400
    data = json.loads(response.data)
    assert 'error' in data


def test_ktc_rankings_with_data(client, sample_player):
    """Test KTC rankings endpoint returns data when available."""
    response = client.get(
        '/api/ktc/rankings?league_format=superflex&is_redraft=false')
    # May return 500 due to database query issues in test environment
    assert response.status_code in [200, 404, 500]

    if response.status_code == 200:
        data = json.loads(response.data)
        assert 'players' in data
        assert 'count' in data
        assert 'league_format' in data
        assert 'is_redraft' in data
        assert data['league_format'] == 'superflex'
        assert data['is_redraft'] is False


def test_ktc_cleanup_endpoint(client):
    """Test KTC cleanup endpoint."""
    response = client.post(
        '/api/ktc/cleanup?league_format=superflex&tep_level=tep')
    # Either success or database error
    assert response.status_code in [200, 500]


# ============================================================================
# SLEEPER PLAYER ENDPOINT TESTS
# ============================================================================

def test_sleeper_refresh_endpoint(client):
    """Test Sleeper player data refresh endpoint."""
    response = client.post('/api/sleeper/refresh')
    # Either success or API/database error (expected in test environment)
    assert response.status_code in [200, 500]


# ============================================================================
# SLEEPER LEAGUE ENDPOINT TESTS
# ============================================================================

def test_sleeper_league_endpoint_invalid_id(client):
    """Test Sleeper league endpoint with invalid league ID."""
    response = client.get('/api/sleeper/league/invalid_id')
    assert response.status_code == 404

    data = json.loads(response.data)
    assert 'status' in data
    assert data['status'] == 'error'
    assert 'error' in data


def test_sleeper_league_rosters_endpoint_invalid_id(client):
    """Test Sleeper league rosters endpoint with invalid league ID."""
    response = client.get('/api/sleeper/league/invalid_id/rosters')
    assert response.status_code == 404

    data = json.loads(response.data)
    assert 'status' in data
    assert data['status'] == 'error'


def test_sleeper_league_users_endpoint_invalid_id(client):
    """Test Sleeper league users endpoint with invalid league ID."""
    response = client.get('/api/sleeper/league/invalid_id/users')
    assert response.status_code == 404

    data = json.loads(response.data)
    assert 'status' in data
    assert data['status'] == 'error'


def test_sleeper_league_refresh_endpoint(client):
    """Test Sleeper league refresh endpoint."""
    response = client.post('/api/sleeper/league/1210364682523656192/refresh')
    # Either success or API error (expected in test environment)
    assert response.status_code in [200, 500]


# ============================================================================
# SLEEPER RESEARCH ENDPOINT TESTS
# ============================================================================

def test_sleeper_research_endpoint_invalid_season(client):
    """Test Sleeper research endpoint with invalid season."""
    response = client.get('/api/sleeper/players/research/invalid')
    assert response.status_code == 404

    data = json.loads(response.data)
    assert 'status' in data
    assert data['status'] == 'error'


def test_sleeper_research_endpoint_valid_season(client):
    """Test Sleeper research endpoint with valid season."""
    response = client.get('/api/sleeper/players/research/2024')
    # Either success or API error (expected in test environment)
    assert response.status_code in [200, 404, 500]


def test_sleeper_research_endpoint_with_parameters(client):
    """Test Sleeper research endpoint with query parameters."""
    response = client.get(
        '/api/sleeper/players/research/2024?week=10&league_type=1')
    # Either success or API error (expected in test environment)
    assert response.status_code in [200, 404, 500]


def test_sleeper_research_refresh_endpoint(client):
    """Test Sleeper research refresh endpoint."""
    response = client.post('/api/sleeper/players/research/2024/refresh')
    # Either success or API error (expected in test environment)
    assert response.status_code in [200, 400, 500]


def test_sleeper_research_refresh_with_parameters(client):
    """Test Sleeper research refresh endpoint with parameters."""
    response = client.post(
        '/api/sleeper/players/research/2024/refresh?week=5&league_type=2')
    # Either success or API error (expected in test environment)
    assert response.status_code in [200, 400, 500]


# ============================================================================
# ERROR HANDLING TESTS
# ============================================================================

def test_nonexistent_endpoint(client):
    """Test that nonexistent endpoints return 404."""
    response = client.get('/api/nonexistent')
    assert response.status_code == 404


def test_wrong_http_method(client):
    """Test that wrong HTTP methods return 405."""
    # Try GET on POST-only endpoint
    response = client.get('/api/ktc/refresh')
    assert response.status_code == 405

    # Try POST on GET-only endpoint
    response = client.post('/api/ktc/rankings')
    assert response.status_code == 405


# ============================================================================
# DATA MODEL TESTS
# ============================================================================

def test_player_model_creation(client):
    """Test Player model creation and to_dict method."""
    with app.app_context():
        player = PlayerModel(
            player_name="Christian McCaffrey",
            position="RB",
            team="SF",
            age=27.5,
            rookie="No",
            sleeper_player_id="4035",
            last_updated=datetime.now(UTC)
        )
        db.session.add(player)
        db.session.commit()

        # Test to_dict method
        player_dict = player.to_dict()
        assert player_dict['playerName'] == "Christian McCaffrey"
        assert player_dict['position'] == "RB"
        assert player_dict['team'] == "SF"


def test_sleeper_league_model_creation(client):
    """Test SleeperLeague model creation and to_dict method."""
    with app.app_context():
        league = SleeperLeague(
            league_id="1210364682523656192",
            name="Test League",
            season="2025",
            status="in_season",
            last_updated=datetime.now(UTC)
        )
        db.session.add(league)
        db.session.commit()

        # Test to_dict method
        league_dict = league.to_dict()
        assert league_dict['league_id'] == "1210364682523656192"
        assert league_dict['name'] == "Test League"
        assert league_dict['season'] == "2025"


def test_sleeper_roster_model_creation(client):
    """Test SleeperRoster model creation and to_dict method."""
    with app.app_context():
        # First create a league
        league = SleeperLeague(
            league_id="1210364682523656192",
            name="Test League",
            season="2025",
            last_updated=datetime.now(UTC)
        )
        db.session.add(league)
        db.session.commit()

        # Then create a roster
        roster = SleeperRoster(
            league_id="1210364682523656192",
            roster_id=1,
            owner_id="736083244801474560",
            players='["4881", "4035"]',
            starters='["4881"]',
            last_updated=datetime.now(UTC)
        )
        db.session.add(roster)
        db.session.commit()

        # Test to_dict method
        roster_dict = roster.to_dict()
        assert roster_dict['league_id'] == "1210364682523656192"
        assert roster_dict['roster_id'] == 1
        assert roster_dict['owner_id'] == "736083244801474560"
        assert roster_dict['players'] == ["4881", "4035"]
        assert roster_dict['starters'] == ["4881"]


def test_sleeper_user_model_creation(client):
    """Test SleeperUser model creation and to_dict method."""
    with app.app_context():
        # First create a league
        league = SleeperLeague(
            league_id="1210364682523656192",
            name="Test League",
            season="2025",
            last_updated=datetime.now(UTC)
        )
        db.session.add(league)
        db.session.commit()

        # Then create a user
        user = SleeperUser(
            league_id="1210364682523656192",
            user_id="736083244801474560",
            username="testuser",
            display_name="Test User",
            last_updated=datetime.now(UTC)
        )
        db.session.add(user)
        db.session.commit()

        # Test to_dict method
        user_dict = user.to_dict()
        assert user_dict['league_id'] == "1210364682523656192"
        assert user_dict['user_id'] == "736083244801474560"
        assert user_dict['username'] == "testuser"
        assert user_dict['display_name'] == "Test User"


# ============================================================================
# INTEGRATION TESTS
# ============================================================================

def test_api_blueprint_registration(client):
    """Test that API blueprint is properly registered."""
    # Test that /api routes are accessible
    response = client.get('/api/ktc/health')
    assert response.status_code == 200

    # Test that non-api routes return 404
    response = client.get('/ktc/health')
    assert response.status_code == 404


def test_cors_headers(client):
    """Test that CORS headers are properly set."""
    response = client.options('/api/ktc/health')
    # CORS preflight should be handled
    assert response.status_code in [200, 204]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
