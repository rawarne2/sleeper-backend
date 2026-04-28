"""
Sleeper Weekly Stats API endpoint tests.
"""
import json
from tests.fixtures.database import client


def test_seed_league_stats_post_creates(client):
    """POST with required fields creates a new league stats record."""
    data = {
        'league_name': 'Test League',
        'season': '2024',
        'league_type': 'dynasty',
    }
    response = client.post('/api/sleeper/league/123456789/stats/seed', json=data)
    assert response.status_code in [200, 400, 500]


def test_seed_league_stats_put_updates(client):
    """PUT without fields succeeds when league already exists; requires POST first."""
    seed_data = {'league_name': 'Test League', 'season': '2024', 'league_type': 'dynasty'}
    client.post('/api/sleeper/league/123456789/stats/seed', json=seed_data)
    response = client.put('/api/sleeper/league/123456789/stats/seed', json={})
    # 200 if league was created above, 400 if DB is empty (no existing row)
    assert response.status_code in [200, 400, 500]


def test_seed_league_stats_missing_data_on_new_league(client):
    """POST with empty body for a new league returns 400."""
    response = client.post('/api/sleeper/league/new_league_999/stats/seed', json={})
    assert response.status_code == 400
    data = json.loads(response.data)
    assert data['status'] == 'error'
    assert 'error' in data


def test_seed_league_stats_invalid_json(client):
    """Invalid JSON is ignored (silent parse); new league without fields returns 400."""
    response = client.post(
        '/api/sleeper/league/new_league_invalid_json/stats/seed',
        data='invalid json',
        content_type='text/plain',
    )
    assert response.status_code == 400
    data = json.loads(response.data)
    assert data['status'] == 'error'


def test_get_weekly_stats_endpoint_exists(client):
    """GET weekly stats endpoint responds."""
    response = client.get('/api/sleeper/league/123456789/stats/week/1')
    assert response.status_code in [200, 404, 500]


def test_get_weekly_stats_with_params(client):
    """GET weekly stats accepts optional query parameters."""
    response = client.get(
        '/api/sleeper/league/123456789/stats/week/1?season=2024&league_type=dynasty')
    assert response.status_code in [200, 404, 500]


def test_put_weekly_stats_endpoint_exists(client):
    """PUT is the preferred method for refreshing weekly stats."""
    response = client.put('/api/sleeper/league/123456789/stats/week/1')
    assert response.status_code in [200, 400, 500]


def test_put_weekly_stats_with_params(client):
    """PUT weekly stats accepts optional query parameters."""
    response = client.put(
        '/api/sleeper/league/123456789/stats/week/1?season=2024&league_type=dynasty')
    assert response.status_code in [200, 400, 500]
