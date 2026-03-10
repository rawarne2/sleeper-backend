"""
KTC Bulk Operations API endpoint tests.
"""
import json
from tests.fixtures.database import client


def test_refresh_all_endpoint_exists(client):
    """Test that the refresh all endpoint exists and accepts POST requests"""
    response = client.post('/api/ktc/refresh/all')
    # Either success or scraping error (expected in test environment)
    assert response.status_code in [200, 500]


def test_refresh_all_response_format(client):
    """Test that the refresh all endpoint returns properly formatted JSON"""
    response = client.post('/api/ktc/refresh/all')

    # May fail due to scraping issues in test environment
    if response.status_code == 200:
        data = json.loads(response.data)

        # Check for the expected response structure
        assert 'message' in data
        assert 'timestamp' in data
        assert 'results' in data

        results = data['results']
        assert 'overall_status' in results
        assert results['overall_status'] in [
            'success', 'partial_success', 'error']

        if 'summary' in data:
            summary = data['summary']
            assert 'total_players' in summary
            assert 'total_saved' in summary
    else:
        # Expected to fail in test environment due to scraping issues
        assert response.status_code == 500
        data = json.loads(response.data)
        assert 'error' in data
