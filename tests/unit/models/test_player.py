"""
Player model unit tests.
"""
from datetime import datetime, UTC
from models.entities import Player as PlayerModel
from models.extensions import db
from tests.fixtures.database import app_context


def test_player_model_creation(app_context):
    """Test Player model creation and to_dict method."""
    player = PlayerModel(
        player_name="Christian McCaffrey",
        position="RB",
        team="SF",
        age=27.5,
        rookie="No",
        sleeper_player_id="4035",
        last_updated=datetime.now(UTC)
    )
    db.session.add(player)
    db.session.commit()

    # Test to_dict method
    player_dict = player.to_dict()
    assert player_dict['playerName'] == "Christian McCaffrey"
    assert player_dict['position'] == "RB"
    assert player_dict['team'] == "SF"


def test_player_model_required_fields(app_context):
    """Test Player model with required fields only."""
    player = PlayerModel(
        player_name="Test Player",
        position="QB",
        team="TEST"
    )
    db.session.add(player)
    db.session.commit()

    assert player.player_name == "Test Player"
    assert player.position == "QB"
    assert player.team == "TEST"


def test_player_model_to_dict_structure(app_context):
    """Test Player model to_dict method returns expected structure."""
    player = PlayerModel(
        player_name="Josh Allen",
        position="QB",
        team="BUF",
        age=28.0,
        rookie="No",
        sleeper_player_id="4881"
    )
    db.session.add(player)
    db.session.commit()

    player_dict = player.to_dict()

    # Check required fields are present
    assert 'playerName' in player_dict
    assert 'position' in player_dict
    assert 'team' in player_dict

    # Check optional fields
    assert 'sleeper_player_id' in player_dict
    assert 'ktc' in player_dict

    # Age is in the ktc nested object
    assert 'age' in player_dict['ktc']
