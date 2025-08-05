import json
import re
from datetime import datetime, UTC
from typing import Dict, List, Optional, Any

import requests

from utils import (PLAYER_NAME_KEY, POSITION_KEY, TEAM_KEY, AGE_KEY, ROOKIE_KEY,
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

                position = (player_data.get('position') or '').upper()
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
            number = SleeperScraper._safe_int_parse(
                player_data.get('number'))
            years_exp = SleeperScraper._safe_int_parse(
                player_data.get('years_exp'))
            depth_chart_order = SleeperScraper._safe_int_parse(
                player_data.get('depth_chart_order'))
            search_rank = SleeperScraper._safe_int_parse(
                player_data.get('search_rank'))

            # Parse rookie year from player_metadata
            rookie_year = None
            player_metadata = player_data.get('player_metadata', {})
            if isinstance(player_metadata, dict) and player_metadata.get('rookie_year'):
                rookie_year = SleeperScraper._safe_int_parse(
                    player_metadata['rookie_year'])

            # Parse fantasy positions array
            fantasy_positions = player_data.get('fantasy_positions', [])
            fantasy_positions_json = json.dumps(
                fantasy_positions) if fantasy_positions else None

            # Store complete player_metadata as JSON
            player_metadata_json = json.dumps(
                player_metadata) if player_metadata else None

            # Validate string lengths to prevent database column overflow
            return {
                'sleeper_player_id': sleeper_id,
                'full_name': SleeperScraper._truncate_string(player_data.get('full_name', ''), 100),
                # 'first_name': SleeperScraper._truncate_string(player_data.get('first_name', ''), 50),
                # 'last_name': SleeperScraper._truncate_string(player_data.get('last_name', ''), 50),
                'position': (player_data.get('position') or '').upper(),
                'team': SleeperScraper._truncate_string(player_data.get('team', ''), 10),
                'birth_date': birth_date,
                'height': SleeperScraper._truncate_string(player_data.get('height', ''), 10),
                'weight': SleeperScraper._truncate_string(player_data.get('weight', ''), 10),
                'college': SleeperScraper._truncate_string(player_data.get('college', ''), 100),
                'years_exp': years_exp,
                'number': number,
                'depth_chart_order': depth_chart_order,
                'depth_chart_position': SleeperScraper._truncate_string(player_data.get('depth_chart_position', ''), 10),
                'fantasy_positions': fantasy_positions_json,
                'hashtag': SleeperScraper._truncate_string(player_data.get('hashtag', ''), 100),
                'search_rank': search_rank,
                'high_school': SleeperScraper._truncate_string(player_data.get('high_school', ''), 200),
                'rookie_year': rookie_year,
                'injury_status': SleeperScraper._truncate_string(player_data.get('injury_status', ''), 50),
                'injury_start_date': injury_start_date,
                # 'active': player_data.get('active', False),
                # 'sport': SleeperScraper._truncate_string(player_data.get('sport', ''), 10),
                'player_metadata': player_metadata_json
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
            position = (player_data.get('position') or '').upper()
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
            response = requests.get(url, timeout=60)
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
            response = requests.get(url, timeout=60)
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
            response = requests.get(url, timeout=60)
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
            response = requests.get(url, timeout=60)
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
            response = requests.get(url, timeout=60)
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
    def parse_player_data(player_obj: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Parse a player object from the playersArray, extracting comprehensive KTC data.
        TODO:
        Extracts ALL available data including both oneQB and superflex values plus 
        all TEP levels (base, TEP, TEPP, TEPPP) regardless of specific filtering needs.
        The database and API layers handle any filtering requirements.

        Args:
            player_obj: Raw player data from KTC

        Returns:
            Parsed player dictionary with comprehensive KTC data or None if parsing fails
        """
        try:
            # Extract basic player information
            player_info = KTCScraper._extract_basic_player_info(player_obj)

            # Build comprehensive result
            return KTCScraper._build_comprehensive_player_result(player_info, player_obj)

        except Exception as e:
            logger.error(
                "Error parsing player %s: %s", player_obj.get('playerName', 'Unknown'), e)
            return None

    @staticmethod
    def _extract_basic_player_info(player_obj: Dict[str, Any]) -> Dict[str, Any]:
        """Extract basic player information from KTC data."""
        return {
            'name': player_obj.get('playerName', ''),
            'position': player_obj.get('position', ''),
            'team': player_obj.get('team', ''),
            'age': player_obj.get('age'),
            'rookie': "Yes" if player_obj.get('rookie', False) else "No",
            # Additional KTC fields
            'ktc_player_id': player_obj.get('playerID'),
            'slug': player_obj.get('slug'),
            'positionID': player_obj.get('positionID'),
            'heightFeet': player_obj.get('heightFeet'),
            'heightInches': player_obj.get('heightInches'),
            'weight': player_obj.get('weight'),
            'seasonsExperience': player_obj.get('seasonsExperience'),
            'pickRound': player_obj.get('pickRound'),
            'pickNum': player_obj.get('pickNum'),
            'isFeatured': player_obj.get('isFeatured'),
            'isStartSitFeatured': player_obj.get('isStartSitFeatured'),
            'isTrending': player_obj.get('isTrending'),
            'isDevyReturningToSchool': player_obj.get('isDevyReturningToSchool'),
            'isDevyYearDecrement': player_obj.get('isDevyYearDecrement'),
            'ktc_number': player_obj.get('number'),
            'teamLongName': player_obj.get('teamLongName'),
            'birthday': player_obj.get('birthday'),
            'draftYear': player_obj.get('draftYear'),
            'byeWeek': player_obj.get('byeWeek'),
            'injury': json.dumps(player_obj.get('injury', {})) if player_obj.get('injury') else None
        }

    @staticmethod
    def _build_comprehensive_player_result(player_info: Dict[str, Any], player_obj: Dict[str, Any]) -> Dict[str, Any]:
        """Build comprehensive player result with all KTC data."""
        # Extract oneQBValues and superflexValues
        oneqb_values = player_obj.get('oneQBValues', {})
        superflex_values = player_obj.get('superflexValues', {})

        # Base player data
        result = {
            PLAYER_NAME_KEY: player_info['name'],
            POSITION_KEY: player_info['position'],
            TEAM_KEY: player_info['team'],
            AGE_KEY: player_info['age'],
            ROOKIE_KEY: player_info['rookie'],
            # All additional KTC fields
            'ktc_player_id': player_info['ktc_player_id'],
            'slug': player_info['slug'],
            'positionID': player_info['positionID'],
            'heightFeet': player_info['heightFeet'],
            'heightInches': player_info['heightInches'],
            'seasonsExperience': player_info['seasonsExperience'],
            'pickRound': player_info['pickRound'],
            'pickNum': player_info['pickNum'],
            'isFeatured': player_info['isFeatured'],
            'isStartSitFeatured': player_info['isStartSitFeatured'],
            'isTrending': player_info['isTrending'],
            'isDevyReturningToSchool': player_info['isDevyReturningToSchool'],
            'isDevyYearDecrement': player_info['isDevyYearDecrement'],
            'ktc_number': player_info['ktc_number'],
            'teamLongName': player_info['teamLongName'],
            'birthday': player_info['birthday'],
            'draftYear': player_info['draftYear'],
            'byeWeek': player_info['byeWeek'],
            'injury': player_info['injury']
        }

        # Extract oneQB and superflex values as separate objects
        result['oneqb_values'] = KTCScraper._extract_format_values(
            oneqb_values)
        result['superflex_values'] = KTCScraper._extract_format_values(
            superflex_values)

        return result

    @staticmethod
    def _extract_format_values(values: Dict[str, Any]) -> Dict[str, Any]:
        """Extract specific fields from oneQBValues or superflexValues subtree."""
        result = {}

        # Base values
        result['value'] = values.get('value')
        result['rank'] = values.get('rank')
        result['positional_rank'] = values.get('positionalRank')
        result['overall_tier'] = values.get('overallTier')
        result['positional_tier'] = values.get('positionalTier')
        result['overall_trend'] = values.get('overallTrend')
        result['positional_trend'] = values.get('positionalTrend')
        result['overall_7day_trend'] = values.get('overall7DayTrend')
        result['positional_7day_trend'] = values.get('positional7DayTrend')
        result['start_sit_value'] = values.get('startSitValue')
        result['kept'] = values.get('kept')
        result['traded'] = values.get('traded')
        result['cut'] = values.get('cut')
        result['diff'] = values.get('diff')
        result['is_out_this_week'] = values.get('isOutThisWeek')
        result['raw_liquidity'] = values.get('rawLiquidity')
        result['std_liquidity'] = values.get('stdLiquidity')
        result['trade_count'] = values.get('tradeCount')

        # TEP values
        tep_values = values.get('tep', {})
        result['tep_value'] = tep_values.get('value')
        result['tep_rank'] = tep_values.get('rank')
        result['tep_positional_rank'] = tep_values.get('positionalRank')
        result['tep_overall_tier'] = tep_values.get('overallTier')
        result['tep_positional_tier'] = tep_values.get('positionalTier')

        # TEPP values
        tepp_values = values.get('tepp', {})
        result['tepp_value'] = tepp_values.get('value')
        result['tepp_rank'] = tepp_values.get('rank')
        result['tepp_positional_rank'] = tepp_values.get('positionalRank')
        result['tepp_overall_tier'] = tepp_values.get('overallTier')
        result['tepp_positional_tier'] = tepp_values.get('positionalTier')

        # TEPPP values
        teppp_values = values.get('teppp', {})
        result['teppp_value'] = teppp_values.get('value')
        result['teppp_rank'] = teppp_values.get('rank')
        result['teppp_positional_rank'] = teppp_values.get('positionalRank')
        result['teppp_overall_tier'] = teppp_values.get('overallTier')
        result['teppp_positional_tier'] = teppp_values.get('positionalTier')

        return result

    @staticmethod
    def scrape_players_from_array(url: str) -> List[Dict[str, Any]]:
        """
        Scrape players using the playersArray from JavaScript source.

        Extracts comprehensive player data including all league formats and TEP levels.

        Args:
            url: KTC URL to scrape (dynasty or redraft rankings page)

        Returns:
            List of parsed player dictionaries with comprehensive KTC data
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
                parsed_player = KTCScraper.parse_player_data(player_obj)
                if parsed_player:
                    players.append(parsed_player)

            logger.info("Successfully parsed %s players", len(players))
            return players

        except Exception as e:
            logger.error("Error in scrape_players_from_array: %s", e)
            return []


    @staticmethod
    def scrape_ktc(is_redraft: bool) -> List[Dict[str, Any]]:
        """
        Main scraping function using the playersArray approach.
        The core parsing extracts comprehensive data for all formats and TEP levels.

        Args:
            is_redraft: If True, scrapes both dynasty and fantasy data

        Returns:
            List of scraped and processed player data with comprehensive KTC values
        """
        try:
            if is_redraft:
                logger.info("Scraping redraft data...")
                players = KTCScraper.scrape_players_from_array(FANTASY_URL)
            else:
                logger.info("Scraping dynasty data...")
                players = KTCScraper.scrape_players_from_array(DYNASTY_URL)

            logger.info("Total players after scraping: %s", len(players))
            return players

        except Exception as e:
            logger.error("Error in scrape_ktc: %s", e)
            return []


def scrape_and_process_data(ktc_scraper, league_format: str, is_redraft: bool, tep_level: Optional[str]) -> tuple[List[Dict[str, Any]], Optional[str]]:
    """
    Scrape data from KTC and merge with existing Sleeper data from database.

    When refreshing KTC data, we should use existing Sleeper data from the database
    rather than scraping Sleeper again, as requested in the task requirements.

    Args:
        ktc_scraper: KTCScraper class
        league_format: League format
        is_redraft: Whether this is redraft data
        tep_level: TEP level

    Returns:
        Tuple of (sorted_players, error_message)
    """
    try:
        logger.info(
            "Starting KTC scrape for %s, redraft=%s, tep_level=%s", league_format, is_redraft, tep_level)
        ktc_players = ktc_scraper.scrape_ktc(is_redraft)
        logger.info("Scraped %s KTC players", len(ktc_players))

        if not ktc_players:
            return [], 'KTC scraping returned empty results - check network connectivity or site availability'

        # Import here to avoid circular imports
        from managers import PlayerMerger, DatabaseManager

        # Get existing Sleeper data from database instead of scraping fresh data
        logger.info("Fetching existing Sleeper player data from database...")
        try:
            # Get all Sleeper players from database (regardless of league format/redraft status)
            from models import Player
            sleeper_players_db = Player.query.filter(
                Player.sleeper_player_id.isnot(None)
            ).all()
            
            # Convert to the format expected by PlayerMerger using to_dict() method
            sleeper_players = []
            for player in sleeper_players_db:
                # Use to_dict() method for consistent structure
                sleeper_data = player.to_dict()
                # PlayerMerger expects 'player_id' key instead of 'sleeper_player_id'
                sleeper_data['player_id'] = sleeper_data['sleeper_player_id']
                sleeper_players.append(sleeper_data)
            
            logger.info("Retrieved %s Sleeper players from database", len(sleeper_players))
            
        except Exception as db_error:
            logger.warning("Failed to get Sleeper data from database: %s. Will use KTC data only.", db_error)
            sleeper_players = []

        # Merge KTC and Sleeper data
        if sleeper_players:
            logger.info("Merging KTC and existing Sleeper player data...")
            merged_players = PlayerMerger.merge_player_data(
                ktc_players, sleeper_players)
            logger.info("Successfully merged player data: %s KTC players with %s existing Sleeper players", 
                       len(ktc_players), len(sleeper_players))
        else:
            logger.warning("No Sleeper data available from database, using KTC data only")
            merged_players = ktc_players

        # Sort players by appropriate rank based on league format
        # Use the correct rank key for sorting
        def get_sort_key(player):
            if league_format == '1qb':
                oneqb_values = player.get('oneqb_values', {})
                return oneqb_values.get('rank') if oneqb_values else float('inf')
            else:  # superflex
                superflex_values = player.get('superflex_values', {})
                return superflex_values.get('rank') if superflex_values else float('inf')
        
        players_sorted = sorted(merged_players, key=get_sort_key)
        logger.info("Sorted %s players by %s rankings", len(players_sorted), league_format)
        return players_sorted, None

    except Exception as e:
        logger.error("Error during scraping and processing: %s", e)
        return [], str(e)


def scrape_and_save_all_ktc_data(ktc_scraper, database_manager) -> Dict[str, Any]:
    """
    Scrape and save comprehensive KTC data (dynasty + redraft) for all formats and TEP levels.

    Since the core KTC parsing already extracts all league formats (1QB + Superflex) and 
    all TEP levels (base, TEP, TEPP, TEPPP) from each player, we don't need to make 
    separate calls with different parameters.

    Args:
        ktc_scraper: KTCScraper class
        database_manager: DatabaseManager class

    Returns:
        Dictionary with results for both dynasty and redraft operations
    """
    results = {
        'dynasty': {'status': 'pending', 'players_count': 0, 'db_count': 0, 'error': None},
        'redraft': {'status': 'pending', 'players_count': 0, 'db_count': 0, 'error': None},
        'overall_status': 'success'
    }

    try:
        # Import here to avoid circular imports
        from utils import save_and_verify_database
        
        # Scrape and save dynasty data (contains all formats and TEP levels)
        logger.info("Scraping comprehensive dynasty data from KTC...")
        dynasty_players, dynasty_error = scrape_and_process_data(
            ktc_scraper, '1qb', False, None)  # Parameters are ignored by core parsing

        if dynasty_error:
            results['dynasty']['status'] = 'error'
            results['dynasty']['error'] = dynasty_error
        else:
            dynasty_count, dynasty_db_error = save_and_verify_database(
                database_manager, dynasty_players, '1qb', False)

            if dynasty_db_error:
                results['dynasty']['status'] = 'error'
                results['dynasty']['error'] = dynasty_db_error
            else:
                results['dynasty']['status'] = 'success'
                results['dynasty']['players_count'] = len(dynasty_players)
                results['dynasty']['db_count'] = dynasty_count

        # Scrape and save redraft data (contains all formats and TEP levels)
        logger.info("Scraping comprehensive redraft data from KTC...")
        redraft_players, redraft_error = scrape_and_process_data(
            ktc_scraper, '1qb', True, None)  # Parameters are ignored by core parsing

        if redraft_error:
            results['redraft']['status'] = 'error'
            results['redraft']['error'] = redraft_error
        else:
            redraft_count, redraft_db_error = save_and_verify_database(
                database_manager, redraft_players, '1qb', True)

            if redraft_db_error:
                results['redraft']['status'] = 'error'
                results['redraft']['error'] = redraft_db_error
            else:
                results['redraft']['status'] = 'success'
                results['redraft']['players_count'] = len(redraft_players)
                results['redraft']['db_count'] = redraft_count

        # Set overall status
        if results['dynasty']['status'] == 'error' and results['redraft']['status'] == 'error':
            results['overall_status'] = 'error'
        elif results['dynasty']['status'] == 'error' or results['redraft']['status'] == 'error':
            results['overall_status'] = 'partial_success'

        return results

    except Exception as e:
        logger.error("Error in scrape_and_save_all_ktc_data: %s", e)
        results['overall_status'] = 'error'
        results['error'] = str(e)
        return results
