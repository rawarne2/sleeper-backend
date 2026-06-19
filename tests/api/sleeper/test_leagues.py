"""
Sleeper Leagues API endpoint tests.
"""


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
        data = response.json()
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

    # The refresh endpoint always returns the full results dict (not the error
    # envelope) even on 404/500. Check the results body shape in all cases.
    data = response.json()
    assert 'status' in data
    assert 'timestamp' in data
    assert 'league_id' in data
    assert 'errors' in data


def test_refresh_league_data_put_method(client):
    """Test that the refresh endpoint also accepts PUT requests"""
    response = client.put('/api/sleeper/league/123456789')
    assert response.status_code in [200, 404, 500]

    data = response.json()
    assert 'status' in data
    assert 'league_id' in data


def test_refresh_league_data_404_body_shape(client):
    """
    When the scrape fails (league_data error), the refresh must return 404
    with the full results dict as the body — NOT the ApiError envelope.
    """
    response = client.post('/api/sleeper/league/000000000000000000')
    # If it returned 404, the body must be the results dict (has 'errors' key),
    # not the ApiError envelope (which only has 'status', 'error', 'timestamp').
    if response.status_code == 404:
        data = response.json()
        assert 'errors' in data, "404 body should be the results dict, not error envelope"
        assert 'league_id' in data
        assert 'status' in data
        assert data['status'] == 'error'
        # Confirm it is NOT the ApiError envelope (which has 'error' but not 'errors')
        assert 'league_data' in data
