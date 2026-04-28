import json
import os
from datetime import datetime, UTC
from typing import Any, Dict, List, Optional

from managers.file_manager import FileManager
from utils.constants import (
    PLAYER_NAME_KEY,
    POSITION_KEY,
    AGE_KEY,
)
from utils.helpers import ktc_write_unmatched_merge_report_enabled, setup_logging

logger = setup_logging()


class PlayerMerger:
    """
    Handles merging KTC and Sleeper player data.

    Matches players by name, using birth date and position to distinguish
    players with the same name.
    """

    @staticmethod
    def merge_player_data(ktc_players: List[Dict[str, Any]], sleeper_players: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Merge KTC and Sleeper player data using improved matching logic.

        Uses search_full_name for better player matching to avoid duplicates like
        "Ja'Marr Chase" vs "Ja\u0027Marr" creating separate entries.

        Filters players to only include those in valid fantasy positions.
        Prefers KTC's age value over Sleeper's since KTC includes decimals.

        Args:
            ktc_players: List of KTC player data
            sleeper_players: List of Sleeper player data

        Returns:
            List of merged player data (filtered for valid positions)
        """
        try:
            from scrapers.sleeper_scraper import SleeperScraper
            from data_types.normalization import normalize_name_for_matching
            from utils.helpers import create_player_match_key

            valid_ktc_players = []
            for ktc_player in ktc_players:
                position = ktc_player.get(POSITION_KEY, '').upper()
                if position in SleeperScraper.VALID_POSITIONS:
                    valid_ktc_players.append(ktc_player)
                else:
                    logger.debug("Filtering out KTC player %s with invalid position: %s",
                                 ktc_player.get(PLAYER_NAME_KEY, 'Unknown'), position)

            logger.info("Filtered KTC players: %s valid out of %s total",
                        len(valid_ktc_players), len(ktc_players))

            log_unmatched = (
                os.getenv('LOG_UNMATCHED_KTC_MERGE', '').lower() == 'true'
                or os.getenv('IS_DEV', '').lower() == 'true'
            )

            sleeper_lookup = {}
            sleeper_name_fallback = {}
            sleeper_name_only_fallback: Dict[str, List[Dict[str, Any]]] = {
            } if log_unmatched else {}

            for sleeper_player in sleeper_players:
                position = sleeper_player.get('position', '').upper()

                if position not in SleeperScraper.VALID_POSITIONS:
                    continue

                search_full_name = sleeper_player.get('search_full_name', '')

                if search_full_name:
                    match_key = create_player_match_key(
                        search_full_name, position)
                    sleeper_lookup[match_key] = sleeper_player

                full_name = sleeper_player.get('full_name', '')
                if full_name:
                    if log_unmatched:
                        normalized_full_name = normalize_name_for_matching(
                            full_name)
                        if normalized_full_name:
                            if normalized_full_name not in sleeper_name_only_fallback:
                                sleeper_name_only_fallback[normalized_full_name] = [
                                ]
                            sleeper_name_only_fallback[normalized_full_name].append(
                                sleeper_player)
                    fallback_key = create_player_match_key(full_name, position)
                    if fallback_key not in sleeper_name_fallback:
                        sleeper_name_fallback[fallback_key] = []
                    sleeper_name_fallback[fallback_key].append(sleeper_player)

            logger.info("Created Sleeper lookup with %s search_full_name keys and %s fallback keys",
                        len(sleeper_lookup), len(sleeper_name_fallback))

            merged_players = []
            matched_count = 0
            duplicate_prevention = set()

            seen_ktc_by_duplicate_key: Dict[str, Dict[str, Any]] = {}
            unmatched_ktc_players: List[Dict[str, Any]] = []
            duplicate_key_collisions: List[Dict[str, Any]] = []

            for ktc_player in valid_ktc_players:
                player_name = ktc_player.get(PLAYER_NAME_KEY, '')
                position = ktc_player.get(POSITION_KEY, '').upper()

                duplicate_key = create_player_match_key(player_name, position)
                if duplicate_key in duplicate_prevention:
                    if log_unmatched:
                        previous = seen_ktc_by_duplicate_key.get(
                            duplicate_key, {})
                        duplicate_key_collisions.append({
                            'duplicate_key': duplicate_key,
                            'position': position,
                            'previous_ktc_player_name': previous.get(PLAYER_NAME_KEY),
                            'previous_ktc_player_id': previous.get('ktc_player_id'),
                            'skipped_ktc_player_name': player_name,
                            'skipped_ktc_player_id': ktc_player.get('ktc_player_id'),
                        })
                    continue
                duplicate_prevention.add(duplicate_key)
                if log_unmatched:
                    seen_ktc_by_duplicate_key[duplicate_key] = ktc_player

                sleeper_match = None
                search_key = create_player_match_key(player_name, position)

                if search_key in sleeper_lookup:
                    sleeper_match = sleeper_lookup[search_key]
                elif search_key in sleeper_name_fallback:
                    candidates = sleeper_name_fallback[search_key]
                    if len(candidates) == 1:
                        sleeper_match = candidates[0]
                    else:
                        logger.warning("Multiple Sleeper matches for %s (%s): %s candidates",
                                       player_name, position, len(candidates))
                        sleeper_match = candidates[0]  # Take first match

                if not sleeper_match:
                    if log_unmatched:
                        ktc_normalized_name = normalize_name_for_matching(
                            player_name)
                        unmatched_ktc_players.append({
                            'ktc_player_name': player_name,
                            'ktc_player_id': ktc_player.get('ktc_player_id'),
                            'position': position,
                            'ktc_match_key': search_key,
                            'ktc_normalized_name': ktc_normalized_name,
                            'potential_sleeper_matches_any_position': [
                                {
                                    'sleeper_player_id': p.get('player_id'),
                                    'full_name': p.get('full_name'),
                                    'position': p.get('position'),
                                }
                                for p in (sleeper_name_only_fallback.get(ktc_normalized_name, []) or [])[:5]
                            ],
                        })

                merged_player = ktc_player.copy()

                if sleeper_match:
                    merged_player['sleeper_player_id'] = sleeper_match.get(
                        'player_id')

                    sleeper_keys = [
                        'birth_date', 'height', 'weight', 'college',
                        'years_exp', 'number', 'depth_chart_order',
                        'depth_chart_position', 'fantasy_positions', 'hashtag',
                        'search_rank', 'high_school', 'injury_status', 'injury_start_date',
                        'full_name', 'status', 'team_abbr', 'competitions', 'injury_body_part',
                        'injury_notes', 'team_changed_at', 'practice_participation',
                        'search_first_name', 'birth_state', 'oddsjam_id',
                        'practice_description', 'opta_id', 'search_full_name',
                        'espn_id', 'search_last_name', 'sportradar_id', 'swish_id',
                        'birth_country', 'gsis_id', 'pandascore_id', 'yahoo_id',
                        'fantasy_data_id', 'stats_id', 'news_updated', 'birth_city',
                        'rotoworld_id', 'rotowire_id'
                    ]

                    for key in sleeper_keys:
                        if key in sleeper_match:
                            if key == 'age' and merged_player.get(AGE_KEY) is not None:
                                continue

                            if key == 'fantasy_positions':
                                fantasy_positions = sleeper_match[key]
                                if isinstance(fantasy_positions, list):
                                    merged_player[key] = json.dumps(
                                        fantasy_positions)
                                else:
                                    merged_player[key] = fantasy_positions
                            else:
                                merged_player[key] = sleeper_match[key]

                    metadata = sleeper_match.get('metadata', {})
                    if isinstance(metadata, dict) and metadata.get('rookie_year'):
                        merged_player['rookie_year'] = metadata['rookie_year']

                    if metadata:
                        merged_player['player_metadata'] = json.dumps(metadata)

                    matched_count += 1

                merged_players.append(merged_player)

            logger.info("Successfully merged %s KTC players with %s Sleeper matches (filtered for valid positions)",
                        len(valid_ktc_players), matched_count)

            if log_unmatched and (unmatched_ktc_players or duplicate_key_collisions):
                logger.warning(
                    "KTC->Sleeper merge report: %s unmatched (no Sleeper match) out of %s, %s duplicate match_key collisions",
                    len(unmatched_ktc_players), len(
                        valid_ktc_players), len(duplicate_key_collisions)
                )

                for entry in unmatched_ktc_players[:20]:
                    logger.warning("UNMATCHED_KTC_PLAYER %s",
                                   json.dumps(entry, default=str))
                if len(unmatched_ktc_players) > 20:
                    logger.warning("UNMATCHED_KTC_PLAYER ... plus %s more",
                                   len(unmatched_ktc_players) - 20)

                for entry in duplicate_key_collisions[:20]:
                    logger.warning(
                        "KTC_DUPLICATE_MATCH_KEY_COLLISION %s", json.dumps(entry, default=str))
                if len(duplicate_key_collisions) > 20:
                    logger.warning("KTC_DUPLICATE_MATCH_KEY_COLLISION ... plus %s more",
                                   len(duplicate_key_collisions) - 20)

                if ktc_write_unmatched_merge_report_enabled():
                    try:
                        report = {
                            'generated_at': datetime.now(UTC).isoformat(),
                            'ktc_players_total': len(valid_ktc_players),
                            'sleeper_players_total': len(sleeper_players),
                            'unmatched_ktc_players': unmatched_ktc_players,
                            'duplicate_key_collisions': duplicate_key_collisions,
                        }
                        filename = f"ktc_unmatched_merge_report_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.json"
                        FileManager.save_json_to_file(report, filename)
                    except Exception as report_error:
                        logger.warning(
                            "Failed to write unmatched merge report: %s", report_error)

            return merged_players

        except Exception as e:
            logger.error("Error merging player data: %s", e)
            return ktc_players  # Return original KTC data if merge fails
