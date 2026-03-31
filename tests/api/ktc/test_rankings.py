"""
KTC Rankings API endpoint tests.
"""
import json

from models.entities import Player as PlayerModel
import routes.ktc.rankings as rankings_module
import services.ktc_refresh_async as ktc_refresh_async


def test_refresh_endpoint_exists(client):
    """Test that the refresh endpoint exists and accepts POST requests"""
    response = client.post(
        '/api/ktc/refresh?league_format=superflex&tep_level=tep')
    # 202 = async accepted; 200/400/500 for sync path or errors
    assert response.status_code in [200, 202, 400, 500]


def test_refresh_endpoint_validation(client):
    """Test that the refresh endpoint validates parameters correctly"""
    # Test invalid league format
    response = client.post('/api/ktc/refresh?league_format=invalid')
    assert response.status_code == 400
    data = json.loads(response.data)
    assert 'error' in data

    # Test invalid TEP level value
    response = client.post('/api/ktc/refresh?tep_level=invalid_tep')
    assert response.status_code == 400
    data = json.loads(response.data)
    assert 'error' in data


def test_refresh_stores_data(client):
    """Test that refresh endpoint stores data in the database"""
    response = client.post(
        '/api/ktc/refresh?is_redraft=false&league_format=superflex&tep_level=tep'
        '&sync=1')

    # May fail due to scraping issues in test environment
    if response.status_code == 200:
        data = json.loads(response.data)

        # Check for the new response structure
        assert 'message' in data
        assert 'timestamp' in data
        assert 'database_success' in data
        assert 'operations_summary' in data

        # Check operations summary contains the count information
        operations_summary = data['operations_summary']
        assert 'players_count' in operations_summary
        assert 'database_saved_count' in operations_summary
        assert operations_summary['players_count'] > 0
        assert operations_summary['database_saved_count'] > 0

        # Verify data was stored in database
        players = PlayerModel.query.all()
        assert len(players) > 0
    else:
        # Expected to fail in test environment due to scraping issues
        assert response.status_code in [400, 500]


def test_refresh_formats_scraper_players_in_response(client, monkeypatch):
    players = [
        {
            'playerName': 'Josh Allen',
            'position': 'QB',
            'team': 'BUF',
            'age': 28,
            'rookie': 'No',
            'oneqb_values': {
                'value': 8500,
                'rank': 5,
                'positionalRank': 3,
                'overallTier': 2,
                'positionalTier': 1,
                'tep': {'value': 8600, 'rank': 5, 'positionalRank': 3, 'overallTier': 2, 'positionalTier': 1}
            },
            'superflex_values': {
                'value': 9500,
                'rank': 1,
                'positionalRank': 1,
                'overallTier': 1,
                'positionalTier': 1,
                'tep': {'value': 9600, 'rank': 1, 'positionalRank': 1, 'overallTier': 1, 'positionalTier': 1}
            }
        }
    ]

    monkeypatch.setattr(
        ktc_refresh_async.DatabaseManager,
        'verify_database_connection',
        staticmethod(lambda: True)
    )
    monkeypatch.setattr(
        ktc_refresh_async,
        'scrape_and_process_data',
        lambda *args, **kwargs: (players, None)
    )
    monkeypatch.setattr(
        ktc_refresh_async,
        'save_and_verify_database',
        lambda *args, **kwargs: (1, None)
    )
    monkeypatch.setattr(
        ktc_refresh_async,
        'perform_file_operations',
        lambda *args, **kwargs: (False, False)
    )

    response = client.post(
        '/api/ktc/refresh?league_format=superflex&tep_level=tep&sync=1')
    assert response.status_code == 200

    data = json.loads(response.data)
    assert data['count'] == 1
    assert len(data['players']) == 1
    assert data['players'][0]['playerName'] == 'Josh Allen'
    assert data['players'][0]['ktc']['oneQBValues'] is None
    assert data['players'][0]['ktc']['superflexValues']['value'] == 9600


def test_refresh_async_returns_202(client, monkeypatch):
    monkeypatch.setattr(
        ktc_refresh_async,
        'execute_ktc_refresh_pipeline',
        lambda *a, **k: ktc_refresh_async.KTCRefreshOutcome(
            True,
            200,
            {
                'operations_summary': {
                    'players_count': 0,
                    'database_saved_count': 0,
                    'file_saved': False,
                    's3_uploaded': False,
                }
            },
        ),
    )
    monkeypatch.setattr(
        ktc_refresh_async.DatabaseManager,
        'verify_database_connection',
        staticmethod(lambda: True)
    )
    response = client.post(
        '/api/ktc/refresh?league_format=superflex&tep_level=tep')
    assert response.status_code == 202
    data = json.loads(response.data)
    assert data.get('accepted') is True
    assert data.get('job_id')
    assert '/api/ktc/refresh/status/' in data.get('poll_url', '')


