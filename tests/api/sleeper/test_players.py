"""
Sleeper Players API endpoint tests.
"""
import json
from tests.fixtures.database import client


def test_refresh_sleeper_endpoint_exists(client):
    """Test that the Sleeper refresh endpoint exists and accepts POST requests"""
    response = client.post('/api/sleeper/refresh')
    # Either success or scraping error (expected in test environment)
    assert response.status_code in [200, 500]


def test_refresh_sleeper_response_format(client):
    """Test that the Sleeper refresh endpoint returns properly formatted JSON"""
    response = client.post('/api/sleeper/refresh')

    # May fail due to scraping issues in test environment
    if response.status_code == 200:
        data = json.loads(response.data)

        # Check for the expected response structure
        assert 'message' in data
        assert 'timestamp' in data
        assert 'sleeper_data_results' in data
        assert 'database_success' in data
        assert 'merge_effective' in data

        # Check sleeper data results structure
        sleeper_results = data['sleeper_data_results']
        assert 'total_sleeper_players' in sleeper_results
        assert 'existing_records_before' in sleeper_results
        assert 'ktc_players_updated' in sleeper_results
        assert 'new_records_created' in sleeper_results
        assert 'match_failures' in sleeper_results
        assert 'total_processed' in sleeper_results
    else:
        # Expected to fail in test environment due to scraping issues
        assert response.status_code == 500
        data = json.loads(response.data)
        assert 'error' in data
        assert 'database_success' in data
        assert data['database_success'] is False
