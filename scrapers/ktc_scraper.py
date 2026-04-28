import json
import os
import re
import time
from datetime import datetime, UTC
from typing import Any, Dict, List, Optional

import requests

from utils.constants import (
    PLAYER_NAME_KEY,
    POSITION_KEY,
    TEAM_KEY,
    AGE_KEY,
    ROOKIE_KEY,
    DYNASTY_URL,
    FANTASY_URL,
)
from utils.helpers import setup_logging

logger = setup_logging()


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
            timeout_s = float(os.getenv('KTC_FETCH_TIMEOUT_SECONDS', '120'))
            retries = int(os.getenv('KTC_FETCH_RETRIES', '2'))
        except (ValueError, TypeError) as e:
            logger.error("Invalid KTC env config: %s — using defaults", e)
            timeout_s = 120.0
            retries = 2

        last_error: Optional[Exception] = None
        for attempt in range(retries + 1):
            try:
                response = requests.get(url, timeout=timeout_s)
                response.raise_for_status()
                return response
            except requests.RequestException as e:
                last_error = e
                if attempt >= retries:
                    break
                backoff_s = min(30, 2 ** attempt)
                logger.warning(
                    "KTC fetch failed (attempt %s/%s) for %s: %s. Retrying in %ss...",
                    attempt + 1, retries + 1, url, e, backoff_s
                )
                time.sleep(backoff_s)

        if last_error:
            logger.error("Failed to fetch page %s: %s", url, last_error)
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
        # Handle fantasy_positions field - convert list to JSON string if present
        fantasy_positions = player_obj.get('fantasy_positions', [])
        fantasy_positions_json = json.dumps(
            fantasy_positions) if fantasy_positions else None

        return {
            'name': player_obj.get('playerName', ''),
            'position': player_obj.get('position', ''),
            'team': player_obj.get('team', ''),
            'age': player_obj.get('age'),
            'rookie': "Yes" if player_obj.get('rookie', False) else "No",
            'ktc_player_id': player_obj.get('playerID'),
            'slug': player_obj.get('slug'),
            'positionID': player_obj.get('positionID'),
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
            'draftYear': player_obj.get('draftYear'),
            'byeWeek': player_obj.get('byeWeek'),
            'injury': json.dumps(player_obj.get('injury', {})) if player_obj.get('injury') else None,
            'fantasy_positions': fantasy_positions_json,
        }

    @staticmethod
    def _build_comprehensive_player_result(player_info: Dict[str, Any], player_obj: Dict[str, Any]) -> Dict[str, Any]:
        """Build comprehensive player result with all KTC data."""
        # Extract oneQBValues and superflexValues
        oneqb_values = player_obj.get('oneQBValues', {})
        superflex_values = player_obj.get('superflexValues', {})

        result = {
            PLAYER_NAME_KEY: player_info['name'],
            POSITION_KEY: player_info['position'],
            TEAM_KEY: player_info['team'],
            AGE_KEY: player_info['age'],
            ROOKIE_KEY: player_info['rookie'],
            'ktc_player_id': player_info['ktc_player_id'],
            'slug': player_info['slug'],
            'positionID': player_info['positionID'],
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
            'draftYear': player_info['draftYear'],
            'byeWeek': player_info['byeWeek'],
            'injury': player_info['injury'],
            'fantasy_positions': player_info['fantasy_positions'],
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


