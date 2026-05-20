"""KTC refresh must not clobber Sleeper profile data; dynasty/redraft KTC rows are separate."""
from datetime import datetime, UTC

from managers.database_manager import DatabaseManager
from models.entities import Player, PlayerKTCSuperflexValues
from models.extensions import db
from utils.constants import PLAYER_NAME_KEY, POSITION_KEY, TEAM_KEY, AGE_KEY, ROOKIE_KEY


def test_ktc_merge_without_sleeper_match_preserves_sleeper_fields(app_context):
    player = Player(
        player_name='Josh Allen',
        position='QB',
        team='BUF',
        age=28.0,
        rookie='No',
        sleeper_player_id='4881',
        search_rank=12,
        height="6'5\"",
        college='Wyoming',
        last_updated=datetime.now(UTC),
    )
    db.session.add(player)
    db.session.commit()

    ktc_only = {
        PLAYER_NAME_KEY: 'Josh Allen',
        POSITION_KEY: 'QB',
        TEAM_KEY: 'BUF',
        AGE_KEY: 28.5,
        ROOKIE_KEY: 'No',
        'ktc_player_id': 999,
        'superflex_values': {'value': 8000, 'rank': 5},
    }

    DatabaseManager._update_existing_player_with_merged_data(
        player, ktc_only, is_redraft=False)
    db.session.commit()

    refreshed = Player.query.filter_by(sleeper_player_id='4881').one()
    assert refreshed.search_rank == 12
    assert refreshed.height == "6'5\""
    assert refreshed.college == 'Wyoming'
    assert refreshed.sleeper_player_id == '4881'
    assert refreshed.age == 28.5
    assert refreshed.ktc_player_id == 999


def test_ktc_dynasty_and_redraft_values_coexist(app_context):
    player = Player(
        player_name='Test Player',
        position='WR',
        team='MIN',
        sleeper_player_id='9001',
        last_updated=datetime.now(UTC),
    )
    db.session.add(player)
    db.session.commit()

    dynasty = {
        PLAYER_NAME_KEY: 'Test Player',
        POSITION_KEY: 'WR',
        TEAM_KEY: 'MIN',
        'superflex_values': {'value': 5000, 'rank': 50},
    }
    redraft = {
        PLAYER_NAME_KEY: 'Test Player',
        POSITION_KEY: 'WR',
        TEAM_KEY: 'MIN',
        'superflex_values': {'value': 1200, 'rank': 80},
    }

    DatabaseManager._update_existing_player_with_merged_data(
        player, dynasty, is_redraft=False)
    DatabaseManager._update_existing_player_with_merged_data(
        player, redraft, is_redraft=True)
    db.session.commit()

    rows = PlayerKTCSuperflexValues.query.filter_by(player_id=player.id).all()
    assert len(rows) == 2
    by_mode = {bool(r.is_redraft): r for r in rows}
    assert by_mode[False].value == 5000
    assert by_mode[False].rank == 50
    assert by_mode[True].value == 1200
    assert by_mode[True].rank == 80

    dynasty_players, _ = DatabaseManager.get_players_from_db(
        'superflex', is_redraft=False)
    redraft_players, _ = DatabaseManager.get_players_from_db(
        'superflex', is_redraft=True)
    assert len(dynasty_players) == 1
    assert len(redraft_players) == 1
    assert dynasty_players[0]._first_ktc_superflex_row(False).value == 5000
    assert redraft_players[0]._first_ktc_superflex_row(True).value == 1200
