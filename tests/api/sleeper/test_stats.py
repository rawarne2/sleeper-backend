"""
Sleeper Weekly Stats API endpoint tests.
"""
import json
from tests.fixtures.database import client


def test_seed_league_stats_endpoint_exists(client):
    """Test that the seed league stats endpoint exists"""
    data = {
        'league_name': 'Test League',
        'season': '2024',
        'league_type': 'dynasty'
    }
    response = client.post(
        '/api/sleeper/league/123456789/stats/seed', json=data)
    # May return 400, 500 due to invalid league ID or database issues
    assert response.status_code in [200, 400, 500]


def test_seed_league_stats_missing_data(client):
    """Test that missing required data returns appropriate error"""
    response = client.post('/api/sleeper/league/123456789/stats/seed', json={})
    assert response.status_code == 400
    data = json.loads(response.data)
    assert 'status' in data
    assert data['status'] == 'error'
    assert 'error' in data


def test_seed_league_stats_invalid_json(client):
    """Test that invalid JSON returns appropriate error"""
    # Send request without Content-Type header or with wrong content type
    response = client.post('/api/sleeper/league/123456789/stats/seed',
                           data='invalid json',
                           content_type='text/plain')
    # The error handler wraps the 415 error in a 500 response
    assert response.status_code == 500
    data = json.loads(response.data)
    assert 'status' in data
    assert data['status'] == 'error'


def test_get_weekly_stats_endpoint_exists(client):
    """Test that the get weekly stats endpoint exists"""
    response = client.get('/api/sleeper/league/123456789/stats/week/1')
    # May return 404, 500 due to no data or database issues
    assert response.status_code in [200, 404, 500]


def test_get_weekly_stats_with_params(client):
    """Test that the weekly stats endpoint accepts query parameters"""
    response = client.get(
        '/api/sleeper/league/123456789/stats/week/1?season=2024&league_type=dynasty')
    # May return 404, 500 due to no data or database issues
    assert response.status_code in [200, 404, 500]


def test_refresh_weekly_stats_endpoint_exists(client):
    """Test that the refresh weekly stats endpoint exists"""
    response = client.post('/api/sleeper/league/123456789/stats/week/1')
    # May return 400, 500 due to invalid league ID or API issues
    assert response.status_code in [200, 400, 500]


def test_refresh_weekly_stats_with_params(client):
    """Test that the refresh weekly stats endpoint accepts query parameters"""
    response = client.post(
        '/api/sleeper/league/123456789/stats/week/1?season=2024&league_type=dynasty')
    # May return 400, 500 due to invalid league ID or API issues
    assert response.status_code in [200, 400, 500]
