"""
Integration test for Sleeper data saving functionality.

This test verifies that Sleeper data is properly saved to the database
and merged with existing KTC data.
"""
import json
from datetime import datetime, UTC
from models.entities import Player
from models.extensions import db
from managers.database_manager import DatabaseManager
from tests.fixtures.database import app_context


def test_sleeper_data_saving_integration(app_context):
    """Test that Sleeper data is properly saved to the database."""

    # Mock some Sleeper player data
    mock_sleeper_data = [
        {
            'sleeper_player_id': '4881',
            'full_name': 'Josh Allen',
            'position': 'QB',
            'team': 'BUF',
            'birth_date': '1996-05-21',
            'height': '6\'5"',
            'weight': '237',
            'college': 'Wyoming',
            'years_exp': 6,
            'number': 17,
            'depth_chart_order': 1,
            'depth_chart_position': 'QB',
            'fantasy_positions': json.dumps(['QB']),
            'hashtag': '#JoshAllen',
            'search_rank': 1,
            'high_school': 'Reedley High School',
            'rookie_year': 2018,
            'injury_status': None,
            'injury_start_date': None,
            'competitions': None,
            'injury_body_part': None,
            'injury_notes': None,
            'team_changed_at': None,
            'practice_participation': None,
            'search_first_name': 'Josh',
            'birth_state': 'California',
            'oddsjam_id': None,
            'practice_description': None,
            'opta_id': None,
            'search_full_name': 'Josh Allen',
            'espn_id': '3918298',
            'team_abbr': 'BUF',
            'search_last_name': 'Allen',
            'sportradar_id': 'sr:player:1234567',
            'swish_id': None,
            'birth_country': 'USA',
            'gsis_id': '00-0034857',
            'pandascore_id': None,
            'yahoo_id': '31007',
            'fantasy_data_id': '19638',
            'stats_id': '1049',
            'news_updated': 1640995200000,
            'birth_city': 'Firebaugh',
            'rotoworld_id': '13139',
            'rotowire_id': 13139,
            'status': 'Active',
            'player_metadata': json.dumps({'some': 'metadata'})
        },
        {
            'sleeper_player_id': '4035',
            'full_name': 'Christian McCaffrey',
            'position': 'RB',
            'team': 'SF',
            'birth_date': '1996-06-07',
            'height': '5\'11"',
            'weight': '205',
            'college': 'Stanford',
            'years_exp': 7,
            'number': 23,
            'depth_chart_order': 1,
            'depth_chart_position': 'RB',
            'fantasy_positions': json.dumps(['RB']),
            'hashtag': '#ChristianMcCaffrey',
            'search_rank': 2,
            'high_school': 'Valor Christian High School',
            'rookie_year': 2017,
            'injury_status': None,
            'injury_start_date': None,
            'competitions': None,
            'injury_body_part': None,
            'injury_notes': None,
            'team_changed_at': None,
            'practice_participation': None,
            'search_first_name': 'Christian',
            'birth_state': 'Colorado',
            'oddsjam_id': None,
            'practice_description': None,
            'opta_id': None,
            'search_full_name': 'Christian McCaffrey',
            'espn_id': '3116385',
            'team_abbr': 'SF',
            'search_last_name': 'McCaffrey',
            'sportradar_id': 'sr:player:2345678',
            'swish_id': None,
            'birth_country': 'USA',
            'gsis_id': '00-0033357',
            'pandascore_id': None,
            'yahoo_id': '30123',
            'fantasy_data_id': '18423',
            'stats_id': '891',
            'news_updated': 1640995200000,
            'birth_city': 'Castle Rock',
            'rotoworld_id': '12456',
            'rotowire_id': 12456,
            'status': 'Active',
            'player_metadata': json.dumps({'some': 'metadata'})
        }
    ]

    # Test the save_sleeper_data_to_db function
    result = DatabaseManager.save_sleeper_data_to_db(mock_sleeper_data)

    # Verify the result structure
    assert 'status' in result
    assert 'total_sleeper_players' in result
    assert 'existing_sleeper_records' in result
    assert 'updates_made' in result
    assert 'new_records_created' in result
    assert 'match_failures' in result
    assert 'total_processed' in result

    # Check that players were saved
    assert result['total_sleeper_players'] == 2
    # May be 0 if no KTC players to merge with
    assert result['total_processed'] >= 0

    # Verify players exist in database
    josh_allen = Player.query.filter_by(sleeper_player_id='4881').first()
    assert josh_allen is not None
    assert josh_allen.full_name == 'Josh Allen'
    assert josh_allen.position == 'QB'
    assert josh_allen.team == 'BUF'

    mccaffrey = Player.query.filter_by(sleeper_player_id='4035').first()
    assert mccaffrey is not None
    assert mccaffrey.full_name == 'Christian McCaffrey'
    assert mccaffrey.position == 'RB'
    assert mccaffrey.team == 'SF'


def test_sleeper_data_merge_with_existing_ktc(app_context):
    """Test that Sleeper data creates new records when no sleeper_player_id match exists."""

    # First create a KTC player record without sleeper_player_id
    ktc_player = Player(
        player_name='Josh Allen',
        position='QB',
        team='BUF',
        age=28.0,
        rookie='No',
        last_updated=datetime.now(UTC)
    )
    db.session.add(ktc_player)
    db.session.commit()

    # Now add Sleeper data for the same player (by name) but different ID
    mock_sleeper_data = [
        {
            'sleeper_player_id': '4881',
            'full_name': 'Josh Allen',
            'position': 'QB',
            'team': 'BUF',
            'birth_date': '1996-05-21',
            'height': '6\'5"',
            'weight': '237',
            'college': 'Wyoming',
            'years_exp': 6,
            'status': 'Active',
            'player_metadata': json.dumps({'some': 'metadata'})
        }
    ]

    # Test the save operation
    result = DatabaseManager.save_sleeper_data_to_db(mock_sleeper_data)

    # Should create a new record since no sleeper_player_id match exists
    assert result['status'] == 'success'
    assert result['new_records_created'] == 1
    assert result['updates_made'] == 0

    # Verify we now have two players (KTC original + new Sleeper record)
    all_players = Player.query.all()
    assert len(all_players) == 2

    # Verify the new Sleeper record was created
    sleeper_player = Player.query.filter_by(sleeper_player_id='4881').first()
    assert sleeper_player is not None
    assert sleeper_player.full_name == 'Josh Allen'
    assert sleeper_player.birth_date.strftime('%Y-%m-%d') == '1996-05-21'
    assert sleeper_player.height == '6\'5"'
