from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, UTC
import requests
import os
import boto3
from botocore.exceptions import NoCredentialsError, ClientError
from sqlalchemy import text
import json
import tempfile
import re
from dotenv import load_dotenv
import logging
from typing import Dict, List, Optional, Union, Any

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Constants
LEAGUE_FORMATS = ['1QB', 'SF']
TEP_VALUES = [0, 1, 2, 3]
BOOLEAN_STRINGS = ['true', 't', 'yes', 'y', '1']
MAX_SCRAPE_PAGES = 10
DYNASTY_URL = "https://keeptradecut.com/dynasty-rankings"
FANTASY_URL = "https://keeptradecut.com/fantasy-rankings"

# Database configuration
# Use in-memory SQLite for Vercel serverless deployment
DATABASE_URI = os.getenv('DATABASE_URL', 'sqlite:///:memory:')

# HTTP status codes
HTTP_BAD_REQUEST = 400
HTTP_NOT_FOUND = 404
HTTP_INTERNAL_SERVER_ERROR = 500

# Request timeout
REQUEST_TIMEOUT = 30

# File extensions
JSON_EXTENSION = '.json'

# Player data constants
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
REDRAFT_VALUE_KEY = "RdrftValue"
REDRAFT_RANK_KEY = "RdrftRank"
REDRAFT_TREND_KEY = "RdrftTrend"
REDRAFT_TIER_KEY = "RdrftTier"
REDRAFT_POSITION_RANK_KEY = "RdrftPosition Rank"

# Default values
DEFAULT_ROOKIE = "No"
DEFAULT_TREND = "0"
UNKNOWN_PLAYER = "Unknown"

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URI
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,
    'pool_recycle': 3600,
    'connect_args': {
        'timeout': 30,
        'check_same_thread': False
    }
}
db = SQLAlchemy(app)


