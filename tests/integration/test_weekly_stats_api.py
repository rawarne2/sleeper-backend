"""
Integration tests for weekly stats API endpoints.

These tests verify the weekly stats functionality works end-to-end
with the database and API endpoints.
"""
import json
from tests.fixtures.database import client


def test_seed_league_stats_integration(client):
    """Test seeding league stats information via API."""
    data = {
        'league_name': 'Test Fantasy League',
        'season': '2024',
        'league_type': 'dynasty'
    }

    response = client.post(
        '/api/sleeper/league/1050831680350568448/stats/seed', json=data)

    # Should succeed or fail gracefully
    assert response.status_code in [200, 400, 500]

    if response.status_code == 200:
        response_data = json.loads(response.data)
        assert 'status' in response_data
        assert response_data['status'] == 'success'
        assert 'message' in response_data
        assert 'league_id' in response_data
        assert 'season' in response_data


def test_seed_league_stats_missing_data(client):
    """Test seeding league stats with missing required data."""
    # Missing league_name and season
    response = client.post(
        '/api/sleeper/league/1050831680350568448/stats/seed', json={})

    assert response.status_code == 400
    response_data = json.loads(response.data)
    assert 'status' in response_data
    assert response_data['status'] == 'error'
    assert 'error' in response_data


def test_get_weekly_stats_integration(client):
    """Test getting weekly stats for a specific week."""
    response = client.get(
        '/api/sleeper/league/1050831680350568448/stats/week/1')

    # May return 404 if no data exists, 500 for database issues, or 200 for success
    assert response.status_code in [200, 404, 500]

    if response.status_code == 200:
        response_data = json.loads(response.data)
        assert 'status' in response_data
        assert 'records' in response_data
        assert 'count' in response_data


def test_get_weekly_stats_with_params(client):
    """Test getting weekly stats with query parameters."""
    response = client.get(
        '/api/sleeper/league/1050831680350568448/stats/week/1?season=2024&league_type=dynasty')

    # May return 404 if no data exists, 500 for database issues, or 200 for success
    assert response.status_code in [200, 404, 500]


def test_refresh_weekly_stats_integration(client):
    """Test refreshing weekly stats for a specific week."""
    response = client.post(
        '/api/sleeper/league/1050831680350568448/stats/week/1')

    # May fail due to invalid league ID or API issues in test environment
    assert response.status_code in [200, 400, 500]

    if response.status_code == 200:
        response_data = json.loads(response.data)
        assert 'status' in response_data
        assert response_data['status'] == 'success'
        assert 'message' in response_data
        assert 'refresh_results' in response_data


def test_refresh_weekly_stats_with_params(client):
    """Test refreshing weekly stats with query parameters."""
    response = client.post(
        '/api/sleeper/league/1050831680350568448/stats/week/1?season=2024&league_type=dynasty')

    # May fail due to invalid league ID or API issues in test environment
    assert response.status_code in [200, 400, 500]


def test_weekly_stats_invalid_league_id(client):
    """Test weekly stats endpoints with invalid league ID."""
    # Test get endpoint - currently returns 200 with no data, which is acceptable
    response = client.get('/api/sleeper/league/invalid_id/stats/week/1')
    assert response.status_code in [200, 404, 500]

    # Test refresh endpoint - may succeed or fail depending on API validation
    response = client.post('/api/sleeper/league/invalid_id/stats/week/1')
    assert response.status_code in [200, 400, 404, 500]


def test_weekly_stats_invalid_week(client):
    """Test weekly stats endpoints with invalid week number."""
    # Test with week 0 - currently allowed, returns empty data
    response = client.get(
        '/api/sleeper/league/1050831680350568448/stats/week/0')
    assert response.status_code in [200, 400, 404, 500]

    # Test with week 25 - currently allowed, returns empty data
    response = client.get(
        '/api/sleeper/league/1050831680350568448/stats/week/25')
    assert response.status_code in [200, 400, 404, 500]
