"""
Utility functions and constants for the Sleeper Backend application.
"""

import logging
import os
from datetime import datetime, UTC
from typing import Optional, Tuple, List, Dict, Any

logger = logging.getLogger(__name__)

VALID_TEP_LEVELS = ['tep', 'tepp', 'teppp']
BOOLEAN_STRINGS = ['true', 't', 'yes', 'y', '1', 'false', 'f', 'no', 'n', '0']

# URLs
DYNASTY_URL = "https://keeptradecut.com/dynasty-rankings"
FANTASY_URL = "https://keeptradecut.com/fantasy-rankings"

# Player Data Keys
PLAYER_NAME_KEY = "Player Name"
POSITION_KEY = "Position"
TEAM_KEY = "Team"
VALUE_KEY = "Value"
AGE_KEY = "Age"
ROOKIE_KEY = "Rookie"
RANK_KEY = "Rank"
TREND_KEY = "Trend"
TIER_KEY = "Tier"
POSITION_RANK_KEY = "Position Rank"

# Redraft-specific Keys
REDRAFT_VALUE_KEY = "RdrftValue"
REDRAFT_RANK_KEY = "RdrftRank"
REDRAFT_TREND_KEY = "RdrftTrend"
REDRAFT_TIER_KEY = "RdrftTier"
REDRAFT_POSITION_RANK_KEY = "RdrftPosition Rank"

# Database Configuration
DATABASE_URI = os.getenv(
    'DATABASE_URL', 'postgresql://postgres:password@localhost:5433/sleeper_db')


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
        # Validate is_redraft (not returned, just validated)
        if is_redraft.lower() not in BOOLEAN_STRINGS:
            return False, '', None, 'Invalid is_redraft parameter'

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


def validate_refresh_parameters(request) -> tuple[bool, str, Optional[str], bool, Optional[str]]:
    """
    Validate refresh endpoint parameters.

    Args:
        request: Flask request object

    Returns:
        Tuple of (is_valid, league_format, tep_level, is_redraft, error_message)
    """
    is_redraft_str = request.args.get('is_redraft', 'false')
    league_format_str = request.args.get('league_format', '1qb')
    tep_level_str = request.args.get('tep_level', '')

    valid, league_format, tep_level, error_msg = validate_parameters(
        is_redraft_str, league_format_str, tep_level_str
    )

    if not valid:
        return False, '', None, False, error_msg

    is_redraft = is_redraft_str.lower() in BOOLEAN_STRINGS
    return True, league_format, tep_level, is_redraft, None


def scrape_and_process_data(ktc_scraper, league_format: str, is_redraft: bool, tep_level: Optional[str]) -> tuple[List[Dict[str, Any]], Optional[str]]:
    """
    Scrape data from KTC and process it.

    Args:
        ktc_scraper: KTCScraper instance
        league_format: League format
        is_redraft: Whether this is redraft data
        tep_level: TEP level

    Returns:
        Tuple of (sorted_players, error_message)
    """
    try:
        logger.info(
            "Starting KTC scrape for %s, redraft=%s, tep_level=%s", league_format, is_redraft, tep_level)
        players = ktc_scraper.scrape_ktc(is_redraft, league_format, tep_level)
        logger.info("Scraped %s players", len(players))

        if not players:
            return [], 'KTC scraping returned empty results - check network connectivity or site availability'

        # Sort players by rank for consistent ordering
        players_sorted = sorted(
            players, key=lambda x: x.get(RANK_KEY) or float('inf'))
        return players_sorted, None

    except Exception as e:
        logger.error("Error during scraping: %s", e)
        return [], str(e)


def save_and_verify_database(database_manager, players_sorted: List[Dict[str, Any]], league_format: str,
                             is_redraft: bool, tep_level: Optional[str]) -> tuple[int, Optional[str]]:
    """
    Save data to database and verify the operation.

    Args:
        database_manager: DatabaseManager instance
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
            players_sorted, league_format, is_redraft, tep_level)
        logger.info("Successfully saved %s players to database", added_count)

        # Verify database save was successful
        logger.info("Verifying database save operation...")
        verification_players, _ = database_manager.get_players_from_db(
            league_format, is_redraft, tep_level)

        if len(verification_players) != added_count:
            error_msg = f"Database verification failed: saved {added_count} but found {len(verification_players)} players"
            logger.error(error_msg)
            return 0, error_msg

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
        file_manager: FileManager instance
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
            'players': players_sorted
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
            f"File operations failed (database was successful): {file_error}")

    return file_saved, s3_uploaded
