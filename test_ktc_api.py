import pytest
import json
from app import app, db, KTCPlayer


@pytest.fixture
def client():
    app.config['TESTING'] = True
    # Use PostgreSQL test database - assumes you have a test database set up
    app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:password@localhost:5433/sleeper_test_db'

    with app.test_client() as client:
        with app.app_context():
            db.create_all()
            yield client
            db.session.remove()
            db.drop_all()


def test_refresh_endpoint_exists(client):
    """Test that the refresh endpoint exists and accepts POST requests"""
    response = client.post(
        '/api/ktc/refresh?league_format=superflex&tep_level=tep')
    # Either success or invalid params
    assert response.status_code in [200, 400]


def test_refresh_endpoint_validation(client):
    """Test that the refresh endpoint validates parameters correctly"""
    # Test invalid league format
    response = client.post('/api/ktc/refresh?league_format=invalid')
    assert response.status_code == 400
    data = json.loads(response.data)
    assert 'error' in data

    # Test invalid TEP level value
    response = client.post('/api/ktc/refresh?tep_level=invalid_tep')
    assert response.status_code == 400
    data = json.loads(response.data)
    assert 'error' in data


def test_refresh_stores_data(client):
    """Test that refresh endpoint stores data in the database"""
    response = client.post(
        '/api/ktc/refresh?is_redraft=false&league_format=superflex&tep_level=tep')
    assert response.status_code == 200
    data = json.loads(response.data)

    # Check for the new response structure
    assert 'message' in data
    assert 'timestamp' in data
    assert 'database_success' in data
    assert 'operations_summary' in data

    # Check operations summary contains the count information
    operations_summary = data['operations_summary']
    assert 'players_count' in operations_summary
    assert 'database_saved_count' in operations_summary
    assert operations_summary['players_count'] > 0
    assert operations_summary['database_saved_count'] > 0

    # Verify data was stored in database
    players = KTCPlayer.query.all()
    assert len(players) > 0
    assert all(p.league_format == 'superflex' for p in players)
    assert all(p.is_redraft is True for p in players)
    # tep level "tep" stored as string
    assert all(p.tep == 'tep' for p in players)


def test_rankings_endpoint_exists(client):
    """Test that the rankings endpoint exists and returns 200"""
    response = client.get('/api/ktc/rankings')
    assert response.status_code in [200, 404]  # Either data or not found


def test_rankings_response_format(client):
    """Test that the rankings endpoint returns properly formatted JSON"""
    # First refresh the data
    client.post(
        '/api/ktc/refresh?is_redraft=false&league_format=superflex&tep_level=tep')

    # Then test the response format
    response = client.get(
        '/api/ktc/rankings?league_format=superflex&is_redraft=false&tep_level=tep')
    data = json.loads(response.data)

    # Check that all required fields are present
    assert 'timestamp' in data
    assert 'is_redraft' in data
    assert 'league_format' in data
    assert 'tep_level' in data
    assert 'players' in data

    # Check that players is a list
    assert isinstance(data['players'], list)

    # If there are players, check their structure
    if data['players']:
        player = data['players'][0]
        assert "Player Name" in player
        assert "Position" in player
        assert "Team" in player
        assert "Value" in player
        assert "Age" in player
        assert "Rookie" in player
        assert "Rank" in player
        assert "Trend" in player
        assert "Tier" in player
        assert "Position Rank" in player


def test_rankings_query_parameters(client):
    """Test that query parameters are properly handled"""
    # First refresh the data
    client.post(
        '/api/ktc/refresh?is_redraft=true&league_format=superflex&tep_level=tep')

    # Test with custom parameters
    response = client.get(
        '/api/ktc/rankings?is_redraft=true&league_format=superflex&tep_level=tep')
    data = json.loads(response.data)
    assert data['is_redraft'] is True
    assert data['league_format'] == 'superflex'
    assert data['tep_level'] == 'tep'


def test_rankings_invalid_parameters(client):
    """Test that invalid parameters return appropriate errors"""
    # Test invalid league format
    response = client.get('/api/ktc/rankings?league_format=invalid')
    assert response.status_code == 400
    data = json.loads(response.data)
    assert 'error' in data

    # Test invalid TEP level value
    response = client.get('/api/ktc/rankings?tep_level=invalid_tep')
    assert response.status_code == 400
    data = json.loads(response.data)
    assert 'error' in data


def test_rankings_player_data_types(client):
    """Test that player data has correct types"""
    # First refresh the data
    client.post(
        '/api/ktc/refresh?is_redraft=false&league_format=superflex&tep_level=tep')

    response = client.get(
        '/api/ktc/rankings?league_format=superflex&is_redraft=false&tep_level=tep')
    data = json.loads(response.data)

    if data['players']:
        player = data['players'][0]
        assert isinstance(player["Player Name"], str)
        assert isinstance(player["Position"], str)
        assert isinstance(player["Team"], str)
        assert isinstance(player["Value"], int)
        assert isinstance(player["Rookie"], str)
        assert isinstance(player["Trend"], str)
        # Age and Rank can be None
        assert player["Age"] is None or isinstance(player["Age"], (int, float))
        assert player["Rank"] is None or isinstance(player["Rank"], int)
        assert player["Tier"] is None or isinstance(player["Tier"], str)
        assert player["Position Rank"] is None or isinstance(
            player["Position Rank"], str)


def test_rankings_not_found(client):
    """Test that appropriate response is returned when no data exists"""
    response = client.get(
        '/api/ktc/rankings?league_format=superflex&is_redraft=true&tep_level=tepp')
    assert response.status_code == 404
    data = json.loads(response.data)
    assert 'error' in data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
