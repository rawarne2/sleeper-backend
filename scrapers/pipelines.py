from typing import Any, Dict, List, Optional

from utils.helpers import save_and_verify_database, setup_logging

logger = setup_logging()


def load_sleeper_players_for_merge_from_db() -> List[Dict[str, Any]]:
    """
    Rows for KTC merge: has sleeper id, non-empty match_key, not Sleeper search_rank placeholder.
    Avoids loading thousands of draft/meta rows into memory.
    """
    from models.entities import Player
    from utils.player_eligibility import sqlalchemy_player_eligible_for_merge_filter

    sleeper_players_db = (
        Player.query.filter(sqlalchemy_player_eligible_for_merge_filter()).all()
    )
    sleeper_players: List[Dict[str, Any]] = []
    for player in sleeper_players_db:
        sleeper_data = player.to_dict()
        sleeper_data["player_id"] = sleeper_data["sleeper_player_id"]
        sleeper_players.append(sleeper_data)
    logger.info(
        "Loaded %s merge-eligible Sleeper-backed players from database",
        len(sleeper_players),
    )
    return sleeper_players


def scrape_and_process_data(
    ktc_scraper,
    league_format: str,
    is_redraft: bool,
    tep_level: Optional[str],
    sleeper_players: Optional[List[Dict[str, Any]]] = None
) -> tuple[List[Dict[str, Any]], Optional[str]]:
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

        from managers.player_merger import PlayerMerger

        if sleeper_players is None:
            logger.info("Fetching merge-eligible Sleeper player rows from database...")
            try:
                sleeper_players = load_sleeper_players_for_merge_from_db()
            except Exception as db_error:
                logger.warning(
                    "Failed to get Sleeper data from database: %s. Will use KTC data only.",
                    db_error,
                )
                sleeper_players = []
        else:
            logger.info("Using provided Sleeper players for merge (%s records)",
                        len(sleeper_players))

        if sleeper_players:
            logger.info("Merging KTC and existing Sleeper player data...")
            merged_players = PlayerMerger.merge_player_data(
                ktc_players, sleeper_players)
            logger.info("Successfully merged player data: %s KTC players with %s existing Sleeper players",
                        len(ktc_players), len(sleeper_players))
        else:
            logger.warning(
                "No Sleeper data available from database, using KTC data only")
            merged_players = ktc_players

        def get_sort_key(player):
            if league_format == '1qb':
                oneqb_values = player.get('oneqb_values', {})
                return oneqb_values.get('rank') if oneqb_values else float('inf')
            else:  # superflex
                superflex_values = player.get('superflex_values', {})
                return superflex_values.get('rank') if superflex_values else float('inf')

        players_sorted = sorted(merged_players, key=get_sort_key)
        logger.info("Sorted %s players by %s rankings",
                    len(players_sorted), league_format)
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
        try:
            sleeper_players = load_sleeper_players_for_merge_from_db()
        except Exception as db_error:
            logger.warning(
                "Failed to get Sleeper data from database for bulk refresh: %s. Will use KTC data only.",
                db_error,
            )
            sleeper_players = []

        logger.info("Scraping comprehensive dynasty data from KTC...")
        dynasty_players, dynasty_error = scrape_and_process_data(
            ktc_scraper, '1qb', False, None, sleeper_players)

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

        logger.info("Scraping comprehensive redraft data from KTC...")
        redraft_players, redraft_error = scrape_and_process_data(
            ktc_scraper, '1qb', True, None, sleeper_players)

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