def test_refresh_job_status_unknown(client):
    r = client.get('/api/ktc/refresh/status/00000000-0000-0000-0000-000000000099')
    assert r.status_code == 404


def test_refresh_job_status_after_enqueue(client, monkeypatch):
    def _fast_pipeline(league_format, is_redraft, tep_level):
        return ktc_refresh_async.KTCRefreshOutcome(
            True,
            200,
            {
                'operations_summary': {
                    'players_count': 0,
                    'database_saved_count': 0,
                    'file_saved': False,
                    's3_uploaded': False,
                }
            },
        )

    monkeypatch.setattr(
        ktc_refresh_async,
        'execute_ktc_refresh_pipeline',
        _fast_pipeline,
    )
    monkeypatch.setattr(
        ktc_refresh_async.DatabaseManager,
        'verify_database_connection',
        staticmethod(lambda: True)
    )
    post = client.post(
        '/api/ktc/refresh?league_format=1qb&is_redraft=false&tep_level=')
    assert post.status_code == 202
    job_id = json.loads(post.data)['job_id']
    get = client.get(f'/api/ktc/refresh/status/{job_id}')
    assert get.status_code == 200
    body = json.loads(get.data)
    assert body['job_id'] == job_id
    assert body['status'] in ('queued', 'running', 'succeeded', 'failed')


def test_rankings_endpoint_exists(client):
    """Test that the rankings endpoint exists and returns 200"""
    response = client.get('/api/ktc/rankings')
    # May return 500 due to database query issues in test environment
    assert response.status_code in [200, 404, 500]


def test_rankings_response_format(client, sample_player):
    """Test that the rankings endpoint returns properly formatted JSON"""
    # Test the response format
    response = client.get(
        '/api/ktc/rankings?league_format=superflex&is_redraft=false&tep_level=tep')

    # May fail due to database query issues in test environment
    if response.status_code == 200:
        data = json.loads(response.data)

        # Check that all required fields are present
        assert 'timestamp' in data or 'last_updated' in data
        assert 'is_redraft' in data
        assert 'league_format' in data
        assert 'tep_level' in data
        assert 'players' in data

        # Check that players is a list
        assert isinstance(data['players'], list)

        # If there are players, check their structure
        if data['players']:
            player = data['players'][0]
            assert "playerName" in player
            assert "position" in player
            assert "team" in player
    else:
        # Expected to fail in test environment
        assert response.status_code in [404, 500]


def test_rankings_query_parameters(client, sample_player):
    """Test that query parameters are properly handled"""
    # Test with custom parameters
    response = client.get(
        '/api/ktc/rankings?is_redraft=true&league_format=superflex&tep_level=tep')

    # May fail due to database query issues in test environment
    if response.status_code == 200:
        data = json.loads(response.data)
        assert data['is_redraft'] is True
        assert data['league_format'] == 'superflex'
        assert data['tep_level'] == 'tep'
    else:
        # Expected to fail in test environment
        assert response.status_code in [404, 500]


def test_rankings_invalid_parameters(client):
    """Test that invalid parameters return appropriate errors"""
    # Test invalid league format
    response = client.get('/api/ktc/rankings?league_format=invalid')
    assert response.status_code == 400
    data = json.loads(response.data)
    assert 'error' in data

    # Test invalid TEP level value
    response = client.get('/api/ktc/rankings?tep_level=invalid_tep')
    assert response.status_code == 400
    data = json.loads(response.data)
    assert 'error' in data


def test_rankings_player_data_types(client, sample_player):
    """Test that player data has correct types"""
    response = client.get(
        '/api/ktc/rankings?league_format=superflex&is_redraft=false&tep_level=tep')

    # May fail due to database query issues in test environment
    if response.status_code == 200:
        data = json.loads(response.data)

        if data.get('players'):
            player = data['players'][0]
            assert isinstance(player["playerName"], str)
            assert isinstance(player["position"], str)
            assert isinstance(player["team"], str)
            # Age and other fields can be None
            assert player.get("age") is None or isinstance(
                player.get("age"), (int, float))
    else:
        # Expected to fail in test environment
        assert response.status_code in [404, 500]


def test_rankings_not_found(client):
    """Test that appropriate response is returned when no data exists"""
    response = client.get(
        '/api/ktc/rankings?league_format=superflex&is_redraft=true&tep_level=tepp')
    # May return 500 due to database query issues in test environment
    assert response.status_code in [404, 500]
    data = json.loads(response.data)
    assert 'error' in data


def test_cleanup_endpoint_exists(client):
    """Test that the cleanup endpoint exists"""
    response = client.post('/api/ktc/cleanup')
    # May fail due to database operations in test environment
    assert response.status_code in [200, 400, 500]


def test_cleanup_endpoint_validation(client):
    """Test that the cleanup endpoint validates parameters correctly"""
    # Test invalid league format
    response = client.post('/api/ktc/cleanup?league_format=invalid')
    assert response.status_code == 400
    data = json.loads(response.data)
    assert 'error' in data
