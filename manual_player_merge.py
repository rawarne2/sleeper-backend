"""
Manual Player Merge Utility

This script handles manual merging of players that have different name variations
between KTC and Sleeper data sources that the automatic matching doesn't catch.

Examples:
- "Cam Ward" vs "Cameron Ward"
- "Kenneth Walker III" vs "Kenneth Walker"
- Other similar name variations

Usage:
    python manual_player_merge.py
"""

import logging
from typing import Dict, List, Tuple, Optional
from datetime import datetime, UTC

from app import app
from models import db, Player, PlayerKTCOneQBValues, PlayerKTCSuperflexValues
from utils import create_player_match_key
from data_types import normalize_name_for_matching

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Manual merge mappings - Add players that need manual merging here
# Format: (ktc_name, sleeper_name, position)
MANUAL_MERGE_MAPPINGS = [
    # QB mappings
    ("Cam Ward", "Cameron Ward", "QB"),
    
    # RB mappings  
    ("Kenneth Walker III", "Kenneth Walker", "RB"),
    
    # WR mappings
    ("Marquise Brown", "Hollywood Brown", "WR"),  # Hollywood is his nickname
    ("Calvin Austin III", "Calvin Austin", "WR"),
    ("Gabriel Davis", "Gabe Davis", "WR"),
    
    # TE mappings
    ("Chigoziem Okonkwo", "Chig Okonkwo", "TE"),
    
    # Add more mappings as needed
    # ("KTC Name", "Sleeper Name", "Position"),
]


