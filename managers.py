import json
import os
import tempfile
from datetime import datetime, UTC
from typing import Dict, List, Optional, Any

import boto3
from botocore.exceptions import NoCredentialsError, ClientError
from sqlalchemy import text

from models import db, Player, PlayerKTCOneQBValues, PlayerKTCSuperflexValues
from utils import (normalize_tep_level, PLAYER_NAME_KEY, POSITION_KEY, TEAM_KEY,
                   AGE_KEY, ROOKIE_KEY, setup_logging)

logger = setup_logging()


class PlayerMerger:
    """
    Handles merging KTC and Sleeper player data.

    Matches players by name, using birth date and position to distinguish
    players with the same name.
    """


    @staticmethod
    def merge_player_data(ktc_players: List[Dict[str, Any]], sleeper_players: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Merge KTC and Sleeper player data using improved matching logic.
        
        Uses search_full_name for better player matching to avoid duplicates like
        "Ja'Marr Chase" vs "Ja\u0027Marr" creating separate entries.
        
        Filters players to only include those in valid fantasy positions.
        Prefers KTC's age value over Sleeper's since KTC includes decimals.

        Args:
            ktc_players: List of KTC player data
            sleeper_players: List of Sleeper player data

        Returns:
            List of merged player data (filtered for valid positions)
        """
        try:
            from scrapers import SleeperScraper
            
            # Filter KTC players to only include valid positions
            valid_ktc_players = []
            for ktc_player in ktc_players:
                position = ktc_player.get(POSITION_KEY, '').upper()
                if position in SleeperScraper.VALID_POSITIONS:
                    valid_ktc_players.append(ktc_player)
                else:
                    logger.debug("Filtering out KTC player %s with invalid position: %s", 
                               ktc_player.get(PLAYER_NAME_KEY, 'Unknown'), position)
            
            logger.info("Filtered KTC players: %s valid out of %s total", 
                       len(valid_ktc_players), len(ktc_players))

            # Create lookup dictionary for Sleeper players using search_full_name
            sleeper_lookup = {}
            sleeper_name_fallback = {}  # Fallback using normalized KTC names

            for sleeper_player in sleeper_players:
                position = sleeper_player.get('position', '').upper()
                
                if position not in SleeperScraper.VALID_POSITIONS:
                    continue
                
                search_full_name = sleeper_player.get('search_full_name', '')
                
                # Create match key using search_full_name (already normalized by Sleeper)
                if search_full_name:
                    match_key = f"{search_full_name.lower()}-{position}"
                    sleeper_lookup[match_key] = sleeper_player
                
                # Also create fallback lookup using full_name normalization
                full_name = sleeper_player.get('full_name', '')
                if full_name:
                    from utils import create_player_match_key
                    fallback_key = create_player_match_key(full_name, position)
                    if fallback_key not in sleeper_name_fallback:
                        sleeper_name_fallback[fallback_key] = []
                    sleeper_name_fallback[fallback_key].append(sleeper_player)

            logger.info("Created Sleeper lookup with %s search_full_name keys and %s fallback keys",
                        len(sleeper_lookup), len(sleeper_name_fallback))

            # Merge data
            merged_players = []
            matched_count = 0
            duplicate_prevention = set()  # Track processed players to prevent duplicates

            for ktc_player in valid_ktc_players:
                player_name = ktc_player.get(PLAYER_NAME_KEY, '')
                position = ktc_player.get(POSITION_KEY, '').upper()
                
                # Create duplicate prevention key using centralized function
                from utils import create_player_match_key
                duplicate_key = create_player_match_key(player_name, position)
                if duplicate_key in duplicate_prevention:
                    logger.debug("Skipping duplicate KTC player: %s (%s)", player_name, position)
                    continue
                duplicate_prevention.add(duplicate_key)

                # Try to find matching Sleeper player using centralized match key
                sleeper_match = None
                search_key = create_player_match_key(player_name, position)
                
                if search_key in sleeper_lookup:
                    sleeper_match = sleeper_lookup[search_key]
                elif search_key in sleeper_name_fallback:
                    # Use fallback matching
                    candidates = sleeper_name_fallback[search_key]
                    if len(candidates) == 1:
                        sleeper_match = candidates[0]
                    else:
                        # Multiple candidates - log for manual review
                        logger.warning("Multiple Sleeper matches for %s (%s): %s candidates",
                                       player_name, position, len(candidates))
                        sleeper_match = candidates[0]  # Take first match

                # Create merged player data
                merged_player = ktc_player.copy()

                if sleeper_match:
                    # Map Sleeper data to merged player
                    # Note: Sleeper API uses 'player_id' as the key, we need to map it to 'sleeper_player_id'
                    merged_player['sleeper_player_id'] = sleeper_match.get('player_id')
                    
                    # Add Sleeper data fields, but prefer KTC age if available
                    sleeper_keys = [
                        'birth_date', 'height', 'weight', 'college',
                        'years_exp', 'number', 'depth_chart_order',
                        'depth_chart_position', 'fantasy_positions', 'hashtag',
                        'search_rank', 'high_school', 'injury_status', 'injury_start_date',
                        'full_name', 'status', 'team_abbr', 'competitions', 'injury_body_part',
                        'injury_notes', 'team_changed_at', 'practice_participation',
                        'search_first_name', 'birth_state', 'oddsjam_id',
                        'practice_description', 'opta_id', 'search_full_name',
                        'espn_id', 'search_last_name', 'sportradar_id', 'swish_id',
                        'birth_country', 'gsis_id', 'pandascore_id', 'yahoo_id',
                        'fantasy_data_id', 'stats_id', 'news_updated', 'birth_city',
                        'rotoworld_id', 'rotowire_id'
                    ]
                    
                    for key in sleeper_keys:
                        if key in sleeper_match:
                            # Special handling for age - prefer KTC's more precise age
                            if key == 'age' and merged_player.get(AGE_KEY) is not None:
                                # Keep KTC age (more precise with decimals)
                                continue
                            merged_player[key] = sleeper_match[key]
                    
                    # Extract rookie_year from metadata if available
                    metadata = sleeper_match.get('metadata', {})
                    if isinstance(metadata, dict) and metadata.get('rookie_year'):
                        merged_player['rookie_year'] = metadata['rookie_year']
                    
                    # Store the complete metadata as JSON string
                    if metadata:
                        merged_player['player_metadata'] = json.dumps(metadata)

                    matched_count += 1

                merged_players.append(merged_player)

            logger.info("Successfully merged %s KTC players with %s Sleeper matches (filtered for valid positions)",
                        len(valid_ktc_players), matched_count)
            return merged_players

        except Exception as e:
            logger.error("Error merging player data: %s", e)
            return ktc_players  # Return original KTC data if merge fails


class FileManager:
    """Handles file operations for JSON data storage and S3 uploads."""

    @staticmethod
    def get_data_directory() -> str:
        """Get the appropriate data directory path based on environment."""
        return '/app/data-files' if os.path.exists('/app') else './data-files'

    @staticmethod
    def create_json_filename(league_format: str, is_redraft: bool, tep_level: Optional[str], prefix: str = "ktc") -> str:
        """
        Create standardized JSON filename with improved accuracy and descriptiveness.

        Args:
            league_format: '1qb' or 'superflex'
            is_redraft: Whether this is redraft data
            tep_level: TEP configuration level
            prefix: Filename prefix

        Returns:
            Standardized filename string with timestamp and descriptive naming
        """
        # Get current timestamp for unique identification
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")

        # More descriptive format type
        format_type = 'redraft' if is_redraft else 'dynasty'

        # More descriptive league format
        league_desc = 'superflex' if league_format == 'superflex' else '1qb'

        # Use raw TEP level
        tep_suffix = tep_level if tep_level else "no_tep"

        # Create descriptive filename
        filename = f"{prefix}_{league_desc}_{format_type}_{tep_suffix}_{timestamp}.json"

        return filename

    @staticmethod
    def create_descriptive_filename(league_format: str, is_redraft: bool, tep_level: Optional[str],
                                    operation_type: str = "refresh", include_timestamp: bool = True) -> str:
        """
        Create a more descriptive filename with additional context and options.

        Args:
            league_format: '1qb' or 'superflex'
            is_redraft: Whether this is redraft data
            tep_level: TEP configuration level
            operation_type: Type of operation ('refresh', 'export', 'backup', etc.)
            include_timestamp: Whether to include timestamp in filename

        Returns:
            Descriptive filename string
        """
        # Get current timestamp if requested
        timestamp = datetime.now(UTC).strftime(
            "%Y%m%d_%H%M%S") if include_timestamp else ""

        # More descriptive format type
        format_type = 'redraft' if is_redraft else 'dynasty'

        # More descriptive league format
        league_desc = 'superflex' if league_format == 'superflex' else '1qb'

        # Use raw TEP level
        tep_desc = tep_level if tep_level else "no_tep"

        # Build filename components
        components = ['ktc', operation_type,
                      league_desc, format_type, tep_desc]

        # Add timestamp if requested
        if timestamp:
            components.append(timestamp)

        # Create filename
        filename = f"{'_'.join(components)}.json"

        return filename

    @staticmethod
    def create_human_readable_filename(league_format: str, is_redraft: bool, tep_level: Optional[str],
                                       operation_type: str = "refresh") -> str:
        """
        Create a human-readable filename with spaces and proper formatting.

        Args:
            league_format: '1qb' or 'superflex'
            is_redraft: Whether this is redraft data
            tep_level: TEP configuration level
            operation_type: Type of operation ('refresh', 'export', 'backup', etc.)

        Returns:
            Human-readable filename string
        """
        # Get current timestamp
        timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H-%M-%S")

        # Human-readable format type
        format_type = 'Redraft' if is_redraft else 'Dynasty'

        # Human-readable league format
        league_desc = 'Superflex' if league_format == 'superflex' else '1QB'

        # Use raw TEP level
        tep_desc = tep_level if tep_level else "No TEP"

        # Create human-readable filename
        filename = f"KTC {operation_type.title()} - {league_desc} {format_type} {tep_desc} - {timestamp}.json"

        return filename

    @staticmethod
    def save_json_to_file(json_data: Dict[str, Any], filename: str) -> bool:
        """
        Save JSON data to a local file in the data-files directory.
        Only saves files if IS_DEV environment variable is set to 'true'.

        Args:
            json_data: Data to save as JSON
            filename: Target filename

        Returns:
            True if successful or skipped (not dev mode), False on error
        """
        # Check if we're in development mode
        is_dev = os.getenv('IS_DEV', '').lower() == 'true'
        
        if not is_dev:
            logger.info("Skipping file save to data-files (not in dev mode): %s", filename)
            return True  # Return True since this is expected behavior in production
        
        try:
            data_dir = FileManager.get_data_directory()
            os.makedirs(data_dir, exist_ok=True)
            file_path = os.path.join(data_dir, filename)

            logger.info("Saving JSON data to %s...", file_path)
            with open(file_path, 'w') as json_file:
                json.dump(json_data, json_file, indent=2, default=str)

            logger.info("Successfully saved JSON data to %s", file_path)
            return True
        except Exception as e:
            logger.error("Error saving JSON to file: %s", e)
            return False

    @staticmethod
    def upload_json_to_s3(json_data: Dict[str, Any], bucket_name: str, object_key: str) -> bool:
        """
        Upload JSON data to an S3 bucket or access point.

        Args:
            json_data: Data to upload as JSON
            bucket_name: S3 bucket name or access point alias
            object_key: S3 object key (filename)

        Returns:
            True if successful, False otherwise
        """
        temp_file_path = None
        try:
            s3_client = boto3.client('s3')

            # Create temporary file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as temp_file:
                json.dump(json_data, temp_file, indent=2, default=str)
                temp_file_path = temp_file.name

            logger.info(
                f"Uploading JSON to s3://{bucket_name}/{object_key}...")

            # Upload to S3
            s3_client.upload_file(temp_file_path, bucket_name, object_key)
            logger.info(
                f"Successfully uploaded JSON to s3://{bucket_name}/{object_key}")

            return True

        except NoCredentialsError:
            logger.error(
                "AWS credentials not found. Make sure you've configured your AWS credentials.")
            return False
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            error_message = e.response.get(
                'Error', {}).get('Message', 'Unknown error')
            logger.error(
                f"S3 ClientError - Code: {error_code}, Message: {error_message}")
            return False
        except Exception as e:
            logger.error("Unexpected error uploading to S3: %s", e)
            return False
        finally:
            # Clean up temporary file
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.unlink(temp_file_path)
                except Exception as cleanup_error:
                    logger.warning(
                        f"Failed to cleanup temp file {temp_file_path}: {cleanup_error}")


class DatabaseManager:
    """
    Handles database operations for KTC player data with Sleeper integration.

    Provides methods for saving, retrieving, and managing player data
    in the PostgreSQL database with proper error handling and validation.
    """

    @staticmethod
    def verify_database_connection() -> bool:
        """
        Verify database connection and basic functionality.

        Returns:
            True if connection is successful, False otherwise
        """
        try:
            # Test basic query
            db.session.execute(text("SELECT 1")).fetchone()
            logger.info("Database connection verified successfully")
            return True
        except Exception as e:
            logger.error("Database connection verification failed: %s", e)
            return False

    @staticmethod
    def get_players_from_db(league_format: str) -> tuple[List[Player], Optional[datetime]]:
        """
        Retrieve players from database for specific configuration.

        Args:
            league_format: '1qb' or 'superflex'

        Returns:
            Tuple of (players_list, last_updated_timestamp)
        """
        # Query players with appropriate joins for ordering
        # Filter to only return players that have values for the requested format
        if league_format == '1qb':
            players = Player.query.join(PlayerKTCOneQBValues).order_by(
                PlayerKTCOneQBValues.rank.asc()
            ).all()
        else:  # superflex
            players = Player.query.join(PlayerKTCSuperflexValues).order_by(
                PlayerKTCSuperflexValues.rank.asc()
            ).all()

        # Filter players that have the appropriate values based on league format
        filtered_players = []
        for player in players:
            if league_format == '1qb' and player.oneqb_values:
                filtered_players.append(player)
            elif league_format == 'superflex' and player.superflex_values:
                filtered_players.append(player)

        last_updated = max(
            player.last_updated for player in filtered_players) if filtered_players else None
        return filtered_players, last_updated


    @staticmethod
    def _validate_save_inputs(players: List[Dict[str, Any]], league_format: str, tep_level: Optional[str]) -> Optional[str]:
        """
        Validate inputs for save operation.

        Args:
            players: List of player data
            league_format: League format string
            tep_level: TEP level string

        Returns:
            Normalized TEP level string

        Raises:
            ValueError: If validation fails
        """
        if not players:
            raise ValueError("No players provided to save")
        if not league_format:
            raise ValueError("League format is required")

        return normalize_tep_level(tep_level)



    @staticmethod
    def save_players_to_db(players: List[Dict[str, Any]], league_format: str, is_redraft: bool) -> int:
        """
        Save KTC player data to database using upsert logic.
        
        This function saves KTC rankings data merged with Sleeper data. Instead of deleting
        and recreating records, it updates existing records or creates new ones as needed.
        This approach is cleaner and avoids unnecessary data deletion.

        Args:
            players: List of player data dictionaries (merged KTC + Sleeper data)
            league_format: '1qb' or 'superflex'
            is_redraft: Whether this is redraft data

        Returns:
            Number of players processed (added or updated)

        Raises:
            Exception: If save operation fails
        """
        if not players:
            raise ValueError("No players provided to save")
        
        logger.info("Starting KTC data save: %s players for %s %s format", 
                   len(players), "redraft" if is_redraft else "dynasty", league_format)

        processed_count = 0
        skipped_count = 0
        
        try:
            # Verify database connection
            if not DatabaseManager.verify_database_connection():
                raise Exception("Database connection verification failed")

            # Create tables if they don't exist
            db.create_all()

            # Process each player with upsert logic
            for i, player_data in enumerate(players):
                try:
                    # Validate required fields
                    player_name = player_data.get(PLAYER_NAME_KEY)
                    position = player_data.get(POSITION_KEY)

                    if not player_name or not position:
                        logger.warning("Skipping player #%s: missing name or position", i+1)
                        skipped_count += 1
                        continue

                    # Check if we have KTC values for this league format
                    has_values = False
                    if league_format == '1qb' and player_data.get('oneqb_values'):
                        has_values = True
                    elif league_format == 'superflex' and player_data.get('superflex_values'):
                        has_values = True

                    if not has_values:
                        logger.debug("Skipping player %s - no %s values", player_name, league_format)
                        skipped_count += 1
                        continue

                    # Look for existing player record using normalized name matching
                    # Since we're saving KTC data merged with Sleeper data, we need to find existing
                    # players using normalized names to handle cases like "Kenneth Walker III" vs "Kenneth Walker"
                    existing_player = None
                    sleeper_id = player_data.get('sleeper_player_id')
                    
                    # First try sleeper_player_id if available (most reliable for merged data)
                    if sleeper_id:
                        existing_player = Player.query.filter_by(sleeper_player_id=sleeper_id).first()
                    
                    # If no sleeper_id match, use efficient match_key lookup
                    if not existing_player:
                        from utils import create_player_match_key
                        
                        # Create match key for KTC player
                        match_key = create_player_match_key(player_name, position)
                        
                        # Single efficient database query using indexed match_key
                        existing_player = Player.query.filter_by(match_key=match_key).first()

                    if existing_player:
                        # Update existing player and ensure match_key is set
                        DatabaseManager._update_existing_player_with_merged_data(existing_player, player_data)
                        # Ensure match_key is set for efficient future lookups
                        if not existing_player.match_key:
                            from utils import create_player_match_key
                            existing_player.match_key = create_player_match_key(player_name, position)
                        logger.debug("Updated existing player: %s", player_name)
                    else:
                        # Create new non-sleeper player (rare)
                        new_player = DatabaseManager._create_player_with_merged_data(player_data, league_format, is_redraft)
                        # Set match_key for efficient future lookups
                        from utils import create_player_match_key
                        new_player.match_key = create_player_match_key(player_name, position)
                        logger.debug("Created new non-sleeper player: %s", player_name)

                    processed_count += 1

                except Exception as player_error:
                    logger.error("Error processing player #%s (%s): %s", 
                               i+1, player_data.get(PLAYER_NAME_KEY, 'Unknown'), player_error)
                    skipped_count += 1
                    continue

            # Commit all changes
            logger.info("Committing %s player records to database...", processed_count)
            db.session.commit()
            logger.info("Successfully saved %s players (%s skipped)", processed_count, skipped_count)

            return processed_count

        except Exception as e:
            logger.error("Database save operation failed: %s", e)
            try:
                db.session.rollback()
                logger.info("Database rollback completed")
            except Exception as rollback_error:
                logger.error("Database rollback failed: %s", rollback_error)
            
            raise Exception(f"Failed to save KTC data: {e}")

    @staticmethod
    def get_database_stats() -> Dict[str, Any]:
        """
        Get database statistics for debugging and monitoring.

        Returns:
            Dictionary containing database statistics
        """
        try:
            stats = {}

            # Get total record count
            total_records = Player.query.count()
            stats['total_records'] = total_records

            # Get counts of players with Sleeper IDs
            sleeper_players_count = Player.query.filter(Player.sleeper_player_id.isnot(None)).count()
            stats['sleeper_players_count'] = sleeper_players_count

            # Get counts of players with KTC values
            oneqb_players_count = Player.query.join(PlayerKTCOneQBValues).count()
            superflex_players_count = Player.query.join(PlayerKTCSuperflexValues).count()
            
            stats['oneqb_players_count'] = oneqb_players_count
            stats['superflex_players_count'] = superflex_players_count

            # Get counts by position
            position_counts = db.session.query(
                Player.position,
                db.func.count(Player.id).label('count')
            ).group_by(Player.position).all()

            stats['position_breakdown'] = [
                {
                    'position': pos.position,
                    'count': pos.count
                }
                for pos in position_counts
            ]

            return stats

        except Exception as e:
            logger.error("Error getting database stats: %s", e)
            return {'error': str(e)}

    @staticmethod
    def cleanup_incomplete_data(league_format: str, is_redraft: bool, tep_level: Optional[str]) -> Dict[str, Any]:
        """
        Clean up potentially incomplete or corrupted data for a specific configuration.

        Args:
            league_format: '1qb' or 'superflex'
            is_redraft: Whether this is redraft data
            tep_level: TEP configuration level

        Returns:
            Dictionary containing cleanup results and statistics
        """
        try:
            normalized_tep = normalize_tep_level(tep_level)
            logger.info(
                "Starting cleanup for %s, redraft=%s, tep_level=%s", league_format, is_redraft, tep_level)

            # Get current count of all players
            current_count = Player.query.count()

            # Find records with missing critical data or missing value relationships
            if league_format == '1qb':
                incomplete_records = Player.query.outerjoin(PlayerKTCOneQBValues).filter(
                    db.or_(
                        Player.player_name.is_(None),
                        Player.player_name == '',
                        Player.position.is_(None),
                        Player.position == '',
                        # Remove players that should have 1QB values but don't
                        db.and_(
                            Player.sleeper_player_id.isnot(None),  # Only check Sleeper-based players
                            PlayerKTCOneQBValues.id.is_(None)
                        )
                    )
                ).all()
            else:  # superflex
                incomplete_records = Player.query.outerjoin(PlayerKTCSuperflexValues).filter(
                    db.or_(
                        Player.player_name.is_(None),
                        Player.player_name == '',
                        Player.position.is_(None),
                        Player.position == '',
                        # Remove players that should have Superflex values but don't
                        db.and_(
                            Player.sleeper_player_id.isnot(None),  # Only check Sleeper-based players
                            PlayerKTCSuperflexValues.id.is_(None)
                        )
                    )
                ).all()

            incomplete_count = len(incomplete_records)

            # Remove incomplete records if found
            if incomplete_count > 0:
                logger.warning(
                    "Found %s incomplete records, removing them...", incomplete_count)
                for record in incomplete_records:
                    db.session.delete(record)
                db.session.commit()
                logger.info("Removed %s incomplete records", incomplete_count)

            # Get final count
            final_count = Player.query.count()

            return {
                'status': 'success',
                'initial_count': current_count,
                'incomplete_removed': incomplete_count,
                'final_count': final_count,
                'configuration': {
                    'league_format': league_format,
                    'is_redraft': is_redraft,
                    'tep_level': tep_level
                }
            }

        except Exception as e:
            logger.error("Error during cleanup: %s", e)
            db.session.rollback()
            return {
                'status': 'error',
                'error': str(e),
                'configuration': {
                    'league_format': league_format,
                    'is_redraft': is_redraft,
                    'tep_level': tep_level
                }
            }

    @staticmethod
    def save_sleeper_data_to_db(sleeper_players: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Save Sleeper player data to database as base datasource.
        
        Since Sleeper is the base datasource, we create/update player records with Sleeper data
        and then merge any existing KTC data into these Sleeper-based records.
        """
        try:
            logger.info(
                "Starting Sleeper data save with %s players...", len(sleeper_players))

            existing_sleeper_count = Player.query.filter(
                Player.sleeper_player_id.isnot(None)).count()

            updates_made = 0
            new_records_created = 0
            match_failures = 0

            # Process in batches for better performance
            batch_size = 100
            for i in range(0, len(sleeper_players), batch_size):
                batch = sleeper_players[i:i + batch_size]
                batch_results = DatabaseManager._process_sleeper_batch(batch)

                updates_made += batch_results['updates']
                new_records_created += batch_results['new_records']
                match_failures += batch_results['match_failures']

                db.session.commit()

            logger.info("Sleeper data save completed: %s updates, %s new records, %s failures",
                        updates_made, new_records_created, match_failures)

            return {
                'status': 'success',
                'total_sleeper_players': len(sleeper_players),
                'existing_sleeper_records': existing_sleeper_count,
                'updates_made': updates_made,
                'new_records_created': new_records_created,
                'match_failures': match_failures,
                'total_processed': updates_made + new_records_created
            }

        except Exception as e:
            db.session.rollback()
            logger.error("Error saving Sleeper data: %s", e)
            return {
                'status': 'error',
                'error': str(e),
                'total_sleeper_players': len(sleeper_players) if sleeper_players else 0
            }

    @staticmethod
    def save_league_data(league_data: Dict[str, Any]) -> Dict[str, Any]:
        """Save comprehensive league data to database."""
        if not league_data.get('success'):
            return {'status': 'error', 'error': 'League data fetch failed'}

        try:
            league_info = league_data['league_info']
            league_id = league_info['league_id']

            logger.info("Saving league data for league_id: %s", league_id)

            # Save all data in single transaction
            league_result = DatabaseManager._save_league_info(league_info)
            rosters_result = DatabaseManager._save_league_rosters(
                league_id, league_data.get('rosters', []))
            users_result = DatabaseManager._save_league_users(
                league_id, league_data.get('users', []))

            db.session.commit()

            return {
                'status': 'success',
                'league_id': league_id,
                'league_saved': league_result['saved'],
                'league_updated': league_result['updated'],
                'rosters_saved': rosters_result['saved'],
                'rosters_updated': rosters_result['updated'],
                'users_saved': users_result['saved'],
                'users_updated': users_result['updated']
            }

        except Exception as e:
            db.session.rollback()
            logger.error("Error saving league data: %s", e)
            return {'status': 'error', 'error': str(e)}

    @staticmethod
    def _upsert_record(model_class, filter_criteria: Dict[str, Any], data: Dict[str, Any]) -> Dict[str, Any]:
        """Generic upsert helper to reduce duplicate code."""
        existing = model_class.query.filter_by(**filter_criteria).first()

        if existing:
            # Update existing record
            for key, value in data.items():
                setattr(existing, key, value)
            setattr(existing, 'last_updated', datetime.now(UTC))
            return {'saved': False, 'updated': True}
        else:
            # Create new record
            new_record = model_class(**data)
            db.session.add(new_record)
            return {'saved': True, 'updated': False}

    @staticmethod
    def _save_league_info(league_info: Dict[str, Any]) -> Dict[str, Any]:
        """Save league information to database."""
        from models import SleeperLeague

        league_id = league_info['league_id']
        data = {
            'league_id': league_id,
            'name': league_info.get('name'),
            'season': league_info.get('season'),
            'total_rosters': league_info.get('total_rosters'),
            'roster_positions': json.dumps(league_info.get('roster_positions')),
            'status': league_info.get('status'),
            'draft_id': league_info.get('draft_id'),
            'avatar': league_info.get('avatar'),
            'last_refreshed': datetime.now(UTC)
        }

        return DatabaseManager._upsert_record(
            SleeperLeague,
            {'league_id': league_id},
            data
        )

    @staticmethod
    def _save_league_rosters(league_id: str, rosters_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Save league rosters to database using upsert."""
        from models import SleeperRoster

        saved_count = 0
        updated_count = 0

        for roster_data in rosters_data:
            data = {
                'league_id': league_id,
                'roster_id': roster_data.get('roster_id'),
                'owner_id': roster_data.get('owner_id'),
                'players': json.dumps(roster_data.get('players', [])),
                'starters': json.dumps(roster_data.get('starters', [])),
                'reserve': json.dumps(roster_data.get('reserve', [])),
                'taxi': json.dumps(roster_data.get('taxi', [])),
                'metadata': json.dumps(roster_data.get('metadata', {})),
                'settings': json.dumps(roster_data.get('settings', {}))
            }

            result = DatabaseManager._upsert_record(
                SleeperRoster,
                {'league_id': league_id,
                    'roster_id': roster_data.get('roster_id')},
                data
            )

            if result['saved']:
                saved_count += 1
            else:
                updated_count += 1

        return {'saved': saved_count, 'updated': updated_count}

    @staticmethod
    def _save_league_users(league_id: str, users_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Save league users to database using upsert."""
        from models import SleeperUser

        saved_count = 0
        updated_count = 0

        for user_data in users_data:
            data = {
                'league_id': league_id,
                'user_id': user_data.get('user_id'),
                'username': user_data.get('username'),
                'display_name': user_data.get('display_name'),
                'avatar': user_data.get('avatar'),
                'team_name': user_data.get('metadata', {}).get('team_name'),
                'user_metadata': json.dumps(user_data.get('metadata'))
            }

            result = DatabaseManager._upsert_record(
                SleeperUser,
                {'league_id': league_id, 'user_id': user_data.get('user_id')},
                data
            )

            if result['saved']:
                saved_count += 1
            else:
                updated_count += 1

        return {'saved': saved_count, 'updated': updated_count}

    @staticmethod
    def get_league_data(league_id: str) -> Dict[str, Any]:
        """
        Retrieve comprehensive league data from database.

        Args:
            league_id: The Sleeper league ID

        Returns:
            Dictionary containing league data or error
        """
        try:
            from models import SleeperLeague, SleeperRoster, SleeperUser

            # Get league info
            league = SleeperLeague.query.filter_by(league_id=league_id).first()
            if not league:
                return {
                    'status': 'error',
                    'error': 'League not found in database'
                }

            # Get rosters
            rosters = SleeperRoster.query.filter_by(league_id=league_id).all()

            # Get users
            users = SleeperUser.query.filter_by(league_id=league_id).all()

            return {
                'status': 'success',
                'league': league.to_dict(),
                'rosters': [roster.to_dict() for roster in rosters],
                'users': [user.to_dict() for user in users],
                'last_updated': league.last_updated.isoformat() if league.last_updated else None
            }

        except Exception as e:
            logger.error(
                "Error retrieving league data for %s: %s", league_id, e)
            return {
                'status': 'error',
                'error': str(e)
            }

    @staticmethod
    def save_research_data(research_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Save player research data to database.

        Args:
            research_data: Dictionary containing research data

        Returns:
            Dictionary with operation results
        """
        try:
            if not research_data.get('success'):
                return {
                    'status': 'error',
                    'error': research_data.get('error', 'Research data fetch failed')
                }

            from models import SleeperResearch

            season = research_data['season']
            week = research_data.get('week', 1)
            league_type = research_data.get('league_type', 2)
            research_content = research_data.get('research_data', {})

            logger.info(
                "Saving research data for season: %s, week: %s", season, week)

            # Delete existing research data for this season/week/league_type
            SleeperResearch.query.filter_by(
                season=season,
                week=week,
                league_type=league_type
            ).delete()

            saved_count = 0
            # Save research data for each player
            for player_id, player_research in research_content.items():
                research_record = SleeperResearch(
                    season=season,
                    week=week,
                    league_type=league_type,
                    player_id=player_id,
                    research_data=json.dumps(player_research)
                )
                db.session.add(research_record)
                saved_count += 1

            db.session.commit()

            return {
                'status': 'success',
                'season': season,
                'week': week,
                'league_type': league_type,
                'players_saved': saved_count,
                'timestamp': datetime.now(UTC).isoformat()
            }

        except Exception as e:
            logger.error("Error saving research data: %s", e)
            db.session.rollback()
            return {
                'status': 'error',
                'error': str(e)
            }

    @staticmethod
    def get_research_data(season: str, week: int = 1, league_type: int = 2) -> Dict[str, Any]:
        """
        Retrieve player research data from database.

        Args:
            season: The NFL season year
            week: The week number
            league_type: League type (2 for dynasty)

        Returns:
            Dictionary containing research data or error
        """
        try:
            from models import SleeperResearch

            research_records = SleeperResearch.query.filter_by(
                season=season,
                week=week,
                league_type=league_type
            ).all()

            if not research_records:
                return {
                    'status': 'error',
                    'error': 'No research data found for specified parameters'
                }

            # Convert to dictionary format
            research_data = {}
            for record in research_records:
                research_data[record.player_id] = json.loads(
                    record.research_data)

            return {
                'status': 'success',
                'season': season,
                'week': week,
                'league_type': league_type,
                'research_data': research_data,
                'players_count': len(research_records),
                'last_updated': max(record.last_updated for record in research_records).isoformat()
            }

        except Exception as e:
            logger.error("Error retrieving research data: %s", e)
            return {
                'status': 'error',
                'error': str(e)
            }

    @staticmethod
    def _process_sleeper_batch(sleeper_batch: List[Dict[str, Any]]) -> Dict[str, int]:
        """
        Process a batch of Sleeper players for database save.

        Since Sleeper is the base datasource, we create/update player records with Sleeper data.
        For each Sleeper player, we either update an existing record or create a new one.

        Args:
            sleeper_batch: Batch of Sleeper player data

        Returns:
            Dictionary with batch processing results
        """
        updates = 0
        new_records = 0
        match_failures = 0

        for sleeper_player in sleeper_batch:
            try:
                # Check if we already have a record with this sleeper_player_id
                existing_player = Player.query.filter_by(
                    sleeper_player_id=sleeper_player.get('sleeper_player_id')
                ).first()

                if existing_player:
                    # Update existing record with fresh Sleeper data
                    DatabaseManager._update_player_with_sleeper_data(existing_player, sleeper_player)
                    updates += 1
                else:
                    # Create new player record from Sleeper data
                    DatabaseManager._create_player_from_sleeper_data(sleeper_player)
                    new_records += 1

            except Exception as e:
                logger.warning("Error processing Sleeper player %s: %s",
                               sleeper_player.get('full_name', 'unknown'), e)
                match_failures += 1
                continue

        return {
            'updates': updates,
            'new_records': new_records,
            'match_failures': match_failures
        }


    @staticmethod
    def _update_player_with_sleeper_data(existing_player: Player, sleeper_data: Dict[str, Any]) -> None:
        """
        Update existing player record with fresh Sleeper data.

        Args:
            existing_player: Existing player record
            sleeper_data: Fresh Sleeper player data
        """
        # Parse birth date if available
        birth_date = None
        if sleeper_data.get('birth_date'):
            try:
                birth_date = datetime.strptime(sleeper_data['birth_date'], '%Y-%m-%d').date()
            except (ValueError, TypeError):
                birth_date = None

        # Parse injury start date if available
        injury_start_date = None
        if sleeper_data.get('injury_start_date'):
            try:
                injury_start_date = datetime.strptime(sleeper_data['injury_start_date'], '%Y-%m-%d').date()
            except (ValueError, TypeError):
                injury_start_date = None

        # Parse numeric fields safely
        number = None
        if sleeper_data.get('number'):
            try:
                number = int(sleeper_data['number'])
            except (ValueError, TypeError):
                number = None

        # Update Sleeper fields while preserving KTC data
        existing_player.player_name = sleeper_data.get('full_name', existing_player.player_name)
        existing_player.position = sleeper_data.get('position', existing_player.position)
        existing_player.team = sleeper_data.get('team', existing_player.team)
        existing_player.birth_date = birth_date
        existing_player.height = sleeper_data.get('height')
        existing_player.weight = sleeper_data.get('weight')
        existing_player.college = sleeper_data.get('college')
        existing_player.years_exp = sleeper_data.get('years_exp')
        existing_player.number = number
        existing_player.depth_chart_order = sleeper_data.get('depth_chart_order')
        existing_player.depth_chart_position = sleeper_data.get('depth_chart_position')
        existing_player.fantasy_positions = sleeper_data.get('fantasy_positions')
        existing_player.hashtag = sleeper_data.get('hashtag')
        existing_player.search_rank = sleeper_data.get('search_rank')
        existing_player.high_school = sleeper_data.get('high_school')
        existing_player.rookie_year = sleeper_data.get('rookie_year')
        existing_player.injury_status = sleeper_data.get('injury_status')
        existing_player.injury_start_date = injury_start_date
        
        # Update additional Sleeper fields
        existing_player.competitions = sleeper_data.get('competitions')
        existing_player.injury_body_part = sleeper_data.get('injury_body_part')
        existing_player.injury_notes = sleeper_data.get('injury_notes')
        existing_player.team_changed_at = sleeper_data.get('team_changed_at')
        existing_player.practice_participation = sleeper_data.get('practice_participation')
        existing_player.search_first_name = sleeper_data.get('search_first_name')
        existing_player.birth_state = sleeper_data.get('birth_state')
        existing_player.oddsjam_id = sleeper_data.get('oddsjam_id')
        existing_player.practice_description = sleeper_data.get('practice_description')
        existing_player.opta_id = sleeper_data.get('opta_id')
        existing_player.search_full_name = sleeper_data.get('search_full_name')
        existing_player.espn_id = sleeper_data.get('espn_id')
        existing_player.team_abbr = sleeper_data.get('team_abbr')
        existing_player.search_last_name = sleeper_data.get('search_last_name')
        existing_player.sportradar_id = sleeper_data.get('sportradar_id')
        existing_player.swish_id = sleeper_data.get('swish_id')
        existing_player.birth_country = sleeper_data.get('birth_country')
        existing_player.gsis_id = sleeper_data.get('gsis_id')
        existing_player.pandascore_id = sleeper_data.get('pandascore_id')
        existing_player.yahoo_id = sleeper_data.get('yahoo_id')
        existing_player.fantasy_data_id = sleeper_data.get('fantasy_data_id')
        existing_player.stats_id = sleeper_data.get('stats_id')
        existing_player.news_updated = sleeper_data.get('news_updated')
        existing_player.birth_city = sleeper_data.get('birth_city')
        existing_player.rotoworld_id = sleeper_data.get('rotoworld_id')
        existing_player.rotowire_id = sleeper_data.get('rotowire_id')
        existing_player.full_name = sleeper_data.get('full_name')
        existing_player.status = sleeper_data.get('status')
        existing_player.player_metadata = sleeper_data.get('player_metadata')
        
        # Update timestamp
        existing_player.last_updated = datetime.now(UTC)
        
        logger.debug("Updated existing player with Sleeper data: %s (%s)", 
                    sleeper_data.get('full_name', 'Unknown'), sleeper_data.get('position', 'Unknown'))

    @staticmethod
    def _create_player_from_sleeper_data(sleeper_data: Dict[str, Any]) -> None:
        """
        Create new player record from Sleeper data.

        Args:
            sleeper_data: Sleeper player data
        """
        # Parse birth date if available
        birth_date = None
        if sleeper_data.get('birth_date'):
            try:
                birth_date = datetime.strptime(sleeper_data['birth_date'], '%Y-%m-%d').date()
            except (ValueError, TypeError):
                birth_date = None

        # Parse injury start date if available
        injury_start_date = None
        if sleeper_data.get('injury_start_date'):
            try:
                injury_start_date = datetime.strptime(sleeper_data['injury_start_date'], '%Y-%m-%d').date()
            except (ValueError, TypeError):
                injury_start_date = None

        # Parse numeric fields safely
        number = None
        if sleeper_data.get('number'):
            try:
                number = int(sleeper_data['number'])
            except (ValueError, TypeError):
                number = None

        # Create comprehensive player record with all available Sleeper data
        new_player = Player(
            player_name=sleeper_data.get('full_name', ''),
            position=sleeper_data.get('position', ''),
            team=sleeper_data.get('team', ''),
            age=None,  # Will be calculated from birth_date if needed
            rookie="No",  # Default, can be updated later
            
            # Sleeper identification and core data
            sleeper_player_id=sleeper_data.get('sleeper_player_id'),
            birth_date=birth_date,
            height=sleeper_data.get('height'),
            weight=sleeper_data.get('weight'),
            college=sleeper_data.get('college'),
            years_exp=sleeper_data.get('years_exp'),
            number=number,
            depth_chart_order=sleeper_data.get('depth_chart_order'),
            depth_chart_position=sleeper_data.get('depth_chart_position'),
            fantasy_positions=sleeper_data.get('fantasy_positions'),
            hashtag=sleeper_data.get('hashtag'),
            search_rank=sleeper_data.get('search_rank'),
            high_school=sleeper_data.get('high_school'),
            rookie_year=sleeper_data.get('rookie_year'),
            injury_status=sleeper_data.get('injury_status'),
            injury_start_date=injury_start_date,
            
            # Additional Sleeper fields
            competitions=sleeper_data.get('competitions'),
            injury_body_part=sleeper_data.get('injury_body_part'),
            injury_notes=sleeper_data.get('injury_notes'),
            team_changed_at=sleeper_data.get('team_changed_at'),
            practice_participation=sleeper_data.get('practice_participation'),
            search_first_name=sleeper_data.get('search_first_name'),
            birth_state=sleeper_data.get('birth_state'),
            oddsjam_id=sleeper_data.get('oddsjam_id'),
            practice_description=sleeper_data.get('practice_description'),
            opta_id=sleeper_data.get('opta_id'),
            search_full_name=sleeper_data.get('search_full_name'),
            espn_id=sleeper_data.get('espn_id'),
            team_abbr=sleeper_data.get('team_abbr'),
            search_last_name=sleeper_data.get('search_last_name'),
            sportradar_id=sleeper_data.get('sportradar_id'),
            swish_id=sleeper_data.get('swish_id'),
            birth_country=sleeper_data.get('birth_country'),
            gsis_id=sleeper_data.get('gsis_id'),
            pandascore_id=sleeper_data.get('pandascore_id'),
            yahoo_id=sleeper_data.get('yahoo_id'),
            fantasy_data_id=sleeper_data.get('fantasy_data_id'),
            stats_id=sleeper_data.get('stats_id'),
            news_updated=sleeper_data.get('news_updated'),
            birth_city=sleeper_data.get('birth_city'),
            rotoworld_id=sleeper_data.get('rotoworld_id'),
            rotowire_id=sleeper_data.get('rotowire_id'),
            full_name=sleeper_data.get('full_name'),
            status=sleeper_data.get('status'),
            
            # Player metadata as JSON
            player_metadata=sleeper_data.get('player_metadata')
        )

        db.session.add(new_player)
        logger.info("Created new player record from Sleeper data: %s (%s)", 
                   sleeper_data.get('full_name', 'Unknown'), sleeper_data.get('position', 'Unknown'))

    @staticmethod
    def _process_ktc_players_with_sleeper_merge(players: List[Dict[str, Any]], league_format: str,
                                              is_redraft: bool) -> tuple[int, int, List[str]]:
        """
        Process KTC players with Sleeper data merge for database insertion.
        
        This function handles the core logic of merging KTC data into existing Sleeper-based records
        or creating new records with both KTC and Sleeper data.

        Args:
            players: List of merged player data (KTC + Sleeper)
            league_format: League format
            is_redraft: Whether this is redraft data

        Returns:
            Tuple of (processed_count, skipped_count, validation_errors)
        """
        processed_count = 0
        skipped_count = 0
        validation_errors = []

        for i, player in enumerate(players):
            try:
                # Validate required fields
                player_name = player.get(PLAYER_NAME_KEY)
                position = player.get(POSITION_KEY)

                if not player_name or not position:
                    error_msg = f"Player #{i+1} missing required fields: name='{player_name}', position='{position}'"
                    logger.warning(error_msg)
                    validation_errors.append(error_msg)
                    skipped_count += 1
                    continue

                # Check if we have KTC values for this league format
                has_values = False
                if league_format == '1qb' and player.get('oneqb_values'):
                    has_values = True
                elif league_format == 'superflex' and player.get('superflex_values'):
                    has_values = True

                if not has_values:
                    logger.debug(f"Skipping player {player_name} - no {league_format} values")
                    skipped_count += 1
                    continue

                # Look for existing player by name and position
                # Note: KTC API responses don't contain sleeper_player_id, so we match by name/position
                existing_player = Player.query.filter_by(
                    player_name=player_name,
                    position=position,
                    league_format=league_format,
                    is_redraft=is_redraft
                ).first()

                if existing_player:
                    # Update existing player with merged data
                    DatabaseManager._update_existing_player_with_merged_data(existing_player, player)
                    processed_count += 1
                else:
                    # Create new player with merged data
                    DatabaseManager._create_player_with_merged_data(player, league_format, is_redraft)
                    processed_count += 1

            except Exception as player_error:
                error_msg = f"Error processing player #{i+1} ({player.get(PLAYER_NAME_KEY, 'Unknown')}): {player_error}"
                logger.error(error_msg)
                validation_errors.append(error_msg)
                skipped_count += 1
                continue

        return processed_count, skipped_count, validation_errors

    @staticmethod
    def _update_existing_player_with_merged_data(existing_player: Player, merged_data: Dict[str, Any]) -> None:
        """
        Update existing player with merged KTC and Sleeper data.

        Args:
            existing_player: Existing player record
            merged_data: Merged KTC and Sleeper data
        """
        # Parse dates
        birth_date = None
        if merged_data.get('birth_date'):
            try:
                birth_date = datetime.strptime(merged_data['birth_date'], '%Y-%m-%d').date()
            except (ValueError, TypeError):
                birth_date = None

        injury_start_date = None
        if merged_data.get('injury_start_date'):
            try:
                injury_start_date = datetime.strptime(merged_data['injury_start_date'], '%Y-%m-%d').date()
            except (ValueError, TypeError):
                injury_start_date = None

        # Parse numeric fields
        number = None
        if merged_data.get('number'):
            try:
                number = int(merged_data['number'])
            except (ValueError, TypeError):
                number = None

        # Update core fields (always preserve Sleeper name if available, don't overwrite with KTC data)
        if merged_data.get('full_name'):
            # Always use Sleeper's full_name if available (don't overwrite with KTC name)
            existing_player.player_name = merged_data.get('full_name')
        elif not existing_player.player_name:
            # Only use KTC name if no existing name
            existing_player.player_name = merged_data.get(PLAYER_NAME_KEY, existing_player.player_name)
        
        existing_player.position = merged_data.get(POSITION_KEY, existing_player.position)
        existing_player.team = merged_data.get(TEAM_KEY, existing_player.team)
        
        # Update KTC fields
        existing_player.ktc_player_id = merged_data.get('ktc_player_id')
        existing_player.age = merged_data.get(AGE_KEY)
        existing_player.rookie = merged_data.get(ROOKIE_KEY, "No")
        existing_player.slug = merged_data.get('slug')
        existing_player.positionID = merged_data.get('positionID')
        existing_player.heightFeet = merged_data.get('heightFeet')
        existing_player.heightInches = merged_data.get('heightInches')
        existing_player.seasonsExperience = merged_data.get('seasonsExperience')
        existing_player.pickRound = merged_data.get('pickRound')
        existing_player.pickNum = merged_data.get('pickNum')
        existing_player.isFeatured = merged_data.get('isFeatured')
        existing_player.isStartSitFeatured = merged_data.get('isStartSitFeatured')
        existing_player.isTrending = merged_data.get('isTrending')
        existing_player.isDevyReturningToSchool = merged_data.get('isDevyReturningToSchool')
        existing_player.isDevyYearDecrement = merged_data.get('isDevyYearDecrement')
        existing_player.teamLongName = merged_data.get('teamLongName')
        existing_player.birthday = merged_data.get('birthday')
        existing_player.draftYear = merged_data.get('draftYear')
        existing_player.byeWeek = merged_data.get('byeWeek')
        existing_player.injury = merged_data.get('injury')

        # Update Sleeper fields
        existing_player.sleeper_player_id = merged_data.get('sleeper_player_id')
        existing_player.birth_date = birth_date
        existing_player.height = merged_data.get('height')
        existing_player.weight = merged_data.get('weight')
        existing_player.college = merged_data.get('college')
        existing_player.years_exp = merged_data.get('years_exp')
        existing_player.number = number
        existing_player.depth_chart_order = merged_data.get('depth_chart_order')
        existing_player.depth_chart_position = merged_data.get('depth_chart_position')
        existing_player.fantasy_positions = merged_data.get('fantasy_positions')
        existing_player.hashtag = merged_data.get('hashtag')
        existing_player.search_rank = merged_data.get('search_rank')
        existing_player.high_school = merged_data.get('high_school')
        existing_player.rookie_year = merged_data.get('rookie_year')
        existing_player.injury_status = merged_data.get('injury_status')
        existing_player.injury_start_date = injury_start_date
        existing_player.full_name = merged_data.get('full_name')
        existing_player.status = merged_data.get('status')
        existing_player.player_metadata = merged_data.get('player_metadata')

        # Update additional Sleeper fields
        existing_player.competitions = merged_data.get('competitions')
        existing_player.injury_body_part = merged_data.get('injury_body_part')
        existing_player.injury_notes = merged_data.get('injury_notes')
        existing_player.team_changed_at = merged_data.get('team_changed_at')
        existing_player.practice_participation = merged_data.get('practice_participation')
        existing_player.search_first_name = merged_data.get('search_first_name')
        existing_player.birth_state = merged_data.get('birth_state')
        existing_player.oddsjam_id = merged_data.get('oddsjam_id')
        existing_player.practice_description = merged_data.get('practice_description')
        existing_player.opta_id = merged_data.get('opta_id')
        # Ensure search_full_name is always saved (critical for player matching)
        existing_player.search_full_name = merged_data.get('search_full_name')
        existing_player.espn_id = merged_data.get('espn_id')
        existing_player.team_abbr = merged_data.get('team_abbr')
        existing_player.search_last_name = merged_data.get('search_last_name')
        existing_player.sportradar_id = merged_data.get('sportradar_id')
        existing_player.swish_id = merged_data.get('swish_id')
        existing_player.birth_country = merged_data.get('birth_country')
        existing_player.gsis_id = merged_data.get('gsis_id')
        existing_player.pandascore_id = merged_data.get('pandascore_id')
        existing_player.yahoo_id = merged_data.get('yahoo_id')
        existing_player.fantasy_data_id = merged_data.get('fantasy_data_id')
        existing_player.stats_id = merged_data.get('stats_id')
        existing_player.news_updated = merged_data.get('news_updated')
        existing_player.birth_city = merged_data.get('birth_city')
        existing_player.rotoworld_id = merged_data.get('rotoworld_id')
        existing_player.rotowire_id = merged_data.get('rotowire_id')

        # Update KTC values
        DatabaseManager._update_player_ktc_values(existing_player, merged_data)

        # Update timestamp
        existing_player.last_updated = datetime.now(UTC)

        logger.debug("Updated existing player with merged data: %s (%s)", 
                    merged_data.get(PLAYER_NAME_KEY, 'Unknown'), merged_data.get(POSITION_KEY, 'Unknown'))

    @staticmethod
    def _create_player_with_merged_data(merged_data: Dict[str, Any], league_format: str, is_redraft: bool) -> Player:
        """
        Create new player record with merged KTC and Sleeper data.

        Args:
            merged_data: Merged KTC and Sleeper data
            league_format: League format
            is_redraft: Whether this is redraft data
        """
        # Parse dates
        birth_date = None
        if merged_data.get('birth_date'):
            try:
                birth_date = datetime.strptime(merged_data['birth_date'], '%Y-%m-%d').date()
            except (ValueError, TypeError):
                birth_date = None

        injury_start_date = None
        if merged_data.get('injury_start_date'):
            try:
                injury_start_date = datetime.strptime(merged_data['injury_start_date'], '%Y-%m-%d').date()
            except (ValueError, TypeError):
                injury_start_date = None

        # Parse numeric fields
        number = None
        if merged_data.get('number'):
            try:
                number = int(merged_data['number'])
            except (ValueError, TypeError):
                number = None

        # Create new player with merged data
        new_player = Player(
            player_name=merged_data.get('full_name') or merged_data.get(PLAYER_NAME_KEY, ''),
            position=merged_data.get(POSITION_KEY, ''),
            team=merged_data.get(TEAM_KEY, ''),
            age=merged_data.get(AGE_KEY),
            rookie=merged_data.get(ROOKIE_KEY, "No"),
            
            # KTC data
            ktc_player_id=merged_data.get('ktc_player_id'),
            slug=merged_data.get('slug'),
            positionID=merged_data.get('positionID'),
            heightFeet=merged_data.get('heightFeet'),
            heightInches=merged_data.get('heightInches'),
            seasonsExperience=merged_data.get('seasonsExperience'),
            pickRound=merged_data.get('pickRound'),
            pickNum=merged_data.get('pickNum'),
            isFeatured=merged_data.get('isFeatured'),
            isStartSitFeatured=merged_data.get('isStartSitFeatured'),
            isTrending=merged_data.get('isTrending'),
            isDevyReturningToSchool=merged_data.get('isDevyReturningToSchool'),
            isDevyYearDecrement=merged_data.get('isDevyYearDecrement'),
            teamLongName=merged_data.get('teamLongName'),
            birthday=merged_data.get('birthday'),
            draftYear=merged_data.get('draftYear'),
            byeWeek=merged_data.get('byeWeek'),
            injury=merged_data.get('injury'),
            
            # Sleeper data
            sleeper_player_id=merged_data.get('sleeper_player_id'),
            birth_date=birth_date,
            height=merged_data.get('height'),
            weight=merged_data.get('weight'),
            college=merged_data.get('college'),
            years_exp=merged_data.get('years_exp'),
            number=number,
            depth_chart_order=merged_data.get('depth_chart_order'),
            depth_chart_position=merged_data.get('depth_chart_position'),
            fantasy_positions=merged_data.get('fantasy_positions'),
            hashtag=merged_data.get('hashtag'),
            search_rank=merged_data.get('search_rank'),
            high_school=merged_data.get('high_school'),
            rookie_year=merged_data.get('rookie_year'),
            injury_status=merged_data.get('injury_status'),
            injury_start_date=injury_start_date,
            full_name=merged_data.get('full_name'),
            status=merged_data.get('status'),
            player_metadata=merged_data.get('player_metadata'),
            
            # Additional Sleeper fields
            competitions=merged_data.get('competitions'),
            injury_body_part=merged_data.get('injury_body_part'),
            injury_notes=merged_data.get('injury_notes'),
            team_changed_at=merged_data.get('team_changed_at'),
            practice_participation=merged_data.get('practice_participation'),
            search_first_name=merged_data.get('search_first_name'),
            birth_state=merged_data.get('birth_state'),
            oddsjam_id=merged_data.get('oddsjam_id'),
            practice_description=merged_data.get('practice_description'),
            opta_id=merged_data.get('opta_id'),
            search_full_name=merged_data.get('search_full_name'),
            espn_id=merged_data.get('espn_id'),
            team_abbr=merged_data.get('team_abbr'),
            search_last_name=merged_data.get('search_last_name'),
            sportradar_id=merged_data.get('sportradar_id'),
            swish_id=merged_data.get('swish_id'),
            birth_country=merged_data.get('birth_country'),
            gsis_id=merged_data.get('gsis_id'),
            pandascore_id=merged_data.get('pandascore_id'),
            yahoo_id=merged_data.get('yahoo_id'),
            fantasy_data_id=merged_data.get('fantasy_data_id'),
            stats_id=merged_data.get('stats_id'),
            news_updated=merged_data.get('news_updated'),
            birth_city=merged_data.get('birth_city'),
            rotoworld_id=merged_data.get('rotoworld_id'),
            rotowire_id=merged_data.get('rotowire_id')
        )

        db.session.add(new_player)

        # Add KTC values
        DatabaseManager._update_player_ktc_values(new_player, merged_data)

        logger.info("Created new player with merged data: %s (%s)", 
                   merged_data.get(PLAYER_NAME_KEY, 'Unknown'), merged_data.get(POSITION_KEY, 'Unknown'))
        
        return new_player

    @staticmethod
    def _update_player_ktc_values(player: Player, merged_data: Dict[str, Any]) -> None:
        """
        Update or create KTC values for a player.

        Args:
            player: Player record
            merged_data: Merged data containing KTC values
        """
        # Update OneQB values if present
        if merged_data.get('oneqb_values'):
            oneqb_data = merged_data['oneqb_values']
            
            # Remove existing OneQB values
            if player.oneqb_values:
                db.session.delete(player.oneqb_values)
            
            # Create new OneQB values
            oneqb_values = PlayerKTCOneQBValues(
                player=player,
                **oneqb_data
            )
            db.session.add(oneqb_values)

        # Update Superflex values if present
        if merged_data.get('superflex_values'):
            superflex_data = merged_data['superflex_values']
            
            # Remove existing Superflex values
            if player.superflex_values:
                db.session.delete(player.superflex_values)
            
            # Create new Superflex values
            superflex_values = PlayerKTCSuperflexValues(
                player=player,
                **superflex_data
            )
            db.session.add(superflex_values)
