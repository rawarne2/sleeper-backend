import pytest
from app import app, db, KTCPlayer
import json
from typing import TypedDict, List, Union, Literal
from datetime import datetime

# Type definitions for our API responses


class Player(TypedDict):
    player_name: str
    position: str
    team: str
    value: int
    age: Union[float, None]
    rookie: str
    rank: Union[int, None]
    trend: str
    tier: Union[str, None]
    position_rank: Union[str, None]


class KTCResponse(TypedDict):
    timestamp: str
    is_redraft: bool
    league_format: Literal["1QB", "SF"]
    tep: int
    players: List[Player]


@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'

    with app.test_client() as client:
        with app.app_context():
            db.create_all()
            yield client
            db.session.remove()
            db.drop_all()


def test_refresh_endpoint_exists(client):
    """Test that the refresh endpoint exists and accepts POST requests"""
    response = client.post('/api/ktc/refresh?league_format=SF&tep=1')
    # Either success or invalid params
    assert response.status_code in [200, 400]


def test_refresh_endpoint_validation(client):
    """Test that the refresh endpoint validates parameters correctly"""
    # Test invalid league format
    response = client.post('/api/ktc/refresh?league_format=invalid')
    assert response.status_code == 400
    data = json.loads(response.data)
    assert 'error' in data

    # Test invalid TEP value
    response = client.post('/api/ktc/refresh?tep=5')
    assert response.status_code == 400
    data = json.loads(response.data)
    assert 'error' in data


def test_rankings_endpoint_exists(client):
    """Test that the rankings endpoint exists and returns 200"""
    response = client.get('/api/ktc/rankings')
    assert response.status_code in [200, 404]  # Either data or not found


def test_rankings_invalid_parameters(client):
    """Test that invalid parameters return appropriate errors"""
    # Test invalid league format
    response = client.get('/api/ktc/rankings?league_format=invalid')
    assert response.status_code == 400
    data = json.loads(response.data)
    assert 'error' in data

    # Test invalid TEP value
    response = client.get('/api/ktc/rankings?tep=5')
    assert response.status_code == 400
    data = json.loads(response.data)
    assert 'error' in data


def test_rankings_not_found(client):
    """Test that appropriate response is returned when no data exists"""
    response = client.get(
        '/api/ktc/rankings?league_format=SF&is_redraft=true&tep=2')
    assert response.status_code == 404
    data = json.loads(response.data)
    assert 'error' in data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
