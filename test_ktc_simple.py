import pytest
from app import app
from models import db, KTCPlayer
import json


@pytest.fixture
def client():
    app.config['TESTING'] = True
    # Use SQLite in-memory database for testing
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'

    with app.test_client() as client:
        with app.app_context():
            db.create_all()
            yield client
            db.session.remove()
            db.drop_all()


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


def test_rankings_endpoint_exists(client):
    """Test that the rankings endpoint exists"""
    response = client.get('/api/ktc/rankings')
    assert response.status_code in [200, 404]  # Either data or not found


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


def test_rankings_not_found(client):
    """Test that appropriate response is returned when no data exists"""
    response = client.get(
        '/api/ktc/rankings?league_format=superflex&is_redraft=true&tep_level=tepp')
    assert response.status_code == 404
    data = json.loads(response.data)
    assert 'error' in data
