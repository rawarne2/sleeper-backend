import json
import logging
import re
from datetime import datetime, UTC
from typing import Dict, List, Optional, Any

import requests

from utils import (normalize_tep_level, PLAYER_NAME_KEY, POSITION_KEY, TEAM_KEY,
                   VALUE_KEY, AGE_KEY, ROOKIE_KEY, RANK_KEY, TREND_KEY, TIER_KEY,
                   POSITION_RANK_KEY, REDRAFT_VALUE_KEY, REDRAFT_RANK_KEY,
                   REDRAFT_TREND_KEY, REDRAFT_TIER_KEY, REDRAFT_POSITION_RANK_KEY,
                   DYNASTY_URL, FANTASY_URL, SLEEPER_API_URL, setup_logging)

logger = setup_logging()


class SleeperScraper:
    """
    Handles scraping operations for Sleeper API player data.

    Fetches and processes player data from Sleeper API,
    filtering for active NFL players in fantasy-relevant positions,
    with comprehensive error handling and logging patterns.
    """

    VALID_POSITIONS = {'QB', 'RB', 'WR', 'TE', 'RDP'}

    @staticmethod
    def fetch_sleeper_data() -> Optional[Dict[str, Any]]:
        """
        Fetch all NFL players from Sleeper API.

        Returns:
            Dictionary of player data keyed by sleeper_id, or None if failed
        """
        try:
            logger.info("Fetching players from Sleeper API...")
            response = requests.get(SLEEPER_API_URL, timeout=60)
            response.raise_for_status()

            players_data = response.json()
            logger.info(
                "Successfully fetched %s players from Sleeper API", len(players_data))
            return players_data

        except requests.RequestException as e:
            logger.error("Failed to fetch Sleeper API data: %s", e)
            return None
        except json.JSONDecodeError as e:
            logger.error("Failed to parse Sleeper API response: %s", e)
            return None

    @staticmethod
    def parse_sleeper_players(players_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Parse and filter Sleeper player data into standardized format.

        Args:
            players_data: Raw player data from Sleeper API

        Returns:
            List of parsed and filtered player dictionaries
        """
        if not players_data:
            logger.error("No player data provided for parsing")
            return []

        filtered_players = []
        invalid_players = 0

        for sleeper_id, player_data in players_data.items():
            try:
                if not player_data.get('active', False):
                    continue

                position = player_data.get('position', '').upper()
                if position not in SleeperScraper.VALID_POSITIONS:
                    continue

                # Validate required fields
                if not player_data.get('full_name'):
                    invalid_players += 1
                    continue

                # Parse and validate data with comprehensive error handling
                parsed_player = SleeperScraper._parse_individual_player(
                    sleeper_id, player_data)
                if parsed_player:
                    filtered_players.append(parsed_player)
                else:
                    invalid_players += 1

            except Exception as e:
                logger.warning("Error processing player %s: %s", sleeper_id, e)
                invalid_players += 1
                continue

        logger.info("Successfully parsed %s players, skipped %s invalid players",
                    len(filtered_players), invalid_players)
        return filtered_players

    @staticmethod
    def _parse_individual_player(sleeper_id: str, player_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Parse individual player data with comprehensive validation.

        Includes injury-related fields from Sleeper API.

        Args:
            sleeper_id: Sleeper player ID
            player_data: Raw player data from Sleeper API

        Returns:
            Parsed player dictionary or None if parsing fails
        """
        try:
            # Comprehensive data validation and sanitization
            validated_data = SleeperScraper._validate_player_data(player_data)
            if not validated_data:
                return None

            # Parse birth date with proper error handling
            birth_date = None
            if player_data.get('birth_date'):
                try:
                    birth_date = datetime.strptime(
                        player_data['birth_date'], '%Y-%m-%d').date()
                except ValueError:
                    logger.warning("Invalid birth_date format for player %s: %s",
                                   player_data.get('full_name'), player_data.get('birth_date'))

            # Parse injury start date
            injury_start_date = None
            if player_data.get('injury_start_date'):
                try:
                    injury_start_date = datetime.strptime(
                        player_data['injury_start_date'], '%Y-%m-%d').date()
                except ValueError:
                    logger.warning("Invalid injury_start_date format for player %s: %s",
                                   player_data.get('full_name'), player_data.get('injury_start_date'))

            # Parse numeric fields with validation
            jersey_number = SleeperScraper._safe_int_parse(
                player_data.get('number'))
            years_exp = SleeperScraper._safe_int_parse(
                player_data.get('years_exp'))
            depth_chart_order = SleeperScraper._safe_int_parse(
                player_data.get('depth_chart_order'))
            search_rank = SleeperScraper._safe_int_parse(
                player_data.get('search_rank'))

            # Parse rookie year from metadata
            rookie_year = None
            metadata = player_data.get('metadata', {})
            if isinstance(metadata, dict) and metadata.get('rookie_year'):
                rookie_year = SleeperScraper._safe_int_parse(
                    metadata['rookie_year'])

            # Parse fantasy positions array
            fantasy_positions = player_data.get('fantasy_positions', [])
            fantasy_positions_json = json.dumps(
                fantasy_positions) if fantasy_positions else None

            # Validate string lengths to prevent database column overflow
            return {
                'sleeper_id': sleeper_id,
                'full_name': SleeperScraper._truncate_string(player_data.get('full_name', ''), 100),
                'first_name': SleeperScraper._truncate_string(player_data.get('first_name', ''), 50),
                'last_name': SleeperScraper._truncate_string(player_data.get('last_name', ''), 50),
                'position': player_data.get('position', '').upper(),
                'team': SleeperScraper._truncate_string(player_data.get('team', ''), 10),
                'birth_date': birth_date,
                'height': SleeperScraper._truncate_string(player_data.get('height', ''), 10),
                'weight': SleeperScraper._truncate_string(player_data.get('weight', ''), 10),
                'college': SleeperScraper._truncate_string(player_data.get('college', ''), 100),
                'years_exp': years_exp,
                'jersey_number': jersey_number,
                'depth_chart_order': depth_chart_order,
                'depth_chart_position': SleeperScraper._truncate_string(player_data.get('depth_chart_position', ''), 10),
                'fantasy_positions': fantasy_positions_json,
                'hashtag': SleeperScraper._truncate_string(player_data.get('hashtag', ''), 100),
                'search_rank': search_rank,
                'high_school': SleeperScraper._truncate_string(player_data.get('high_school', ''), 200),
                'rookie_year': rookie_year,
                'injury_status': SleeperScraper._truncate_string(player_data.get('injury_status', ''), 50),
                'injury_start_date': injury_start_date
            }

        except Exception as e:
            logger.error(
                "Error parsing individual Sleeper player %s: %s", sleeper_id, e)
            return None

    @staticmethod
    def _validate_player_data(player_data: Dict[str, Any]) -> bool:
        """
        Comprehensive validation of player data before processing.

        Implements security validation for data integrity.

        Args:
            player_data: Raw player data

        Returns:
            True if data is valid, False otherwise
        """
        try:
            # Check required fields
            required_fields = ['full_name', 'position']
            for field in required_fields:
                if not player_data.get(field):
                    return False

            # Validate data types
            if not isinstance(player_data.get('full_name'), str):
                return False

            # Validate position is a valid enum value
            position = player_data.get('position', '').upper()
            if position not in SleeperScraper.VALID_POSITIONS:
                return False

            return True

        except Exception as e:
            logger.warning("Data validation failed: %s", e)
            return False

    @staticmethod
    def _safe_int_parse(value: Any) -> Optional[int]:
        """Parse integer values safely with error handling."""
        if value is None:
            return None
        try:
            return int(value)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _truncate_string(value: str, max_length: int) -> str:
        """Truncate string to prevent database column overflow."""
        if not value:
            return ''
        return value[:max_length] if len(value) > max_length else value

    @staticmethod
    def scrape_sleeper_data() -> List[Dict[str, Any]]:
        """
        Main function to scrape and process Sleeper player data.

        Mirrors the structure of KTCScraper.scrape_ktc().

        Returns:
            List of processed Sleeper player dictionaries
        """
        try:
            logger.info("Starting Sleeper data scraping operation...")

            # Fetch raw data
            raw_players = SleeperScraper.fetch_sleeper_data()
            if not raw_players:
                logger.error("Failed to fetch Sleeper player data")
                return []

            # Parse and filter players
            parsed_players = SleeperScraper.parse_sleeper_players(raw_players)
            if not parsed_players:
                logger.error(
                    "No valid players found after parsing Sleeper data")
                return []

            logger.info("Successfully scraped %s Sleeper players",
                        len(parsed_players))
            return parsed_players

        except Exception as e:
            logger.error("Error in scrape_sleeper_data: %s", e)
            return []

    @staticmethod
    def fetch_league_info(league_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetch league information from Sleeper API.

        Args:
            league_id: The Sleeper league ID

        Returns:
            League data dictionary or None if failed
        """
        try:
            logger.info("Fetching league info for league_id: %s", league_id)
            url = f"https://api.sleeper.app/v1/league/{league_id}"
            response = requests.get(url, timeout=30)
            response.raise_for_status()

            league_data = response.json()
            logger.info(
                "Successfully fetched league info for league_id: %s", league_id)
            return league_data

        except requests.RequestException as e:
            logger.error(
                "Failed to fetch league info for %s: %s", league_id, e)
            return None
        except json.JSONDecodeError as e:
            logger.error(
                "Failed to parse league info response for %s: %s", league_id, e)
            return None

    @staticmethod
    def fetch_league_rosters(league_id: str) -> Optional[List[Dict[str, Any]]]:
        """
        Fetch league rosters from Sleeper API.

        Args:
            league_id: The Sleeper league ID

        Returns:
            List of roster dictionaries or None if failed
        """
        try:
            logger.info("Fetching rosters for league_id: %s", league_id)
            url = f"https://api.sleeper.app/v1/league/{league_id}/rosters"
            response = requests.get(url, timeout=30)
            response.raise_for_status()

            rosters_data = response.json()
            logger.info("Successfully fetched %s rosters for league_id: %s",
                        len(rosters_data) if rosters_data else 0, league_id)
            return rosters_data

        except requests.RequestException as e:
            logger.error("Failed to fetch rosters for %s: %s", league_id, e)
            return None
        except json.JSONDecodeError as e:
            logger.error(
                "Failed to parse rosters response for %s: %s", league_id, e)
            return None

    @staticmethod
    def fetch_league_users(league_id: str) -> Optional[List[Dict[str, Any]]]:
        """
        Fetch league users from Sleeper API.

        Args:
            league_id: The Sleeper league ID

        Returns:
            List of user dictionaries or None if failed
        """
        try:
            logger.info("Fetching users for league_id: %s", league_id)
            url = f"https://api.sleeper.app/v1/league/{league_id}/users"
            response = requests.get(url, timeout=30)
            response.raise_for_status()

            users_data = response.json()
            logger.info("Successfully fetched %s users for league_id: %s",
                        len(users_data) if users_data else 0, league_id)
            return users_data

        except requests.RequestException as e:
            logger.error("Failed to fetch users for %s: %s", league_id, e)
            return None
        except json.JSONDecodeError as e:
            logger.error(
                "Failed to parse users response for %s: %s", league_id, e)
            return None

    @staticmethod
    def fetch_players_research(season: str, week: int = 1, league_type: int = 2) -> Optional[Dict[str, Any]]:
        """
        Fetch player research data from Sleeper API.

        Args:
            season: The NFL season year (e.g., "2024")
            week: The week number (default: 1)
            league_type: League type (default: 2 for dynasty)

        Returns:
            Research data dictionary or None if failed
        """
        try:
            logger.info("Fetching research data for season: %s, week: %s, league_type: %s",
                        season, week, league_type)
            url = f"https://api.sleeper.app/players/nfl/research/regular/{season}/{week}?league_type={league_type}"
            response = requests.get(url, timeout=30)
            response.raise_for_status()

            research_data = response.json()
            logger.info(
                "Successfully fetched research data for season: %s", season)
            return research_data

        except requests.RequestException as e:
            logger.error(
                "Failed to fetch research data for season %s: %s", season, e)
            return None
        except json.JSONDecodeError as e:
            logger.error(
                "Failed to parse research response for season %s: %s", season, e)
            return None

    @staticmethod
    def scrape_league_data(league_id: str) -> Dict[str, Any]:
        """
        Comprehensive scraping of all league-related data.

        Args:
            league_id: The Sleeper league ID

        Returns:
            Dictionary containing league info, rosters, and users data
        """
        try:
            logger.info(
                "Starting comprehensive league data scraping for league_id: %s", league_id)

            # Fetch all league data concurrently would be better, but keeping simple for now
            league_info = SleeperScraper.fetch_league_info(league_id)
            if not league_info:
                return {
                    'success': False,
                    'error': 'Failed to fetch league info - invalid league ID or API error',
                    'league_id': league_id
                }

            rosters_data = SleeperScraper.fetch_league_rosters(league_id)
            users_data = SleeperScraper.fetch_league_users(league_id)

            return {
                'success': True,
                'league_id': league_id,
                'league_info': league_info,
                'rosters': rosters_data or [],
                'users': users_data or [],
                'timestamp': datetime.now(UTC).isoformat()
            }

        except Exception as e:
            logger.error(
                "Error in scrape_league_data for %s: %s", league_id, e)
            return {
                'success': False,
                'error': str(e),
                'league_id': league_id
            }

    @staticmethod
    def scrape_research_data(season: str, week: int = 1, league_type: int = 2) -> Dict[str, Any]:
        """
        Scrape player research data for a given season.

        Args:
            season: The NFL season year
            week: The week number
            league_type: League type (2 for dynasty)

        Returns:
            Dictionary containing research data and metadata
        """
        try:
            logger.info(
                "Starting research data scraping for season: %s", season)

            research_data = SleeperScraper.fetch_players_research(
                season, week, league_type)
            if not research_data:
                return {
                    'success': False,
                    'error': 'Failed to fetch research data - invalid season or API error',
                    'season': season
                }

            return {
                'success': True,
                'season': season,
                'week': week,
                'league_type': league_type,
                'research_data': research_data,
                'timestamp': datetime.now(UTC).isoformat()
            }

        except Exception as e:
            logger.error(
                "Error in scrape_research_data for season %s: %s", season, e)
            return {
                'success': False,
                'error': str(e),
                'season': season
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
            fantasy_dict = {player[PLAYER_NAME_KEY]                            : player for player in fantasy_players}

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
