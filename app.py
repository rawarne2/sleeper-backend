import json
import logging
import os
import re
import tempfile
from datetime import datetime, UTC
from typing import Dict, List, Optional, Any

import boto3
import requests
from botocore.exceptions import NoCredentialsError, ClientError
from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text

from utils import (normalize_tep_level, validate_parameters, BOOLEAN_STRINGS, PLAYER_NAME_KEY,
                   POSITION_KEY, TEAM_KEY, VALUE_KEY, AGE_KEY, ROOKIE_KEY, RANK_KEY, TREND_KEY,
                   TIER_KEY, POSITION_RANK_KEY, REDRAFT_VALUE_KEY, REDRAFT_RANK_KEY,
                   REDRAFT_TREND_KEY, REDRAFT_TIER_KEY, REDRAFT_POSITION_RANK_KEY,
                   DYNASTY_URL, FANTASY_URL, DATABASE_URI, setup_logging,
                   validate_refresh_parameters, scrape_and_process_data,
                   save_and_verify_database, perform_file_operations)

# Load environment variables from .env file
load_dotenv()

# Configure logging using utils function
logger = setup_logging()

# Flask App Configuration
app = Flask(__name__)
app.config.update({
    'SQLALCHEMY_DATABASE_URI': DATABASE_URI,
    'SQLALCHEMY_TRACK_MODIFICATIONS': False,
    'SQLALCHEMY_ENGINE_OPTIONS': {
        'pool_pre_ping': True,
        'pool_recycle': 3600,
        'pool_size': 10,
        'max_overflow': 20
    }
})

db = SQLAlchemy(app)


class KTCPlayer(db.Model):
    """
    SQLAlchemy model for KTC player data.

    Stores player rankings and values for different league formats,
    including dynasty and redraft rankings with TEP variations.
    """
    # Primary key
    id = db.Column(db.Integer, primary_key=True)

    # Player identification
    player_name = db.Column(db.String(100), nullable=False)
    position = db.Column(db.String(10), nullable=False)
    team = db.Column(db.String(10))

    # Player metrics
    value = db.Column(db.Integer)
    age = db.Column(db.Float)
    rookie = db.Column(db.String(5))
    rank = db.Column(db.Integer)
    trend = db.Column(db.String(10))
    tier = db.Column(db.String(10))
    position_rank = db.Column(db.String(10))

    # Configuration
    league_format = db.Column(db.String(10), nullable=False)
    is_redraft = db.Column(db.Boolean, nullable=False)
    tep = db.Column(db.String(10))

    # Metadata
    last_updated = db.Column(db.DateTime, nullable=False,
                             default=lambda: datetime.now(UTC))

    def to_dict(self) -> Dict[str, Any]:
        """Convert player object to dictionary for API responses."""
        return {
            'id': self.id,
            RANK_KEY: self.rank,
            VALUE_KEY: self.value,
            PLAYER_NAME_KEY: self.player_name,
            POSITION_RANK_KEY: self.position_rank,
            POSITION_KEY: self.position,
            TEAM_KEY: self.team,
            AGE_KEY: self.age,
            ROOKIE_KEY: self.rookie,
            TREND_KEY: self.trend,
            TIER_KEY: self.tier
        }


