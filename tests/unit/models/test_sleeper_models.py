"""
Sleeper models unit tests.
"""
from datetime import datetime, UTC
from models.entities import SleeperLeague, SleeperRoster, SleeperUser
from models.extensions import db
from tests.fixtures.database import app_context


def test_sleeper_league_model_creation(app_context):
    """Test SleeperLeague model creation and to_dict method."""
    league = SleeperLeague(
        league_id="1210364682523656192",
        name="Test League",
        season="2025",
        status="in_season",
        last_updated=datetime.now(UTC)
    )
    db.session.add(league)
    db.session.commit()

    # Test to_dict method
    league_dict = league.to_dict()
    assert league_dict['league_id'] == "1210364682523656192"
    assert league_dict['name'] == "Test League"
    assert league_dict['season'] == "2025"


def test_sleeper_roster_model_creation(app_context):
    """Test SleeperRoster model creation and to_dict method."""
    # First create a league
    league = SleeperLeague(
        league_id="1210364682523656192",
        name="Test League",
        season="2025",
        last_updated=datetime.now(UTC)
    )
    db.session.add(league)
    db.session.commit()

    # Then create a roster
    roster = SleeperRoster(
        league_id="1210364682523656192",
        roster_id=1,
        owner_id="736083244801474560",
        players='["4881", "4035"]',
        starters='["4881"]',
        last_updated=datetime.now(UTC)
    )
    db.session.add(roster)
    db.session.commit()

    # Test to_dict method
    roster_dict = roster.to_dict()
    assert roster_dict['league_id'] == "1210364682523656192"
    assert roster_dict['roster_id'] == 1
    assert roster_dict['owner_id'] == "736083244801474560"
    assert roster_dict['players'] == ["4881", "4035"]
    assert roster_dict['starters'] == ["4881"]


def test_sleeper_user_model_creation(app_context):
    """Test SleeperUser model creation and to_dict method."""
    # First create a league
    league = SleeperLeague(
        league_id="1210364682523656192",
        name="Test League",
        season="2025",
        last_updated=datetime.now(UTC)
    )
    db.session.add(league)
    db.session.commit()

    # Then create a user
    user = SleeperUser(
        league_id="1210364682523656192",
        user_id="736083244801474560",
        username="testuser",
        display_name="Test User",
        last_updated=datetime.now(UTC)
    )
    db.session.add(user)
    db.session.commit()

    # Test to_dict method
    user_dict = user.to_dict()
    assert user_dict['league_id'] == "1210364682523656192"
    assert user_dict['user_id'] == "736083244801474560"
    assert user_dict['username'] == "testuser"
    assert user_dict['display_name'] == "Test User"


def test_sleeper_league_roster_relationship(app_context):
    """Test relationship between SleeperLeague and SleeperRoster."""
    # Create league
    league = SleeperLeague(
        league_id="test_league",
        name="Test League",
        season="2024"
    )
    db.session.add(league)

    # Create roster
    roster = SleeperRoster(
        league_id="test_league",
        roster_id=1,
        owner_id="test_owner",
        players='["4881"]'
    )
    db.session.add(roster)
    db.session.commit()

    # Test that roster is associated with league
    assert roster.league_id == league.league_id
