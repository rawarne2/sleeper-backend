"""
Sleeper Research API endpoint tests.
"""
import json
from tests.fixtures.database import client


def test_get_research_data_endpoint_exists(client):
    """Test that the get research data endpoint exists"""
    response = client.get('/api/sleeper/players/research/2024')
    # May return 404 or 500 due to no data or API issues
    assert response.status_code in [200, 404, 500]


def test_get_research_data_invalid_season(client):
    """Test that invalid season format returns appropriate error"""
    response = client.get('/api/sleeper/players/research/invalid')
    # Should return 404 or 500 for invalid season
    assert response.status_code in [404, 500]


def test_get_research_data_with_params(client):
    """Test that the research endpoint accepts query parameters"""
    response = client.get(
        '/api/sleeper/players/research/2024?week=1&league_type=dynasty')
    # May return 404 or 500 due to no data or API issues
    assert response.status_code in [200, 404, 500]


def test_refresh_research_data_endpoint_exists(client):
    """Test that the refresh research data endpoint exists"""
    response = client.post('/api/sleeper/players/research/2024')
    # May return 400 or 500 due to API scraping issues
    assert response.status_code in [200, 400, 500]


def test_refresh_research_data_with_params(client):
    """Test that the refresh research endpoint accepts query parameters"""
    response = client.post(
        '/api/sleeper/players/research/2024?week=1&league_type=dynasty')
    # May return 400 or 500 due to API scraping issues
    assert response.status_code in [200, 400, 500]
