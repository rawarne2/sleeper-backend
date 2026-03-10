"""
Health API endpoint tests.
"""
import json
from tests.fixtures.database import client


def test_health_check_endpoint_exists(client):
    """Test that the health check endpoint exists"""
    response = client.get('/api/ktc/health')
    # Should return 200 or 500 depending on database connection
    assert response.status_code in [200, 500]


def test_health_check_response_format(client):
    """Test that the health check endpoint returns properly formatted JSON"""
    response = client.get('/api/ktc/health')
    data = json.loads(response.data)

    # Check that all required fields are present
    assert 'status' in data
    assert 'database' in data
    assert 'timestamp' in data

    # Check that status is one of the expected values
    assert data['status'] in ['healthy', 'unhealthy']

    # Check that database status is one of the expected values
    assert data['database'] in ['connected', 'connection_failed', 'error']

    # If unhealthy, there should be an error message
    if data['status'] == 'unhealthy':
        assert 'error' in data or data['database'] != 'connected'