class KTCPlayer(db.Model):
    """SQLAlchemy model for KTC player data"""
    id = db.Column(db.Integer, primary_key=True)
    player_name = db.Column(db.String(100), nullable=False)
    position = db.Column(db.String(10), nullable=False)
    team = db.Column(db.String(10))
    value = db.Column(db.Integer)
    age = db.Column(db.Float)
    rookie = db.Column(db.String(5))
    rank = db.Column(db.Integer)
    trend = db.Column(db.String(10))
    tier = db.Column(db.String(10))
    position_rank = db.Column(db.String(10))
    league_format = db.Column(db.String(10), nullable=False)
    is_redraft = db.Column(db.Boolean, nullable=False)
    tep = db.Column(db.Integer, nullable=False)
    last_updated = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(UTC))

    def to_dict(self) -> Dict[str, Any]:
        """Convert player object to dictionary"""
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
    """Class to handle KTC scraping operations"""

    @staticmethod
    def fetch_ktc_page(url: str) -> Optional[requests.Response]:
        """Fetch a page from KTC website"""
        try:
            response = requests.get(url, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            return response
        except requests.RequestException as e:
            logger.error(f"Failed to fetch page {url}: {e}")
            return None

    @staticmethod
    def extract_players_array(html_content: str) -> List[Dict[str, Any]]:
        """Extract the playersArray from the JavaScript in the HTML source"""
        try:
            pattern = r'var playersArray = (\[.*?\]);'
            match = re.search(pattern, html_content, re.DOTALL)

            if not match:
                logger.error("Could not find playersArray in HTML source")
                return []

            players_json = match.group(1)
            return json.loads(players_json)

        except (json.JSONDecodeError, AttributeError) as e:
            logger.error(f"Error parsing playersArray: {e}")
            return []

    @staticmethod
    def parse_player_data(player_obj: Dict[str, Any], league_format: str, is_redraft: bool = False, tep: int = 0) -> Optional[Dict[str, Any]]:
        """Parse a player object from the playersArray"""
        try:
            is_1qb = league_format == '1QB'
            base_values = player_obj.get('oneQBValues', {}) if is_1qb else player_obj.get(
                'superflexValues', {})

            # Select the appropriate values object based on TEP setting
            if tep == 1:
                tep_values = base_values.get('tep', {})
                # Use TEP values if available, otherwise fall back to base values
                value = tep_values.get('value', base_values.get('value', 0))
                rank = tep_values.get('rank', base_values.get('rank'))
                tier = tep_values.get(
                    'overallTier', base_values.get('overallTier'))
            elif tep == 2:
                tepp_values = base_values.get('tepp', {})
                # Use TEPP values if available, otherwise fall back to base values
                value = tepp_values.get('value', base_values.get('value', 0))
                rank = tepp_values.get('rank', base_values.get('rank'))
                tier = tepp_values.get(
                    'overallTier', base_values.get('overallTier'))
            elif tep == 3:
                teppp_values = base_values.get('teppp', {})
                # Use TEPPP values if available, otherwise fall back to base values
                value = teppp_values.get('value', base_values.get('value', 0))
                rank = teppp_values.get('rank', base_values.get('rank'))
                tier = teppp_values.get(
                    'overallTier', base_values.get('overallTier'))
            else:
                # TEP = 0, use base values
                value = base_values.get('value', 0)
                rank = base_values.get('rank')
                tier = base_values.get('overallTier')

            # Extract basic player info
            player_name = player_obj.get('playerName', '')
            position = player_obj.get('position', '')
            team = player_obj.get('team', '')
            age = player_obj.get('age')
            rookie = "Yes" if player_obj.get(
                'rookie', False) else DEFAULT_ROOKIE

            # Format trend using base values (trend typically doesn't change with TEP)
            trend = KTCScraper._format_trend(
                base_values.get('overallTrend', 0))

            # Format tier string
            tier_str = f"Tier {tier}" if tier else ""

            # Extract positional rank using base values (positional rank typically doesn't change with TEP)
            pos_rank = base_values.get('positionalRank')
            position_rank = f"{position}{pos_rank}" if pos_rank else None

            # Build result based on format type
            if is_redraft:
                return {
                    PLAYER_NAME_KEY: player_name,
                    POSITION_KEY: position,
                    TEAM_KEY: team,
                    REDRAFT_VALUE_KEY: value,
                    AGE_KEY: age,
                    ROOKIE_KEY: rookie,
                    REDRAFT_RANK_KEY: rank,
                    REDRAFT_TREND_KEY: trend,
                    REDRAFT_TIER_KEY: tier_str,
                    REDRAFT_POSITION_RANK_KEY: position_rank
                }
            else:
                return {
                    PLAYER_NAME_KEY: player_name,
                    POSITION_KEY: position,
                    TEAM_KEY: team,
                    VALUE_KEY: value,
                    AGE_KEY: age,
                    ROOKIE_KEY: rookie,
                    RANK_KEY: rank,
                    TREND_KEY: trend,
                    TIER_KEY: tier_str,
                    POSITION_RANK_KEY: position_rank
                }

        except Exception as e:
            logger.error(
                f"Error parsing player {player_obj.get('playerName', UNKNOWN_PLAYER)}: {e}")
            return None

    @staticmethod
    def _format_trend(trend_value: int) -> str:
        """Format trend value for display"""
        return f"+{trend_value}" if trend_value > 0 else str(trend_value)

    @staticmethod
    def scrape_players_from_array(url: str, league_format: str, is_redraft: bool = False, tep: int = 0) -> List[Dict[str, Any]]:
        """Scraping function that uses the playersArray from JavaScript source"""
        try:
            logger.info(f"Fetching data from: {url}")
            response = KTCScraper.fetch_ktc_page(url)
            if not response:
                logger.error(f"Failed to fetch page: {url}")
                return []

            players_array = KTCScraper.extract_players_array(response.text)
            if not players_array:
                logger.warning("No players found in playersArray")
                return []

            logger.info(f"Found {len(players_array)} players in playersArray")

            players = []
            for player_obj in players_array:
                parsed_player = KTCScraper.parse_player_data(
                    player_obj, league_format, is_redraft, tep)
                if parsed_player:
                    players.append(parsed_player)

            logger.info(f"Successfully parsed {len(players)} players")
            return players

        except Exception as e:
            logger.error(f"Error in scrape_players_from_array: {e}")
            return []

    @staticmethod
    def merge_dynasty_fantasy_data(dynasty_players: List[Dict[str, Any]], fantasy_players: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Merge dynasty and fantasy player data"""
        try:
            fantasy_dict = {player[PLAYER_NAME_KEY]
                : player for player in fantasy_players}

            merged_players = []
            for dynasty_player in dynasty_players:
                player_name = dynasty_player[PLAYER_NAME_KEY]
                fantasy_player = fantasy_dict.get(player_name)

                merged_player = dynasty_player.copy()
                if fantasy_player:
                    merged_player.update({
                        REDRAFT_VALUE_KEY: fantasy_player.get(REDRAFT_VALUE_KEY),
                        REDRAFT_POSITION_RANK_KEY: fantasy_player.get(REDRAFT_POSITION_RANK_KEY),
                        REDRAFT_RANK_KEY: fantasy_player.get(REDRAFT_RANK_KEY),
                        REDRAFT_TREND_KEY: fantasy_player.get(REDRAFT_TREND_KEY),
                        REDRAFT_TIER_KEY: fantasy_player.get(REDRAFT_TIER_KEY)
                    })

                merged_players.append(merged_player)

            logger.info(
                f"Merged {len(merged_players)} players from dynasty and fantasy data")
            return merged_players

        except Exception as e:
            logger.error(f"Error merging dynasty and fantasy data: {e}")
            return dynasty_players

    @staticmethod
    def scrape_ktc(is_redraft: bool, league_format: str, tep: int = 0) -> List[Dict[str, Any]]:
        """Main scraping function using the playersArray approach"""
        try:
            if is_redraft:
                logger.info(
                    f"Scraping dynasty data for {league_format} format with TEP={tep}...")
                dynasty_players = KTCScraper.scrape_players_from_array(
                    DYNASTY_URL, league_format, is_redraft=False, tep=tep)

                logger.info(
                    f"Scraping fantasy data for {league_format} format with TEP={tep}...")
                fantasy_players = KTCScraper.scrape_players_from_array(
                    FANTASY_URL, league_format, is_redraft=True, tep=tep)

                players = KTCScraper.merge_dynasty_fantasy_data(
                    dynasty_players, fantasy_players)
            else:
                logger.info(
                    f"Scraping dynasty data for {league_format} format with TEP={tep}...")
                players = KTCScraper.scrape_players_from_array(
                    DYNASTY_URL, league_format, is_redraft=False, tep=tep)

            logger.info(f"Total players after scraping: {len(players)}")
            return players

        except Exception as e:
            logger.error(f"Error in scrape_ktc: {e}")
            return []


class FileManager:
    """Class to handle file operations"""

    @staticmethod
    def get_data_directory() -> str:
        """Get the appropriate data directory path"""
        return '/app/data-files' if os.path.exists('/app') else './data-files'

    @staticmethod
    def create_json_filename(league_format: str, is_redraft: bool, tep: int, prefix: str = "ktc") -> str:
        """Create standardized JSON filename"""
        format_type = 'redraft' if is_redraft else 'dynasty'
        return f"{prefix}_{league_format.lower()}_{format_type}_tep{tep}.json"

    @staticmethod
    def save_json_to_file(json_data: Dict[str, Any], filename: str) -> bool:
        """Save JSON data to a local file in the data-files directory"""
        try:
            data_dir = FileManager.get_data_directory()
            os.makedirs(data_dir, exist_ok=True)
            file_path = os.path.join(data_dir, filename)

            logger.info(f"Saving JSON data to {file_path}...")
            with open(file_path, 'w') as json_file:
                json.dump(json_data, json_file, indent=2, default=str)

            logger.info(f"Successfully saved JSON data to {file_path}")
            return True
        except Exception as e:
            logger.error(f"Error saving JSON to file: {e}")
            return False

    @staticmethod
    def upload_json_to_s3(json_data: Dict[str, Any], bucket_name: str, object_key: str) -> bool:
        """Upload JSON data to an S3 bucket or access point"""
        try:
            # Check if bucket_name is an access point alias
            s3_client = boto3.client('s3')

            with tempfile.NamedTemporaryFile(mode='w', suffix=JSON_EXTENSION, delete=False) as temp_file:
                json.dump(json_data, temp_file, indent=2, default=str)
                temp_file_path = temp_file.name

            logger.info(
                f"Uploading JSON to s3://{bucket_name}/{object_key}...")

            # Upload to S3
            try:
                s3_client.upload_file(temp_file_path, bucket_name, object_key)
                logger.info(
                    f"Successfully uploaded JSON to s3://{bucket_name}/{object_key}")
                os.unlink(temp_file_path)
                return True
            except Exception as e:
                logger.error(f"Error uploading to S3: {e}")
                os.unlink(temp_file_path)
                return False

        except NoCredentialsError:
            logger.error(
                "AWS credentials not found. Make sure you've configured your AWS credentials.")
            return False
        except ClientError as e:
            logger.error(f"Error uploading to S3: {e}")
            # Log additional details for debugging
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            error_message = e.response.get(
                'Error', {}).get('Message', 'Unknown error')
            logger.error(f"Error Code: {error_code}, Message: {error_message}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error uploading to S3: {e}")
            return False


class RequestValidator:
    """Class to handle request validation"""

    @staticmethod
    def validate_parameters(is_redraft: str, league_format: str, tep: str) -> tuple[bool, str, int, Optional[str]]:
        """Validate request parameters"""
        try:
            # Validate is_redraft
            is_redraft_bool = is_redraft.lower() in BOOLEAN_STRINGS

            # Validate league_format
            league_format_upper = league_format.upper()
            if league_format_upper not in LEAGUE_FORMATS:
                return False, '', 0, f'Invalid league format. Must be one of: {", ".join(LEAGUE_FORMATS)}'

            # Validate tep
            try:
                tep_int = int(tep)
                if tep_int not in TEP_VALUES:
                    return False, '', 0, f'Invalid TEP value. Must be one of: {", ".join(map(str, TEP_VALUES))}'
            except ValueError:
                return False, '', 0, 'TEP value must be an integer'

            return True, league_format_upper, tep_int, None

        except Exception as e:
            logger.error(f"Error validating parameters: {e}")
            return False, '', 0, 'Parameter validation error'


class DatabaseManager:
    """Class to handle database operations"""

    @staticmethod
    def save_players_to_db(players: List[Dict[str, Any]], league_format: str, is_redraft: bool, tep: int) -> int:
        """Save players to database with simplified error handling"""
        try:
            # Create tables if they don't exist
            db.create_all()

            logger.info(
                f"Starting database operation for {league_format}, redraft={is_redraft}, tep={tep}")

            # Delete existing data for this configuration
            deleted_count = KTCPlayer.query.filter_by(
                league_format=league_format,
                is_redraft=is_redraft,
                tep=tep
            ).delete(synchronize_session=False)

            logger.info(f"Deleted {deleted_count} existing records")

            # Process and add new data
            added_count = 0
            for player in players:
                value, position_rank = DatabaseManager._extract_player_values(
                    player, is_redraft)

                if value is None or value == 0:
                    logger.debug(
                        f"Skipping player {player.get(PLAYER_NAME_KEY, UNKNOWN_PLAYER)} - no value")
                    continue

                # Validate required fields
                player_name = player.get(PLAYER_NAME_KEY)
                position = player.get(POSITION_KEY)

                if not player_name or not position:
                    logger.warning(
                        f"Skipping player with missing required fields: {player}")
                    continue

                ktc_player = KTCPlayer(
                    player_name=player_name,
                    position=position,
                    team=player.get(TEAM_KEY),
                    value=value,
                    age=player.get(AGE_KEY),
                    rookie=player.get(ROOKIE_KEY, DEFAULT_ROOKIE),
                    rank=player.get(RANK_KEY),
                    trend=player.get(TREND_KEY, DEFAULT_TREND),
                    tier=player.get(TIER_KEY),
                    position_rank=position_rank,
                    league_format=league_format,
                    is_redraft=is_redraft,
                    tep=tep
                )
                db.session.add(ktc_player)
                added_count += 1

            logger.info(f"Adding {added_count} records to database")
            db.session.commit()
            logger.info("Database commit successful")

            return added_count

        except Exception as e:
            logger.error(f"Database operation failed: {e}")
            db.session.rollback()
            raise Exception(f"Database save operation failed: {e}")

    @staticmethod
    def _extract_player_values(player: Dict[str, Any], is_redraft: bool) -> tuple[Optional[int], Optional[str]]:
        """Extract value and position rank from player data"""
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
                        f"Could not convert value '{value}' to int for player {player.get(PLAYER_NAME_KEY, UNKNOWN_PLAYER)}")
                    value = 0

            return value, position_rank

        except Exception as e:
            logger.error(f"Error extracting player values: {e}")
            return 0, None

    @staticmethod
    def get_players_from_db(league_format: str, is_redraft: bool, tep: int) -> tuple[List[KTCPlayer], Optional[datetime]]:
        """Get players from database"""
        players = KTCPlayer.query.filter_by(
            league_format=league_format,
            is_redraft=is_redraft,
            tep=tep
        ).order_by(KTCPlayer.rank.asc()).all()

        last_updated = max(
            player.last_updated for player in players) if players else None

        return players, last_updated

    @staticmethod
    def verify_database_connection() -> bool:
        """Verify database connection and basic functionality"""
        try:
            # Test basic query
            player = db.session.execute(db.text("SELECT 1")).fetchone()
            print(player)
            logger.info("Database connection verified successfully")
            return True
        except Exception as e:
            logger.error(f"Database connection verification failed: {e}")
            return False

    @staticmethod
    def get_database_stats() -> Dict[str, Any]:
        """Get database statistics for debugging"""
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
            logger.error(f"Error getting database stats: {e}")
            return {'error': str(e)}


@app.route('/api/ktc/health', methods=['GET'])
def health_check():
    """Database health check endpoint"""
    try:
        # Test database connection
        connection_ok = DatabaseManager.verify_database_connection()

        if not connection_ok:
            return jsonify({
                'status': 'unhealthy',
                'database': 'connection_failed',
                'timestamp': datetime.now(UTC).isoformat()
            }), HTTP_INTERNAL_SERVER_ERROR

        # Get database statistics
        stats = DatabaseManager.get_database_stats()

        return jsonify({
            'status': 'healthy',
            'database': 'connected',
            'timestamp': datetime.now(UTC).isoformat(),
            'stats': stats
        })

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({
            'status': 'unhealthy',
            'database': 'error',
            'error': str(e),
            'timestamp': datetime.now(UTC).isoformat()
        }), HTTP_INTERNAL_SERVER_ERROR


@app.route('/api/ktc/refresh', methods=['POST'])
def refresh_rankings():
    """Endpoint to fetch fresh data from KTC and store in database"""
    try:
        # Get and validate parameters
        is_redraft_str = request.args.get('is_redraft', 'false')
        league_format_str = request.args.get('league_format', '1QB')
        tep_str = request.args.get('tep', '0')

        valid, league_format, tep, error_msg = RequestValidator.validate_parameters(
            is_redraft_str, league_format_str, tep_str
        )

        if not valid:
            return jsonify({'error': error_msg}), HTTP_BAD_REQUEST

        is_redraft = is_redraft_str.lower() in BOOLEAN_STRINGS

        # Scrape fresh data
        players = KTCScraper.scrape_ktc(is_redraft, league_format, tep)
        logger.info(f"Scraped {len(players)} players")

        if not players:
            return jsonify({'error': 'No players found during scraping'}), HTTP_INTERNAL_SERVER_ERROR

        # Sort players by rank for consistent ordering
        players_sorted = sorted(
            players, key=lambda x: x.get(RANK_KEY) or float('inf'))

        # Save to database
        added_count = DatabaseManager.save_players_to_db(
            players_sorted, league_format, is_redraft, tep)
        logger.info(f"Successfully saved {added_count} players to database")

        # Create JSON data for file operations
        json_data = {
            'message': 'Rankings refreshed successfully',
            'timestamp': datetime.now(UTC).isoformat(),
            'count': len(players_sorted),
            'database_count': added_count,
            'parameters': {
                'is_redraft': is_redraft,
                'league_format': league_format,
                'tep': tep
            },
            'players': players_sorted
        }

        # Save to file and S3
        json_filename = FileManager.create_json_filename(
            league_format, is_redraft, tep, "ktc_refresh")
        file_saved = FileManager.save_json_to_file(json_data, json_filename)

        s3_uploaded = False
        bucket_name = os.getenv('S3_BUCKET')
        if bucket_name:
            object_key = FileManager.create_json_filename(
                league_format, is_redraft, tep, "ktc_refresh")
            s3_uploaded = FileManager.upload_json_to_s3(
                json_data, bucket_name, object_key)

        return jsonify({
            'message': 'Rankings refreshed successfully',
            'timestamp': datetime.now(UTC).isoformat(),
            'count': added_count,
            'file_saved': file_saved,
            's3_uploaded': s3_uploaded,
            'data': json_data
        })

    except Exception as e:
        logger.error(f"Error refreshing rankings: {e}")
        return jsonify({
            'error': 'Internal server error during refresh',
            'details': str(e)
        }), HTTP_INTERNAL_SERVER_ERROR


@app.route('/api/ktc/rankings', methods=['GET'])
def get_rankings():
    """Endpoint to retrieve stored rankings with optional filtering"""
    try:
        # Get and validate parameters
        is_redraft_str = request.args.get('is_redraft', 'false')
        league_format_str = request.args.get('league_format', '1QB')
        tep_str = request.args.get('tep', '0')

        valid, league_format, tep, error_msg = RequestValidator.validate_parameters(
            is_redraft_str, league_format_str, tep_str
        )

        if not valid:
            return jsonify({'error': error_msg}), HTTP_BAD_REQUEST

        is_redraft = is_redraft_str.lower() in BOOLEAN_STRINGS

        # Query the database
        players, last_updated = DatabaseManager.get_players_from_db(
            league_format, is_redraft, tep)

        if not players:
            return jsonify({
                'error': 'No rankings found for the specified parameters',
                'suggestion': 'Try calling the /api/ktc/refresh endpoint first to populate data',
                'parameters': {
                    'is_redraft': is_redraft,
                    'league_format': league_format,
                    'tep': tep
                }
            }), HTTP_NOT_FOUND

        # Convert players to dict format
        players_data = [player.to_dict() for player in players]

        return jsonify({
            'timestamp': last_updated.isoformat(),
            'is_redraft': is_redraft,
            'league_format': league_format,
            'tep': tep,
            'count': len(players),
            'players': players_data
        })

    except Exception as e:
        logger.error(f"Error retrieving rankings: {e}")
        return jsonify({
            'error': 'Internal server error during rankings retrieval',
            'details': str(e)
        }), HTTP_INTERNAL_SERVER_ERROR


@app.cli.command("init_db")
def init_db():
    """Initialize the database"""
    db.create_all()
    logger.info("Initialized the database.")


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True)
