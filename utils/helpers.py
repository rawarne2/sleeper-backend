"""Logging, validation, and cross-cutting helpers."""
import logging
import os
from datetime import datetime, UTC
from typing import Any, Dict, List, Optional

from utils.constants import VALID_TEP_LEVELS

logger = logging.getLogger(__name__)


def setup_logging():
    """Configure logging for the application."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    return logging.getLogger(__name__)


def validate_parameters(is_redraft: str, league_format: str, tep_level: str) -> tuple[bool, str, Optional[str], Optional[str]]:
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
        if is_redraft.lower() not in ('true', 'false'):
            return False, '', None, 'Invalid is_redraft parameter - must be "true" or "false"'

        normalized_league_format = league_format.lower()
        if normalized_league_format not in ('1qb', 'superflex'):
            return False, '', None, 'Invalid league_format parameter'

        normalized_tep_level = normalize_tep_level(tep_level)
        if tep_level and normalized_tep_level is None:
            return False, normalized_league_format, None, 'Invalid tep_level parameter'

        return True, normalized_league_format, normalized_tep_level, None

    except Exception as e:
        logger.error("Error validating parameters: %s", e)
        return False, '', None, 'Parameter validation error'


def normalize_tep_level(tep_level: Optional[str]) -> Optional[str]:
    """Normalize TEP level string to standard format."""
    if not tep_level or tep_level == "":
        return None

    normalized = tep_level.lower()
    return normalized if normalized in VALID_TEP_LEVELS else None


def create_player_match_key(player_name: str, position: str) -> str:
    """Create a match key for efficient player lookups."""
    from data_types.normalization import normalize_name_for_matching

    if not player_name or not position:
        return ""

    normalized_name = normalize_name_for_matching(player_name)
    return f"{normalized_name}-{position.upper()}"


def save_and_verify_database(database_manager, players_sorted: List[Dict[str, Any]], league_format: str,
                             is_redraft: bool) -> tuple[int, Optional[str]]:
    """Save data to database and verify the operation."""
    try:
        logger.info("Starting database save operation...")
        added_count = database_manager.save_players_to_db(
            players_sorted, league_format, is_redraft)
        logger.info("Successfully saved %s players to database", added_count)

        logger.info("Verifying database save operation...")
        verification_players, _ = database_manager.get_players_from_db(
            league_format)

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


def ktc_export_json_and_s3_enabled() -> bool:
    """When false (default), skip writing ranking JSON files and S3 uploads after KTC refresh."""
    return os.getenv("KTC_EXPORT_JSON_AND_S3", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def perform_file_operations(file_manager, players_sorted: List[Dict[str, Any]], added_count: int,
                            league_format: str, is_redraft: bool, tep_level: Optional[str]) -> tuple[bool, bool]:
    """Perform file and S3 operations."""
    file_saved = False
    s3_uploaded = False

    if not ktc_export_json_and_s3_enabled():
        return file_saved, s3_uploaded

    try:
        players_dict = []
        for player in players_sorted:
            if hasattr(player, 'to_dict'):
                players_dict.append(player.to_dict())
            else:
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

        json_filename = file_manager.create_descriptive_filename(
            league_format, is_redraft, tep_level, "refresh", True)
        file_saved = file_manager.save_json_to_file(json_data, json_filename)

        if not file_saved:
            logger.warning(
                "File save operation failed, but database operation was successful")

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