class KTCScraper:
    """
    Handles scraping operations for Keep Trade Cut (KTC) player rankings.

    Extracts player data from KTC website's JavaScript playersArray and
    processes it for different league formats and TEP configurations.
    """

    @staticmethod
    def fetch_ktc_page(url: str) -> Optional[requests.Response]:
        """Fetch a page from KTC website with error handling."""
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            return response
        except requests.RequestException as e:
            logger.error("Failed to fetch page %s: %s", url, e)
            return None

    @staticmethod
    def extract_players_array(html_content: str) -> List[Dict[str, Any]]:
        """Extract the playersArray from the JavaScript in the HTML source."""
        try:
            pattern = r'var playersArray = (\[.*?\]);'
            match = re.search(pattern, html_content, re.DOTALL)

            if not match:
                logger.error("Could not find playersArray in HTML source")
                return []

            players_json = match.group(1)
            return json.loads(players_json)

        except (json.JSONDecodeError, AttributeError) as e:
            logger.error("Error parsing playersArray: %s", e)
            return []

    @staticmethod
    def _format_trend(trend_value: int) -> str:
        """Format trend value for display (e.g., 5 -> '+5', -3 -> '-3')."""
        return f"+{trend_value}" if trend_value > 0 else str(trend_value)

    @staticmethod
    def _get_tep_values(base_values: Dict[str, Any], tep_level: Optional[str]) -> tuple[int, Optional[int], Optional[str]]:
        """
        Extract appropriate values based on TEP level.

        Args:
            base_values: Base values dictionary from KTC data
            tep_level: TEP level string ('tep', 'tepp', 'teppp', or None)

        Returns:
            tuple: (value, rank, tier) for the specified TEP level
        """
        if tep_level and tep_level in base_values:
            tep_values = base_values[tep_level]
            return (
                tep_values.get('value', base_values.get('value', 0)),
                tep_values.get('rank', base_values.get('rank')),
                tep_values.get('overallTier', base_values.get('overallTier'))
            )
        else:
            # Use base values for None or invalid tep_level
            return (
                base_values.get('value', 0),
                base_values.get('rank'),
                base_values.get('overallTier')
            )

    @staticmethod
    def parse_player_data(player_obj: Dict[str, Any], league_format: str, is_redraft: bool = False, tep_level: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Parse a player object from the playersArray.

        Args:
            player_obj: Raw player data from KTC
            league_format: '1qb' or 'superflex'
            is_redraft: Whether this is redraft data
            tep_level: TEP configuration level

        Returns:
            Parsed player dictionary or None if parsing fails
        """
        try:
            # Normalize tep_level and get base values
            normalized_tep = normalize_tep_level(tep_level)
            is_1qb = league_format == '1qb'
            base_values = player_obj.get(
                'oneQBValues' if is_1qb else 'superflexValues', {}
            )

            # Get values based on TEP level
            value, rank, tier = KTCScraper._get_tep_values(
                base_values, normalized_tep)

            # Extract basic player information
            player_info = {
                'name': player_obj.get('playerName', ''),
                'position': player_obj.get('position', ''),
                'team': player_obj.get('team', ''),
                'age': player_obj.get('age'),
                'rookie': "Yes" if player_obj.get('rookie', False) else "No"
            }

            # Format additional metrics
            trend = KTCScraper._format_trend(
                base_values.get('overallTrend', 0))
            tier_str = f"Tier {tier}" if tier else ""

            pos_rank = base_values.get('positionalRank')
            position_rank = f"{player_info['position']}{pos_rank}" if pos_rank else None

            # Build result dictionary
            return KTCScraper._build_player_result(
                player_info, value, rank, trend, tier_str, position_rank, is_redraft
            )

        except Exception as e:
            logger.error(
                "Error parsing player %s: %s", player_obj.get('playerName', 'Unknown'), e)
            return None

    @staticmethod
    def _build_player_result(player_info: Dict[str, Any], value: int, rank: Optional[int],
                             trend: str, tier_str: str, position_rank: Optional[str],
                             is_redraft: bool) -> Dict[str, Any]:
        """Build the final player result dictionary based on format type."""
        base_data = {
            PLAYER_NAME_KEY: player_info['name'],
            POSITION_KEY: player_info['position'],
            TEAM_KEY: player_info['team'],
            AGE_KEY: player_info['age'],
            ROOKIE_KEY: player_info['rookie'],
        }

        if is_redraft:
            base_data.update({
                REDRAFT_VALUE_KEY: value,
                REDRAFT_RANK_KEY: rank,
                REDRAFT_TREND_KEY: trend,
                REDRAFT_TIER_KEY: tier_str,
                REDRAFT_POSITION_RANK_KEY: position_rank
            })
        else:
            base_data.update({
                VALUE_KEY: value,
                RANK_KEY: rank,
                TREND_KEY: trend,
                TIER_KEY: tier_str,
                POSITION_RANK_KEY: position_rank
            })

        return base_data

    @staticmethod
    def scrape_players_from_array(url: str, league_format: str, is_redraft: bool = False, tep_level: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Scrape players using the playersArray from JavaScript source.

        Args:
            url: KTC URL to scrape
            league_format: '1qb' or 'superflex'  
            is_redraft: Whether this is redraft data
            tep_level: TEP configuration level

        Returns:
            List of parsed player dictionaries
        """
        try:
            logger.info("Fetching data from: %s", url)
            response = KTCScraper.fetch_ktc_page(url)
            if not response:
                logger.error("Failed to fetch page: %s", url)
                return []

            players_array = KTCScraper.extract_players_array(response.text)
            if not players_array:
                logger.warning("No players found in playersArray")
                return []

            logger.info("Found %s players in playersArray", len(players_array))

            players = []
            for player_obj in players_array:
                parsed_player = KTCScraper.parse_player_data(
                    player_obj, league_format, is_redraft, tep_level)
                if parsed_player:
                    players.append(parsed_player)

            logger.info("Successfully parsed %s players", len(players))
            return players

        except Exception as e:
            logger.error("Error in scrape_players_from_array: %s", e)
            return []

    @staticmethod
    def merge_dynasty_fantasy_data(dynasty_players: List[Dict[str, Any]], fantasy_players: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Merge dynasty and fantasy player data into unified dataset.

        Args:
            dynasty_players: List of dynasty player data
            fantasy_players: List of redraft/fantasy player data

        Returns:
            List of merged player dictionaries with both dynasty and redraft data
        """
        try:
            # Create lookup dictionary for fantasy players
            fantasy_dict = {player[PLAYER_NAME_KEY]
                : player for player in fantasy_players}

            merged_players = []
            for dynasty_player in dynasty_players:
                player_name = dynasty_player[PLAYER_NAME_KEY]
                fantasy_player = fantasy_dict.get(player_name)

                # Start with dynasty data
                merged_player = dynasty_player.copy()

                # Add redraft data if available
                if fantasy_player:
                    redraft_keys = [
                        REDRAFT_VALUE_KEY, REDRAFT_POSITION_RANK_KEY,
                        REDRAFT_RANK_KEY, REDRAFT_TREND_KEY, REDRAFT_TIER_KEY
                    ]
                    for key in redraft_keys:
                        merged_player[key] = fantasy_player.get(key)

                merged_players.append(merged_player)

            logger.info(
                "Merged %s players from dynasty and fantasy data", len(merged_players))
            return merged_players

        except Exception as e:
            logger.error("Error merging dynasty and fantasy data: %s", e)
            return dynasty_players

    @staticmethod
    def scrape_ktc(is_redraft: bool, league_format: str, tep_level: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Main scraping function using the playersArray approach.

        Args:
            is_redraft: If True, scrapes both dynasty and fantasy data for merged results
            league_format: '1qb' or 'superflex'
            tep_level: TEP configuration level

        Returns:
            List of scraped and processed player data
        """
        try:
            if is_redraft:
                logger.info(
                    "Scraping dynasty data for %s format with TEP level=%s...", league_format, tep_level)
                dynasty_players = KTCScraper.scrape_players_from_array(
                    DYNASTY_URL, league_format, is_redraft=False, tep_level=tep_level)

                logger.info(
                    "Scraping fantasy data for %s format with TEP level=%s...", league_format, tep_level)
                fantasy_players = KTCScraper.scrape_players_from_array(
                    FANTASY_URL, league_format, is_redraft=True, tep_level=tep_level)

                players = KTCScraper.merge_dynasty_fantasy_data(
                    dynasty_players, fantasy_players)
            else:
                logger.info(
                    "Scraping dynasty data for %s format with TEP level=%s...", league_format, tep_level)
                players = KTCScraper.scrape_players_from_array(
                    DYNASTY_URL, league_format, is_redraft=False, tep_level=tep_level)

            logger.info("Total players after scraping: %s", len(players))
            return players

        except Exception as e:
            logger.error("Error in scrape_ktc: %s", e)
            return []


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
    Handles database operations for KTC player data.

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
        Process and validate player data for database insertion.

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

                # Create player object
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
                    tep=tep_level
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


@app.route('/api/ktc/refresh', methods=['POST'])
def refresh_rankings():
    """
    Endpoint to fetch fresh data from KTC and store in database.

    Query Parameters:
        is_redraft (str): 'true' or 'false', default 'false'
        league_format (str): '1qb' or 'superflex', default '1qb'
        tep_level (str): '', 'tep', 'tepp', or 'teppp', default ''

    Returns:
        JSON response with refresh results and operation status
    """
    try:
        # Validate parameters
        valid, league_format, tep_level, is_redraft, error_msg = validate_refresh_parameters(
            request)
        if not valid:
            return jsonify({'error': error_msg}), 400

        # Verify database connection
        logger.info("Verifying database connection before refresh...")
        if not DatabaseManager.verify_database_connection():
            logger.error(
                "Database connection verification failed before refresh")
            return jsonify({
                'error': 'Database connection failed',
                'details': 'Cannot establish database connection before starting refresh operation'
            }), 500

        # Scrape and process data
        players_sorted, scrape_error = scrape_and_process_data(
            KTCScraper, league_format, is_redraft, tep_level)
        if scrape_error:
            return jsonify({
                'error': 'No players found during scraping',
                'details': scrape_error
            }), 500

        # Save to database and verify
        added_count, db_error = save_and_verify_database(
            DatabaseManager, players_sorted, league_format, is_redraft, tep_level)
        if db_error:
            return jsonify({
                'error': 'Database operation failed',
                'details': db_error,
                'scraped_count': len(players_sorted),
                'database_success': False
            }), 500

        # Perform file operations (optional - don't fail if these fail)
        file_saved, s3_uploaded = perform_file_operations(
            FileManager, players_sorted, added_count, league_format, is_redraft, tep_level)

        # Return success response
        return jsonify({
            'message': 'Rankings refreshed successfully',
            'timestamp': datetime.now(UTC).isoformat(),
            'database_success': True,
            'file_saved': file_saved,
            's3_uploaded': s3_uploaded,
            'players_sorted': players_sorted,
            'operations_summary': {
                'players_count': len(players_sorted),
                'database_saved_count': added_count,
                'file_saved': file_saved,
                's3_uploaded': s3_uploaded
            }
        })

    except Exception as e:
        logger.error("Error refreshing rankings: %s", e)
        return jsonify({
            'error': 'Internal server error during refresh',
            'details': str(e),
            'database_success': False,
            'context': 'Error occurred in main refresh flow'
        }), 500


@app.route('/api/ktc/health', methods=['GET'])
def health_check():
    """
    Database health check endpoint.

    Returns:
        JSON response with health status and timestamp
    """
    try:
        logger.info('Performing health check...')

        # Test database connection
        connection_ok = DatabaseManager.verify_database_connection()
        timestamp = datetime.now(UTC).isoformat()

        if not connection_ok:
            return jsonify({
                'status': 'unhealthy',
                'database': 'connection_failed',
                'timestamp': timestamp
            }), 500

        return jsonify({
            'status': 'healthy',
            'database': 'connected',
            'timestamp': timestamp
        })

    except Exception as e:
        logger.error("Health check failed: %s", e)
        return jsonify({
            'status': 'unhealthy',
            'database': 'error',
            'error': str(e),
            'timestamp': datetime.now(UTC).isoformat()
        }), 500


@app.route('/api/ktc/cleanup', methods=['POST'])
def cleanup_database():
    """
    Endpoint to clean up incomplete or corrupted data.

    Query Parameters:
        is_redraft (str): 'true' or 'false', default 'false'
        league_format (str): '1qb' or 'superflex', default '1qb'  
        tep_level (str): '', 'tep', 'tepp', or 'teppp', default ''

    Returns:
        JSON response with cleanup results
    """
    try:
        # Get and validate parameters
        is_redraft_str = request.args.get('is_redraft', 'false')
        league_format_str = request.args.get('league_format', '1qb')
        tep_level_str = request.args.get('tep_level', '')

        valid, league_format, tep_level, error_msg = validate_parameters(
            is_redraft_str, league_format_str, tep_level_str
        )

        if not valid:
            return jsonify({'error': error_msg}), 400

        is_redraft = is_redraft_str.lower() in BOOLEAN_STRINGS

        # Perform cleanup
        cleanup_result = DatabaseManager.cleanup_incomplete_data(
            league_format, is_redraft, tep_level)

        if cleanup_result['status'] == 'error':
            return jsonify({
                'error': 'Cleanup operation failed',
                'details': cleanup_result['error'],
                'configuration': cleanup_result['configuration']
            }), 500

        return jsonify({
            'message': 'Database cleanup completed',
            'timestamp': datetime.now(UTC).isoformat(),
            'cleanup_result': cleanup_result
        })

    except Exception as e:
        logger.error("Error during cleanup endpoint: %s", e)
        return jsonify({
            'error': 'Internal server error during cleanup',
            'details': str(e)
        }), 500


@app.route('/api/ktc/rankings', methods=['GET'])
def get_rankings():
    """
    Endpoint to retrieve stored rankings with optional filtering.

    Query Parameters:
        is_redraft (str): 'true' or 'false', default 'false'
        league_format (str): '1qb' or 'superflex', default '1qb'
        tep_level (str): '', 'tep', 'tepp', or 'teppp', default ''

    Returns:
        JSON response with player rankings data
    """
    try:
        # Get and validate parameters
        is_redraft_str = request.args.get('is_redraft', 'false')
        league_format_str = request.args.get('league_format', '1qb')
        tep_level_str = request.args.get('tep_level', '')

        valid, league_format, tep_level, error_msg = validate_parameters(
            is_redraft_str, league_format_str, tep_level_str
        )

        if not valid:
            return jsonify({'error': error_msg}), 400

        is_redraft = is_redraft_str.lower() in BOOLEAN_STRINGS

        # Query the database
        players, last_updated = DatabaseManager.get_players_from_db(
            league_format, is_redraft, tep_level)

        if not players:
            return jsonify({
                'error': 'No rankings found for the specified parameters',
                'suggestion': 'Try calling the /api/ktc/refresh endpoint first to populate data',
                'parameters': {
                    'is_redraft': is_redraft,
                    'league_format': league_format,
                    'tep_level': tep_level
                }
            }), 404

        # Convert players to dict format
        players_data = [player.to_dict() for player in players]

        return jsonify({
            'timestamp': last_updated.isoformat() if last_updated else None,
            'is_redraft': is_redraft,
            'league_format': league_format,
            'tep_level': tep_level,
            'count': len(players),
            'players': players_data
        })

    except Exception as e:
        logger.error("Error retrieving rankings: %s", e)
        return jsonify({
            'error': 'Internal server error during rankings retrieval',
            'details': str(e)
        }), 500


@app.cli.command("init_db")
def init_db():
    """Initialize the database tables."""
    db.create_all()
    logger.info("Initialized the database.")


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True)
