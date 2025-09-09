"""
Utility functions and constants for the Sleeper Backend application.
"""

import logging
import os
from datetime import datetime, UTC
from typing import Optional, Tuple, List, Dict, Any

logger = logging.getLogger(__name__)

VALID_TEP_LEVELS = ['tep', 'tepp', 'teppp']

# URLs
DYNASTY_URL = "https://keeptradecut.com/dynasty-rankings"
FANTASY_URL = "https://keeptradecut.com/fantasy-rankings"
SLEEPER_API_URL = "https://api.sleeper.app/v1/players/nfl"

# Player Data Keys - Updated to match actual API field names
# KTC API uses these field names in the scraped data
PLAYER_NAME_KEY = "playerName"  # KTC uses 'playerName'
POSITION_KEY = "position"       # Both APIs use 'position'
TEAM_KEY = "team"              # Both APIs use 'team'
AGE_KEY = "age"                # Both APIs use 'age'
ROOKIE_KEY = "rookie"          # KTC uses 'rookie' (boolean)

# These were unused redraft-specific keys that don't match actual data structure
# Removed to reduce complexity

# Database Configuration
DATABASE_URI = os.getenv(
    'TEST_DATABASE_URI',
    os.getenv('DATABASE_URL',
              'postgresql://postgres:password@localhost:5433/sleeper_db?sslmode=disable')
)


def setup_logging():
    """Configure logging for the application."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    return logging.getLogger(__name__)


def validate_parameters(is_redraft: str, league_format: str, tep_level: str) -> Tuple[bool, str, Optional[str], Optional[str]]:
    """
    Validate and normalize request parameters.

    Args:
        is_redraft: String representation of boolean
        league_format: League format string
        tep_level: TEP level string

    Returns:
        Tuple of (is_valid, normalized_league_format, normalized_tep_level, error_message)
    """
    try:
        # Validate is_redraft
        if is_redraft.lower() not in ('true', 'false'):
            return False, '', None, 'Invalid is_redraft parameter - must be "true" or "false"'

        # Simple league format normalization - just lowercase
        normalized_league_format = league_format.lower()
        if normalized_league_format not in ('1qb', 'superflex'):
            return False, '', None, 'Invalid league_format parameter'

        # Simple tep level normalization
        normalized_tep_level = normalize_tep_level(tep_level)
        if tep_level and normalized_tep_level is None:
            return False, normalized_league_format, None, 'Invalid tep_level parameter'

        return True, normalized_league_format, normalized_tep_level, None

    except Exception as e:
        logger.error("Error validating parameters: %s", e)
        return False, '', None, 'Parameter validation error'


def normalize_tep_level(tep_level: Optional[str]) -> Optional[str]:
    """
    Normalize TEP level string to standard format.

    Args:
        tep_level: TEP level string ('tep', 'tepp', 'teppp', or None)

    Returns:
        Normalized TEP level string or None for base/default
    """
    if not tep_level or tep_level == "":
        return None

    normalized = tep_level.lower()
    return normalized if normalized in VALID_TEP_LEVELS else None


def create_player_match_key(player_name: str, position: str) -> str:
    """
    Create a match key for efficient player lookups.

    Args:
        player_name: Player name (will be normalized)
        position: Player position

    Returns:
        Match key string in format "normalized_name-position"
    """
    from data_types import normalize_name_for_matching

    if not player_name or not position:
        return ""

    normalized_name = normalize_name_for_matching(player_name)
    return f"{normalized_name}-{position.upper()}"


def save_and_verify_database(database_manager, players_sorted: List[Dict[str, Any]], league_format: str,
                             is_redraft: bool) -> tuple[int, Optional[str]]:
    """
    Save data to database and verify the operation.

    Args:
        database_manager: DatabaseManager class
        players_sorted: Sorted list of player data
        league_format: League format
        is_redraft: Whether this is redraft data
        tep_level: TEP level

    Returns:
        Tuple of (added_count, error_message)
    """
    try:
        logger.info("Starting database save operation...")
        added_count = database_manager.save_players_to_db(
            players_sorted, league_format, is_redraft)
        logger.info("Successfully saved %s players to database", added_count)

        # Verify database save was successful - provides confidence in data integrity
        logger.info("Verifying database save operation...")
        verification_players, _ = database_manager.get_players_from_db(
            league_format)

        # Simple verification - just check that we have some players saved
        # Note: We expect merged data to have fewer players than raw Sleeper data
        # because we only save players with valid positions and KTC values
        if len(verification_players) == 0:
            error_msg = f"Database verification failed: no players found after saving {added_count} players"
            logger.error(error_msg)
            return 0, error_msg
        elif len(verification_players) != added_count:
            logger.info(
                "Database verification: saved %s players, found %s in database (normal when filtering for players with KTC values)",
                added_count, len(verification_players))

        logger.info(
            "Database operation verified successfully: %s players confirmed in database", len(verification_players))
        return added_count, None

    except Exception as e:
        logger.error("Database operation failed: %s", e)
        return 0, str(e)


def perform_file_operations(file_manager, players_sorted: List[Dict[str, Any]], added_count: int,
                            league_format: str, is_redraft: bool, tep_level: Optional[str]) -> tuple[bool, bool]:
    """
    Perform file and S3 operations.

    Args:
        file_manager: FileManager class
        players_sorted: Sorted list of player data
        added_count: Number of players added to database
        league_format: League format
        is_redraft: Whether this is redraft data
        tep_level: TEP level

    Returns:
        Tuple of (file_saved, s3_uploaded)
    """
    file_saved = False
    s3_uploaded = False

    try:
        # Create JSON data for file operations
        # Convert players to dict format using to_dict() method for consistent structure
        players_dict = []
        for player in players_sorted:
            if hasattr(player, 'to_dict'):
                players_dict.append(player.to_dict())
            else:
                # Handle case where player is already a dict
                players_dict.append(player)

        json_data = {
            'message': 'Rankings refreshed successfully',
            'timestamp': datetime.now(UTC).isoformat(),
            'count': len(players_sorted),
            'database_count': added_count,
            'database_verified': True,
            'parameters': {
                'is_redraft': is_redraft,
                'league_format': league_format,
                'tep_level': tep_level
            },
            'players': players_dict
        }

        # Save to file with descriptive naming
        json_filename = file_manager.create_descriptive_filename(
            league_format, is_redraft, tep_level, "refresh", True)
        file_saved = file_manager.save_json_to_file(json_data, json_filename)

        if not file_saved:
            logger.warning(
                "File save operation failed, but database operation was successful")

        # Upload to S3 if configured with descriptive naming
        bucket_name = os.getenv('S3_BUCKET')
        if bucket_name:
            object_key = file_manager.create_descriptive_filename(
                league_format, is_redraft, tep_level, "refresh", True)
            s3_uploaded = file_manager.upload_json_to_s3(
                json_data, bucket_name, object_key)

            if not s3_uploaded:
                logger.warning(
                    "S3 upload failed, but database and file operations were successful")

    except Exception as file_error:
        logger.error(
            "File operations failed (database was successful): %s", file_error)

    return file_saved, s3_uploaded