class ManualPlayerMerger:
    """Handles manual merging of specific player records."""
    
    def __init__(self):
        self.app = app
        self.merged_count = 0
        self.error_count = 0
        self.errors = []
    
    def find_player_by_name_and_position(self, name: str, position: str) -> Optional[Player]:
        """
        Find a player by name and position using various matching strategies.
        
        Args:
            name: Player name to search for
            position: Player position
            
        Returns:
            Player record if found, None otherwise
        """
        position = position.upper()
        
        # Try exact match first
        player = Player.query.filter_by(player_name=name, position=position).first()
        if player:
            return player
        
        # Try match using full_name field
        player = Player.query.filter_by(full_name=name, position=position).first()
        if player:
            return player
        
        # Try normalized name matching
        match_key = create_player_match_key(name, position)
        player = Player.query.filter_by(match_key=match_key).first()
        if player:
            return player
        
        # Try fuzzy matching on normalized names
        normalized_search = normalize_name_for_matching(name)
        players = Player.query.filter_by(position=position).all()
        
        for player in players:
            # Check player_name
            if player.player_name and normalize_name_for_matching(player.player_name) == normalized_search:
                return player
            # Check full_name
            if player.full_name and normalize_name_for_matching(player.full_name) == normalized_search:
                return player
            # Check search_full_name
            if player.search_full_name and normalize_name_for_matching(player.search_full_name) == normalized_search:
                return player
        
        return None
    
    def merge_player_records(self, ktc_player: Player, sleeper_player: Player) -> bool:
        """
        Merge two player records by combining their data into the Sleeper-based record
        and deleting the KTC-only record.
        
        Args:
            ktc_player: Player record from KTC data (to be merged and deleted)
            sleeper_player: Player record from Sleeper data (to be kept and updated)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info("Merging players: KTC='%s' (%d) -> Sleeper='%s' (%d)", 
                       ktc_player.player_name, ktc_player.id,
                       sleeper_player.player_name, sleeper_player.id)
            
            # Transfer KTC-specific data to the Sleeper record
            if ktc_player.ktc_player_id and not sleeper_player.ktc_player_id:
                sleeper_player.ktc_player_id = ktc_player.ktc_player_id
            
            if ktc_player.age and not sleeper_player.age:
                sleeper_player.age = ktc_player.age
            
            if ktc_player.rookie and not sleeper_player.rookie:
                sleeper_player.rookie = ktc_player.rookie
            
            # Transfer KTC fields
            ktc_fields = [
                'slug', 'positionID', 'heightFeet', 'heightInches', 'seasonsExperience',
                'pickRound', 'pickNum', 'isFeatured', 'isStartSitFeatured', 'isTrending',
                'isDevyReturningToSchool', 'isDevyYearDecrement', 'teamLongName',
                'birthday', 'draftYear', 'byeWeek', 'injury'
            ]
            
            for field in ktc_fields:
                ktc_value = getattr(ktc_player, field, None)
                sleeper_value = getattr(sleeper_player, field, None)
                if ktc_value and not sleeper_value:
                    setattr(sleeper_player, field, ktc_value)
            
            # Transfer KTC ranking values
            if ktc_player.oneqb_values and not sleeper_player.oneqb_values:
                ktc_player.oneqb_values.player_id = sleeper_player.id
                sleeper_player.oneqb_values = ktc_player.oneqb_values
            
            if ktc_player.superflex_values and not sleeper_player.superflex_values:
                ktc_player.superflex_values.player_id = sleeper_player.id
                sleeper_player.superflex_values = ktc_player.superflex_values
            
            # Ensure match_key is set for efficient future lookups
            if not sleeper_player.match_key:
                sleeper_player.match_key = create_player_match_key(sleeper_player.player_name, sleeper_player.position)
            
            # Update timestamp
            sleeper_player.last_updated = datetime.now(UTC)
            
            # Delete the KTC-only record
            db.session.delete(ktc_player)
            
            # Commit the changes
            db.session.commit()
            
            logger.info("Successfully merged players: '%s' -> '%s'", 
                       ktc_player.player_name, sleeper_player.player_name)
            return True
            
        except Exception as e:
            logger.error("Failed to merge players '%s' and '%s': %s", 
                        ktc_player.player_name, sleeper_player.player_name, e)
            db.session.rollback()
            return False
    
    def process_manual_merges(self) -> Dict[str, any]:
        """
        Process all manual merge mappings.
        
        Returns:
            Dictionary with merge results
        """
        results = {
            'total_mappings': len(MANUAL_MERGE_MAPPINGS),
            'successful_merges': 0,
            'failed_merges': 0,
            'not_found': 0,
            'already_merged': 0,
            'errors': [],
            'merged_players': []
        }
        
        with self.app.app_context():
            for ktc_name, sleeper_name, position in MANUAL_MERGE_MAPPINGS:
                try:
                    logger.info("Processing mapping: KTC='%s' -> Sleeper='%s' (%s)", 
                               ktc_name, sleeper_name, position)
                    
                    # Find both players
                    ktc_player = self.find_player_by_name_and_position(ktc_name, position)
                    sleeper_player = self.find_player_by_name_and_position(sleeper_name, position)
                    
                    if not ktc_player:
                        logger.warning("KTC player not found: '%s' (%s)", ktc_name, position)
                        results['not_found'] += 1
                        continue
                    
                    if not sleeper_player:
                        logger.warning("Sleeper player not found: '%s' (%s)", sleeper_name, position)
                        results['not_found'] += 1
                        continue
                    
                    # Check if they're already the same record
                    if ktc_player.id == sleeper_player.id:
                        logger.info("Players already merged: '%s' (%s)", ktc_name, position)
                        results['already_merged'] += 1
                        continue
                    
                    # Check if both have Sleeper IDs (indicates they're both from Sleeper)
                    if ktc_player.sleeper_player_id and sleeper_player.sleeper_player_id:
                        logger.warning("Both players have Sleeper IDs - may need different merge strategy: '%s' and '%s'", 
                                     ktc_name, sleeper_name)
                        results['errors'].append(f"Both {ktc_name} and {sleeper_name} have Sleeper IDs")
                        results['failed_merges'] += 1
                        continue
                    
                    # Determine which record to keep (prefer the one with Sleeper ID)
                    if sleeper_player.sleeper_player_id and not ktc_player.sleeper_player_id:
                        # Merge ktc_player into sleeper_player
                        source_player = ktc_player
                        target_player = sleeper_player
                    elif ktc_player.sleeper_player_id and not sleeper_player.sleeper_player_id:
                        # Merge sleeper_player into ktc_player
                        source_player = sleeper_player
                        target_player = ktc_player
                    else:
                        # Neither has Sleeper ID, or both don't - prefer the one found by sleeper_name
                        source_player = ktc_player
                        target_player = sleeper_player
                    
                    # Perform the merge
                    if self.merge_player_records(source_player, target_player):
                        results['successful_merges'] += 1
                        results['merged_players'].append({
                            'ktc_name': ktc_name,
                            'sleeper_name': sleeper_name,
                            'position': position,
                            'merged_into': target_player.player_name
                        })
                    else:
                        results['failed_merges'] += 1
                        
                except Exception as e:
                    error_msg = f"Error processing mapping {ktc_name} -> {sleeper_name}: {e}"
                    logger.error(error_msg)
                    results['errors'].append(error_msg)
                    results['failed_merges'] += 1
                    continue
        
        return results
    
    def find_potential_duplicates(self, limit: int = 50) -> List[Dict[str, any]]:
        """
        Find potential duplicate players that might need manual merging.
        
        Args:
            limit: Maximum number of potential duplicates to return
            
        Returns:
            List of potential duplicate groups
        """
        with self.app.app_context():
            # Find players with similar normalized names in the same position
            duplicates = []
            
            # Get all players grouped by position
            positions = ['QB', 'RB', 'WR', 'TE']
            
            for position in positions:
                players = Player.query.filter_by(position=position).all()
                
                # Group by normalized name
                name_groups = {}
                for player in players:
                    if player.player_name:
                        normalized = normalize_name_for_matching(player.player_name)
                        if normalized not in name_groups:
                            name_groups[normalized] = []
                        name_groups[normalized].append(player)
                
                # Also check full_name if different from player_name
                for player in players:
                    if player.full_name and player.full_name != player.player_name:
                        normalized = normalize_name_for_matching(player.full_name)
                        if normalized not in name_groups:
                            name_groups[normalized] = []
                        if player not in name_groups[normalized]:
                            name_groups[normalized].append(player)
                
                # Find groups with multiple players
                for normalized_name, group_players in name_groups.items():
                    if len(group_players) > 1:
                        # Check if they're actually different players (different sleeper_player_ids)
                        sleeper_ids = set()
                        for p in group_players:
                            if p.sleeper_player_id:
                                sleeper_ids.add(p.sleeper_player_id)
                        
                        # If they have different Sleeper IDs, they're different people
                        if len(sleeper_ids) > 1:
                            continue
                            
                        # If some have no Sleeper ID, they might be duplicates
                        duplicates.append({
                            'normalized_name': normalized_name,
                            'position': position,
                            'players': [
                                {
                                    'id': p.id,
                                    'player_name': p.player_name,
                                    'full_name': p.full_name,
                                    'sleeper_player_id': p.sleeper_player_id,
                                    'ktc_player_id': p.ktc_player_id,
                                    'has_oneqb': bool(p.oneqb_values),
                                    'has_superflex': bool(p.superflex_values)
                                }
                                for p in group_players
                            ]
                        })
                        
                        if len(duplicates) >= limit:
                            break
                
                if len(duplicates) >= limit:
                    break
            
            return duplicates[:limit]


def main():
    """Main function to run manual player merging."""
    print("=== Manual Player Merge Utility ===")
    print(f"Processing {len(MANUAL_MERGE_MAPPINGS)} manual merge mappings...")
    
    merger = ManualPlayerMerger()
    
    # Process manual merges
    results = merger.process_manual_merges()
    
    # Print results
    print("\n=== Merge Results ===")
    print(f"Total mappings processed: {results['total_mappings']}")
    print(f"Successful merges: {results['successful_merges']}")
    print(f"Failed merges: {results['failed_merges']}")
    print(f"Players not found: {results['not_found']}")
    print(f"Already merged: {results['already_merged']}")
    
    if results['merged_players']:
        print("\n=== Successfully Merged Players ===")
        for merge in results['merged_players']:
            print(f"  • {merge['ktc_name']} -> {merge['sleeper_name']} ({merge['position']}) = {merge['merged_into']}")
    
    if results['errors']:
        print("\n=== Errors ===")
        for error in results['errors']:
            print(f"  • {error}")
    
    # Find potential duplicates for review
    print("\n=== Finding Potential Duplicates ===")
    duplicates = merger.find_potential_duplicates(limit=10)
    
    if duplicates:
        print(f"Found {len(duplicates)} potential duplicate groups:")
        for dup in duplicates:
            print(f"\nPosition: {dup['position']}, Normalized name: '{dup['normalized_name']}'")
            for player in dup['players']:
                sleeper_id = player['sleeper_player_id'] or 'None'
                ktc_id = player['ktc_player_id'] or 'None'
                values = []
                if player['has_oneqb']:
                    values.append('1QB')
                if player['has_superflex']:
                    values.append('SF')
                values_str = ','.join(values) if values else 'No values'
                
                print(f"  • ID:{player['id']} '{player['player_name']}' (full: '{player['full_name']}') "
                      f"Sleeper:{sleeper_id} KTC:{ktc_id} Values:{values_str}")
    else:
        print("No potential duplicates found.")
    
    print("\n=== Manual Merge Complete ===")


if __name__ == "__main__":
    main()
