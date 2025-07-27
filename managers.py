import json
import logging
import os
import tempfile
from datetime import datetime, UTC
from typing import Dict, List, Optional, Any

import boto3
from botocore.exceptions import NoCredentialsError, ClientError
from sqlalchemy import text

from models import db, KTCPlayer
from utils import (normalize_tep_level, PLAYER_NAME_KEY, POSITION_KEY, TEAM_KEY,
                   VALUE_KEY, AGE_KEY, ROOKIE_KEY, RANK_KEY, TREND_KEY, TIER_KEY,
                   POSITION_RANK_KEY, REDRAFT_VALUE_KEY, REDRAFT_POSITION_RANK_KEY,
                   setup_logging)

logger = setup_logging()


class PlayerMerger:
    """
    Handles merging KTC and Sleeper player data.

    Matches players by name, using birth date and position to distinguish
    players with the same name.
    """

    @staticmethod
    def normalize_name(name: str) -> str:
        """
        Normalize player name for matching.

        Args:
            name: Player name to normalize

        Returns:
            Normalized name string
        """
        if not name:
            return ""

        # Convert to lowercase and remove extra whitespace
        normalized = ' '.join(name.lower().split())

        # Remove common suffixes
        suffixes = [' jr', ' sr', ' ii', ' iii', ' iv']
        for suffix in suffixes:
            if normalized.endswith(suffix):
                normalized = normalized[:-len(suffix)].strip()
                break

        return normalized

    @staticmethod
    def create_player_key(name: str, position: str, birth_date: Optional[Any] = None) -> str:
        """
        Create a unique key for player matching.

        Args:
            name: Player name
            position: Player position
            birth_date: Player birth date (optional)

        Returns:
            Unique player key string
        """
        normalized_name = PlayerMerger.normalize_name(name)
        position_key = position.upper() if position else ""

        # Include birth date if available for disambiguation
        if birth_date:
            if hasattr(birth_date, 'strftime'):
                date_key = birth_date.strftime('%Y-%m-%d')
            else:
                date_key = str(birth_date)
            return f"{normalized_name}|{position_key}|{date_key}"

        return f"{normalized_name}|{position_key}"

    @staticmethod
    def merge_player_data(ktc_players: List[Dict[str, Any]], sleeper_players: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Merge KTC and Sleeper player data.

        Args:
            ktc_players: List of KTC player data
            sleeper_players: List of Sleeper player data

        Returns:
            List of merged player data
        """
        try:
            # Create lookup dictionary for Sleeper players
            sleeper_lookup = {}
            sleeper_name_lookup = {}  # Fallback lookup by name only

            for sleeper_player in sleeper_players:
                full_name = sleeper_player.get('full_name', '')
                position = sleeper_player.get('position', '')
                birth_date = sleeper_player.get('birth_date')

                # Primary key with birth date
                primary_key = PlayerMerger.create_player_key(
                    full_name, position, birth_date)
                sleeper_lookup[primary_key] = sleeper_player

                # Fallback key without birth date
                fallback_key = PlayerMerger.create_player_key(
                    full_name, position)
                if fallback_key not in sleeper_name_lookup:
                    sleeper_name_lookup[fallback_key] = []
                sleeper_name_lookup[fallback_key].append(sleeper_player)

            logger.info("Created Sleeper lookup with %s primary keys and %s fallback keys",
                        len(sleeper_lookup), len(sleeper_name_lookup))

            # Merge data
            merged_players = []
            matched_count = 0

            for ktc_player in ktc_players:
                player_name = ktc_player.get(PLAYER_NAME_KEY, '')
                position = ktc_player.get(POSITION_KEY, '')

                # Try to find matching Sleeper player
                sleeper_match = None

                # First, try exact match with any available birth date info
                primary_key = PlayerMerger.create_player_key(
                    player_name, position)

                # Look for exact match in primary lookup
                if primary_key in sleeper_lookup:
                    sleeper_match = sleeper_lookup[primary_key]
                elif primary_key in sleeper_name_lookup:
                    # If multiple matches, take the first one
                    candidates = sleeper_name_lookup[primary_key]
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
                    # Add Sleeper data to merged player including injury data
                    sleeper_keys = [
                        'sleeper_id', 'birth_date', 'height', 'weight', 'college',
                        'years_exp', 'jersey_number', 'depth_chart_order',
                        'depth_chart_position', 'fantasy_positions', 'hashtag',
                        'search_rank', 'high_school', 'rookie_year', 'injury_status', 'injury_start_date'
                    ]

                    for key in sleeper_keys:
                        if key in sleeper_match:
                            merged_player[key] = sleeper_match[key]

                    matched_count += 1

                merged_players.append(merged_player)

            logger.info("Successfully merged %s KTC players with %s Sleeper matches",
                        len(ktc_players), matched_count)
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

        Args:
            json_data: Data to save as JSON
            filename: Target filename

        Returns:
            True if successful, False otherwise
        """
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
    def get_players_from_db(league_format: str, is_redraft: bool, tep_level: Optional[str]) -> tuple[List[KTCPlayer], Optional[datetime]]:
        """
        Retrieve players from database for specific configuration.

        Args:
            league_format: '1qb' or 'superflex'
            is_redraft: Whether to get redraft data
            tep_level: TEP configuration level

        Returns:
            Tuple of (players_list, last_updated_timestamp)
        """
        # Normalize tep_level for database query
        normalized_tep = normalize_tep_level(tep_level)

        players = KTCPlayer.query.filter_by(
            league_format=league_format,
            is_redraft=is_redraft,
            tep=normalized_tep
        ).order_by(KTCPlayer.rank.asc()).all()

        last_updated = max(
            player.last_updated for player in players) if players else None
        return players, last_updated

    @staticmethod
    def _extract_player_values(player: Dict[str, Any], is_redraft: bool) -> tuple[Optional[int], Optional[str]]:
        """
        Extract value and position rank from player data.

        Args:
            player: Player data dictionary
            is_redraft: Whether this is redraft data

        Returns:
            Tuple of (value, position_rank)
        """
        try:
            if is_redraft:
                value = player.get(REDRAFT_VALUE_KEY, 0)
                position_rank = player.get(REDRAFT_POSITION_RANK_KEY)
            else:
                value = player.get(VALUE_KEY, 0)
                position_rank = player.get(POSITION_RANK_KEY)

            # Convert value to int if it's a string
            if isinstance(value, str):
                try:
                    value = int(value)
                except (ValueError, TypeError):
                    logger.warning(
                        f"Could not convert value '{value}' to int for player {player.get(PLAYER_NAME_KEY, 'Unknown')}")
                    value = 0

            return value, position_rank

        except Exception as e:
            logger.error("Error extracting player values: %s", e)
            return 0, None

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
    def _prepare_database(league_format: str, is_redraft: bool, tep_level: Optional[str]) -> int:
        """
        Prepare database by verifying connection and cleaning existing data.

        Args:
            league_format: League format
            is_redraft: Whether this is redraft data
            tep_level: TEP level string

        Returns:
            Number of deleted records

        Raises:
            Exception: If database preparation fails
        """
        # Verify database connection
        if not DatabaseManager.verify_database_connection():
            raise Exception("Database connection verification failed")

        # Create tables if they don't exist
        db.create_all()

        # Delete existing data for this configuration
        try:
            deleted_count = KTCPlayer.query.filter_by(
                league_format=league_format,
                is_redraft=is_redraft,
                tep=tep_level
            ).delete(synchronize_session=False)

            logger.info("Deleted %s existing records", deleted_count)
            return deleted_count
        except Exception as e:
            raise Exception(f"Failed to delete existing records: {e}")

    @staticmethod
    def _process_and_validate_players(players: List[Dict[str, Any]], league_format: str,
                                      is_redraft: bool, tep_level: Optional[str]) -> tuple[int, int, List[str]]:
        """
        Process and validate player data for database insertion with Sleeper data.

        Args:
            players: List of player data
            league_format: League format
            is_redraft: Whether this is redraft data
            tep_level: TEP level string

        Returns:
            Tuple of (added_count, skipped_count, validation_errors)
        """
        added_count = 0
        skipped_count = 0
        validation_errors = []

        for i, player in enumerate(players):
            try:
                value, position_rank = DatabaseManager._extract_player_values(
                    player, is_redraft)

                # Skip players without values
                if value is None or value == 0:
                    logger.debug(
                        f"Skipping player {player.get(PLAYER_NAME_KEY, 'Unknown')} - no value")
                    skipped_count += 1
                    continue

                # Validate required fields
                player_name = player.get(PLAYER_NAME_KEY)
                position = player.get(POSITION_KEY)

                if not player_name or not position:
                    error_msg = f"Player #{i+1} missing required fields: name='{player_name}', position='{position}'"
                    logger.warning(error_msg)
                    validation_errors.append(error_msg)
                    skipped_count += 1
                    continue

                # Parse Sleeper-specific data
                birth_date = player.get('birth_date')
                if isinstance(birth_date, str):
                    try:
                        birth_date = datetime.strptime(
                            birth_date, '%Y-%m-%d').date()
                    except ValueError:
                        birth_date = None

                jersey_number = player.get('jersey_number')
                if jersey_number is not None:
                    try:
                        jersey_number = int(jersey_number)
                    except (ValueError, TypeError):
                        jersey_number = None

                # Create player object with Sleeper data
                ktc_player = KTCPlayer(
                    player_name=player_name,
                    position=position,
                    team=player.get(TEAM_KEY),
                    value=value,
                    age=player.get(AGE_KEY),
                    rookie=player.get(ROOKIE_KEY, "No"),
                    rank=player.get(RANK_KEY),
                    trend=player.get(TREND_KEY, "0"),
                    tier=player.get(TIER_KEY),
                    position_rank=position_rank,
                    league_format=league_format,
                    is_redraft=is_redraft,
                    tep=tep_level,
                    # Sleeper data
                    sleeper_id=player.get('sleeper_id'),
                    birth_date=birth_date,
                    height=player.get('height'),
                    weight=player.get('weight'),
                    college=player.get('college'),
                    years_exp=player.get('years_exp'),
                    jersey_number=jersey_number,
                    depth_chart_order=player.get('depth_chart_order'),
                    depth_chart_position=player.get('depth_chart_position'),
                    fantasy_positions=player.get('fantasy_positions'),
                    hashtag=player.get('hashtag'),
                    search_rank=player.get('search_rank'),
                    high_school=player.get('high_school'),
                    rookie_year=player.get('rookie_year'),
                    # Injury data
                    injury_status=player.get('injury_status'),
                    injury_start_date=player.get('injury_start_date')
                )

                db.session.add(ktc_player)
                added_count += 1

            except Exception as player_error:
                error_msg = f"Error processing player #{i+1} ({player.get(PLAYER_NAME_KEY, 'Unknown')}): {player_error}"
                logger.error(error_msg)
                validation_errors.append(error_msg)
                skipped_count += 1
                continue

        return added_count, skipped_count, validation_errors

    @staticmethod
    def _verify_save_operation(league_format: str, is_redraft: bool, tep_level: Optional[str], expected_count: int) -> None:
        """
        Verify that the save operation was successful.

        Args:
            league_format: League format
            is_redraft: Whether this is redraft data
            tep_level: TEP level string
            expected_count: Expected number of records
        """
        try:
            actual_count = KTCPlayer.query.filter_by(
                league_format=league_format,
                is_redraft=is_redraft,
                tep=tep_level
            ).count()

            if actual_count != expected_count:
                logger.warning(
                    "Post-commit verification: expected %s, found %s", expected_count, actual_count)
        except Exception as verify_error:
            logger.warning("Post-commit verification failed: %s", verify_error)

    @staticmethod
    def save_players_to_db(players: List[Dict[str, Any]], league_format: str, is_redraft: bool, tep_level: Optional[str]) -> int:
        """
        Save players to database with comprehensive error handling and validation.

        Args:
            players: List of player data dictionaries
            league_format: '1qb' or 'superflex'
            is_redraft: Whether this is redraft data
            tep_level: TEP configuration level

        Returns:
            Number of players added to database

        Raises:
            Exception: If save operation fails
        """
        operation_stage = "initialization"
        added_count = 0
        deleted_count = 0

        try:
            # Validate inputs
            operation_stage = "input validation"
            normalized_tep = DatabaseManager._validate_save_inputs(
                players, league_format, tep_level)
            logger.info(
                "Starting database transaction for %s, redraft=%s, tep_level=%s", league_format, is_redraft, tep_level)
            logger.info("Input validation: %s players provided", len(players))

            # Prepare database
            operation_stage = "database preparation"
            deleted_count = DatabaseManager._prepare_database(
                league_format, is_redraft, normalized_tep)

            # Process and validate players
            operation_stage = "data processing and validation"
            added_count, skipped_count, validation_errors = DatabaseManager._process_and_validate_players(
                players, league_format, is_redraft, normalized_tep
            )

            # Check if we have any players to save
            if added_count == 0:
                error_details = f"No valid players to save. Skipped: {skipped_count}, Validation errors: {len(validation_errors)}"
                if validation_errors:
                    error_details += f". First few errors: {validation_errors[:3]}"
                raise Exception(error_details)

            # Log processing summary
            logger.info(
                "Processing summary: %s players to add, %s skipped", added_count, skipped_count)
            if validation_errors:
                logger.warning(
                    "Validation errors encountered: %s", len(validation_errors))

            # Commit transaction
            operation_stage = "database commit"
            logger.info("Committing %s records to database...", added_count)
            db.session.commit()
            logger.info("Database commit successful")

            # Verify operation
            operation_stage = "post-commit verification"
            DatabaseManager._verify_save_operation(
                league_format, is_redraft, normalized_tep, added_count)

            return added_count

        except Exception as e:
            logger.error("Error in %s: %s", operation_stage, e)

            # Perform rollback
            try:
                db.session.rollback()
                logger.info("Database rollback completed successfully")
            except Exception as rollback_error:
                logger.error("Database rollback failed: %s", rollback_error)

            # Provide detailed error context
            error_context = {
                'stage': operation_stage,
                'added_count': added_count,
                'deleted_count': deleted_count,
                'total_input_players': len(players) if players else 0
            }

            raise Exception(
                f"Database save operation failed at {operation_stage}: {e}. Context: {error_context}")

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
            total_records = KTCPlayer.query.count()
            stats['total_records'] = total_records

            # Get counts by configuration
            configs = db.session.query(
                KTCPlayer.league_format,
                KTCPlayer.is_redraft,
                KTCPlayer.tep,
                db.func.count(KTCPlayer.id).label('count')
            ).group_by(
                KTCPlayer.league_format,
                KTCPlayer.is_redraft,
                KTCPlayer.tep
            ).all()

            stats['configurations'] = [
                {
                    'league_format': config.league_format,
                    'is_redraft': config.is_redraft,
                    'tep': config.tep,
                    'count': config.count
                }
                for config in configs
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

            # Get current count
            current_count = KTCPlayer.query.filter_by(
                league_format=league_format,
                is_redraft=is_redraft,
                tep=normalized_tep
            ).count()

            # Find records with missing critical data
            incomplete_records = KTCPlayer.query.filter(
                KTCPlayer.league_format == league_format,
                KTCPlayer.is_redraft == is_redraft,
                KTCPlayer.tep == normalized_tep,
                db.or_(
                    KTCPlayer.player_name.is_(None),
                    KTCPlayer.player_name == '',
                    KTCPlayer.position.is_(None),
                    KTCPlayer.position == '',
                    KTCPlayer.value.is_(None),
                    KTCPlayer.value == 0
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
            final_count = KTCPlayer.query.filter_by(
                league_format=league_format,
                is_redraft=is_redraft,
                tep=normalized_tep
            ).count()

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
    def merge_sleeper_data_with_ktc(sleeper_players: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Merge Sleeper player data with existing KTC players using batch processing."""
        try:
            logger.info(
                "Starting Sleeper data merge with %s players...", len(sleeper_players))

            existing_sleeper_count = KTCPlayer.query.filter(
                KTCPlayer.sleeper_id.isnot(None)).count()

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

            logger.info("Merge completed: %s updates, %s new records, %s failures",
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
            logger.error("Error merging Sleeper data: %s", e)
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
        Process a batch of Sleeper players for database merge.

        Implements comprehensive player matching logic:
        - Matches players by name, using birth date and position to distinguish players with the same name
        - Handles multiple players with same name by using birth_date as tie-breaker

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
                # Find matching KTC players using name and position (Criterion 5)
                potential_matches = KTCPlayer.query.filter(
                    KTCPlayer.player_name == sleeper_player['full_name'],
                    KTCPlayer.position == sleeper_player['position']
                ).all()

                # If multiple matches, use birth_date to distinguish (Criterion 5)
                matched_players = []
                if len(potential_matches) > 1 and sleeper_player['birth_date']:
                    for player in potential_matches:
                        if player.birth_date == sleeper_player['birth_date']:
                            matched_players.append(player)

                    if not matched_players:
                        # No birth_date match, use first match as fallback
                        matched_players = [potential_matches[0]]
                        logger.warning(
                            "Multiple name matches for %s, using first match", sleeper_player['full_name'])
                else:
                    matched_players = potential_matches

                if matched_players:
                    # Update existing KTC players with Sleeper data
                    for ktc_player in matched_players:
                        DatabaseManager._update_ktc_player_with_sleeper_data(
                            ktc_player, sleeper_player)
                        updates += 1
                else:
                    # Create new player record (rare case for KTC players)
                    DatabaseManager._create_ktc_player_from_sleeper_data(
                        sleeper_player)
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
    def _update_ktc_player_with_sleeper_data(ktc_player: KTCPlayer, sleeper_data: Dict[str, Any]) -> None:
        """
        Update existing KTC player with Sleeper data while maintaining KTC system integrity.

        Maintains existing KTC identification system as primary identifier.
        Includes all available Sleeper fields including injury data.

        Args:
            ktc_player: Existing KTC player record
            sleeper_data: Sleeper player data to merge
        """
        # Update Sleeper fields while preserving KTC data
        ktc_player.sleeper_id = sleeper_data['sleeper_id']
        ktc_player.birth_date = sleeper_data['birth_date']
        ktc_player.height = sleeper_data['height']
        ktc_player.weight = sleeper_data['weight']
        ktc_player.college = sleeper_data['college']
        ktc_player.years_exp = sleeper_data['years_exp']
        ktc_player.jersey_number = sleeper_data['jersey_number']
        ktc_player.depth_chart_order = sleeper_data['depth_chart_order']
        ktc_player.depth_chart_position = sleeper_data['depth_chart_position']
        ktc_player.fantasy_positions = sleeper_data['fantasy_positions']
        ktc_player.hashtag = sleeper_data['hashtag']
        ktc_player.search_rank = sleeper_data['search_rank']
        ktc_player.high_school = sleeper_data['high_school']
        ktc_player.rookie_year = sleeper_data['rookie_year']
        ktc_player.injury_status = sleeper_data['injury_status']
        ktc_player.injury_start_date = sleeper_data['injury_start_date']
        ktc_player.last_updated = datetime.now(UTC)

    @staticmethod
    def _create_ktc_player_from_sleeper_data(sleeper_data: Dict[str, Any]) -> None:
        """
        Create new KTC player record from Sleeper data.

        This handles the rare case of players in Sleeper API but not in KTC data.
        Maintains KTC functionality as primary with Sleeper data as supplementary.

        Args:
            sleeper_data: Sleeper player data
        """
        new_player = KTCPlayer(
            player_name=sleeper_data['full_name'],
            position=sleeper_data['position'],
            team=sleeper_data['team'],
            value=0,  # Default KTC values
            age=None,
            rookie="No",
            rank=None,
            trend="0",
            tier="",
            position_rank="",
            league_format="1qb",  # Default
            is_redraft=False,
            tep=None,
            # Sleeper fields including injury data
            sleeper_id=sleeper_data['sleeper_id'],
            birth_date=sleeper_data['birth_date'],
            height=sleeper_data['height'],
            weight=sleeper_data['weight'],
            college=sleeper_data['college'],
            years_exp=sleeper_data['years_exp'],
            jersey_number=sleeper_data['jersey_number'],
            depth_chart_order=sleeper_data['depth_chart_order'],
            depth_chart_position=sleeper_data['depth_chart_position'],
            fantasy_positions=sleeper_data['fantasy_positions'],
            hashtag=sleeper_data['hashtag'],
            search_rank=sleeper_data['search_rank'],
            high_school=sleeper_data['high_school'],
            rookie_year=sleeper_data['rookie_year'],
            injury_status=sleeper_data['injury_status'],
            injury_start_date=sleeper_data['injury_start_date']
        )

        db.session.add(new_player)
