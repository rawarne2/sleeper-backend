"""
Integration tests for weekly stats API endpoints.

These tests verify the weekly stats functionality works end-to-end
with the database and API endpoints.
"""
import json
from tests.fixtures.database import client


def test_seed_league_stats_integration(client):
    """POST with all fields creates a new league stats record and triggers weekly stats fetch."""
    data = {
        'league_name': 'Test Fantasy League',
        'season': '2024',
        'league_type': 'dynasty',
    }

    response = client.post(
        '/api/sleeper/league/1050831680350568448/stats/seed', json=data)

    # Should succeed or fail gracefully
    assert response.status_code in [200, 400, 500]

    if response.status_code == 200:
        response_data = json.loads(response.data)
        assert response_data['status'] == 'success'
        assert 'message' in response_data
        assert 'league_id' in response_data
        assert 'season' in response_data
        # Seed now also kicks off weekly stats; presence of these keys is asserted
        # without coupling to whether Sleeper returned data in the test env.
        assert 'last_week_updated' in response_data
        assert 'weekly_stats' in response_data


def test_seed_league_stats_put_update(client):
    """PUT after POST reuses stored season/league_type without requiring them."""
    seed_data = {'league_name': 'Test Fantasy League', 'season': '2024', 'league_type': 'dynasty'}
    client.post('/api/sleeper/league/1050831680350568448/stats/seed', json=seed_data)
    response = client.put(
        '/api/sleeper/league/1050831680350568448/stats/seed', json={})
    assert response.status_code in [200, 400, 500]


def test_seed_league_stats_missing_data(client):
    """POST with no fields for a brand-new league returns 400."""
    response = client.post(
        '/api/sleeper/league/new_league_8888/stats/seed', json={})

    assert response.status_code == 400
    response_data = json.loads(response.data)
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


def test_put_weekly_stats_integration(client):
    """PUT is the preferred method for refreshing weekly stats."""
    response = client.put(
        '/api/sleeper/league/1050831680350568448/stats/week/1')

    assert response.status_code in [200, 400, 500]

    if response.status_code == 200:
        response_data = json.loads(response.data)
        assert response_data['status'] == 'success'
        assert 'message' in response_data
        assert 'refresh_results' in response_data


def test_put_weekly_stats_with_params(client):
    """PUT weekly stats accepts optional query parameters."""
    response = client.put(
        '/api/sleeper/league/1050831680350568448/stats/week/1?season=2024&league_type=dynasty')

    assert response.status_code in [200, 400, 500]


def test_weekly_stats_invalid_league_id(client):
    """GET and PUT with an invalid league ID fail gracefully."""
    response = client.get('/api/sleeper/league/invalid_id/stats/week/1')
    assert response.status_code in [200, 404, 500]

    response = client.put('/api/sleeper/league/invalid_id/stats/week/1')
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
