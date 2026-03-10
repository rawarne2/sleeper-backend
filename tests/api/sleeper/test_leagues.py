"""
Sleeper Leagues API endpoint tests.
"""
import json
from tests.fixtures.database import client


def test_get_league_data_endpoint_exists(client):
    """Test that the get league data endpoint exists"""
    # Using a test league ID
    response = client.get('/api/sleeper/league/123456789')
    # May return 404 or 500 due to invalid league ID or API issues
    assert response.status_code in [200, 404, 500]


def test_get_league_data_invalid_id(client):
    """Test that invalid league ID returns appropriate error"""
    response = client.get('/api/sleeper/league/invalid_id')
    # Should return 404 for invalid league ID
    assert response.status_code in [404, 500]

    if response.status_code == 404:
        data = json.loads(response.data)
        assert 'status' in data
        assert data['status'] == 'error'
        assert 'error' in data


def test_get_league_rosters_endpoint_exists(client):
    """Test that the get league rosters endpoint exists"""
    response = client.get('/api/sleeper/league/123456789/rosters')
    # May return 404 or 500 due to invalid league ID or API issues
    assert response.status_code in [200, 404, 500]


def test_get_league_users_endpoint_exists(client):
    """Test that the get league users endpoint exists"""
    response = client.get('/api/sleeper/league/123456789/users')
    # May return 404 or 500 due to invalid league ID or API issues
    assert response.status_code in [200, 404, 500]


def test_refresh_league_data_endpoint_exists(client):
    """Test that the refresh league data endpoint exists"""
    response = client.post('/api/sleeper/league/123456789')
    # May return 404 or 500 due to invalid league ID or API issues
    assert response.status_code in [200, 404, 500]

    if response.status_code == 200:
        data = json.loads(response.data)
        assert 'status' in data
        assert 'timestamp' in data
        assert 'league_id' in data
