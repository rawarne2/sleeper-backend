#!/usr/bin/env python3
"""
Test script to verify that Sleeper data is being saved to the database correctly.
"""

import os
import sys
import json
from datetime import datetime, UTC

# Set test database URI before importing app
os.environ['TEST_DATABASE_URI'] = 'sqlite:///:memory:'

from models import db, Player
from managers import DatabaseManager
from scrapers import SleeperScraper
from app import app

def test_sleeper_data_saving():
    """Test that Sleeper data is properly saved to the database."""
    
    print("🧪 Testing Sleeper data saving functionality...")
    
    with app.app_context():
        # Create tables
        db.create_all()
        
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
                'sportradar_id': 'sr:player:7654321',
                'swish_id': None,
                'birth_country': 'USA',
                'gsis_id': '00-0033357',
                'pandascore_id': None,
                'yahoo_id': '30123',
                'fantasy_data_id': '18618',
                'stats_id': '1048',
                'news_updated': 1640995200000,
                'birth_city': 'Castle Rock',
                'rotoworld_id': '12139',
                'rotowire_id': 12139,
                'status': 'Active',
                'player_metadata': json.dumps({'some': 'other_metadata'})
            }
        ]
        
        print(f"📊 Testing with {len(mock_sleeper_data)} mock Sleeper players...")
        
        # Test the save_sleeper_data_to_db function
        result = DatabaseManager.save_sleeper_data_to_db(mock_sleeper_data)
        
        print(f"💾 Save result: {result}")
        
        if result['status'] == 'success':
            print("✅ Sleeper data save operation completed successfully!")
            print(f"   - Total Sleeper players: {result['total_sleeper_players']}")
            print(f"   - Updates made: {result['updates_made']}")
            print(f"   - New records created: {result['new_records_created']}")
            print(f"   - Match failures: {result['match_failures']}")
            print(f"   - Total processed: {result['total_processed']}")
            
            # Verify data was actually saved
            saved_players = Player.query.filter(Player.sleeper_player_id.isnot(None)).all()
            print(f"🔍 Found {len(saved_players)} players with Sleeper data in database")
            
            for player in saved_players:
                print(f"   - {player.player_name} ({player.position}) - Sleeper ID: {player.sleeper_player_id}")
                print(f"     College: {player.college}, Height: {player.height}, Weight: {player.weight}")
                
            if len(saved_players) > 0:
                print("✅ SUCCESS: Sleeper data is now being saved to players!")
                assert True
            else:
                print("❌ FAILURE: No players with Sleeper data found in database")
                assert False, "No players with Sleeper data found in database"
        else:
            print(f"❌ FAILURE: Sleeper data save failed - {result.get('error', 'Unknown error')}")
            assert False, f"Sleeper data save failed - {result.get('error', 'Unknown error')}"

def test_sleeper_data_update():
    """Test that existing KTC players get updated with Sleeper data."""
    
    print("\n🧪 Testing Sleeper data update functionality...")
    
    with app.app_context():
        # Create a KTC player first
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
        
        print(f"📊 Created KTC player: {ktc_player.player_name}")
        print(f"   - Before update: Sleeper ID = {ktc_player.sleeper_player_id}")
        print(f"   - Before update: College = {ktc_player.college}")
        
        # Mock Sleeper data for the same player
        mock_sleeper_data = [{
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
            'player_metadata': json.dumps({'some': 'metadata'})
        }]
        
        # Update with Sleeper data
        result = DatabaseManager.save_sleeper_data_to_db(mock_sleeper_data)
        
        if result['status'] == 'success' and result['updates_made'] > 0:
            # Refresh the player from database
            updated_player = Player.query.filter_by(player_name='Josh Allen').first()
            
            print(f"   - After update: Sleeper ID = {updated_player.sleeper_player_id}")
            print(f"   - After update: College = {updated_player.college}")
            print(f"   - After update: Height = {updated_player.height}")
            print(f"   - After update: Weight = {updated_player.weight}")
            
            if updated_player.sleeper_player_id == '4881' and updated_player.college == 'Wyoming':
                print("✅ SUCCESS: Existing KTC player updated with Sleeper data!")
                assert True
            else:
                print("❌ FAILURE: KTC player was not properly updated with Sleeper data")
                assert False, "KTC player was not properly updated with Sleeper data"
        else:
            print(f"❌ FAILURE: Update operation failed - {result}")
            assert False, f"Update operation failed - {result}"

if __name__ == "__main__":
    print("🚀 Starting Sleeper data fix verification tests...\n")
    
    test1_passed = test_sleeper_data_saving()
    test2_passed = test_sleeper_data_update()
    
    print(f"\n📋 Test Results:")
    print(f"   - Sleeper data saving: {'✅ PASSED' if test1_passed else '❌ FAILED'}")
    print(f"   - Sleeper data updating: {'✅ PASSED' if test2_passed else '❌ FAILED'}")
    
    if test1_passed and test2_passed:
        print("\n🎉 ALL TESTS PASSED! The Sleeper data fix is working correctly!")
        sys.exit(0)
    else:
        print("\n💥 SOME TESTS FAILED! The fix needs more work.")
        sys.exit(1)
