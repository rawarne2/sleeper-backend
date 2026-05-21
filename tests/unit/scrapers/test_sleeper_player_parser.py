"""Coverage for the expanded ``SleeperScraper._parse_individual_player`` field set."""
from __future__ import annotations

from datetime import datetime, UTC

from scrapers.sleeper_scraper import SleeperScraper


def _api_player() -> dict:
    return {
        'full_name': 'Justin Jefferson',
        'first_name': 'Justin',
        'last_name': 'Jefferson',
        'position': 'WR',
        'team': 'MIN',
        'team_abbr': 'MIN',
        'active': True,
        'sport': 'nfl',
        'birth_date': '1999-06-16',
        'birth_city': 'St. Rose',
        'birth_state': 'LA',
        'birth_country': 'USA',
        'height': "6'1\"",
        'weight': '195',
        'college': 'LSU',
        'years_exp': 4,
        'number': 18,
        'depth_chart_order': 1,
        'depth_chart_position': 'WR',
        'fantasy_positions': ['WR'],
        'hashtag': '#JustinJefferson',
        'search_rank': 7,
        'search_full_name': 'justinjefferson',
        'search_first_name': 'justin',
        'search_last_name': 'jefferson',
        'high_school': 'Destrehan',
        'rookie_year': 2020,
        'injury_status': 'Questionable',
        'injury_body_part': 'Hamstring',
        'injury_start_date': '2025-09-15',
        'injury_notes': 'Tweaked late in practice; testing weekly.',
        'practice_participation': 'Limited',
        'practice_description': 'Did not finish drills',
        'status': 'Active',
        'player_metadata': {'rookie_year': 2020},
        'competitions': [],
        'team_changed_at': '2024-08-21T15:30:00Z',
        'news_updated': 1726000000000,
        'espn_id': 4262921,
        'yahoo_id': '32692',
        'fantasy_data_id': '21684',
        'stats_id': '4262921',
        'gsis_id': '00-0036900',
        'sportradar_id': 'sr:player:9999',
        'rotoworld_id': '15001',
        'rotowire_id': 14820,
        'swish_id': 50012,
        'oddsjam_id': '',
        'opta_id': None,
        'pandascore_id': '',
    }


def test_parse_individual_player_expands_all_persisted_columns():
    api = _api_player()
    parsed = SleeperScraper._parse_individual_player('6794', api)
    assert parsed is not None

    # Intentional omissions stay omitted (Player model does not store them).
    assert 'first_name' not in parsed
    assert 'last_name' not in parsed
    assert 'active' not in parsed
    assert 'sport' not in parsed

    # Core fields
    assert parsed['sleeper_player_id'] == '6794'
    assert parsed['full_name'] == 'Justin Jefferson'
    assert parsed['position'] == 'WR'
    assert parsed['team'] == 'MIN'
    assert parsed['team_abbr'] == 'MIN'

    # Injury / practice
    assert parsed['injury_status'] == 'Questionable'
    assert parsed['injury_body_part'] == 'Hamstring'
    assert parsed['injury_notes'] == api['injury_notes']
    assert parsed['practice_participation'] == 'Limited'
    assert parsed['practice_description'] == 'Did not finish drills'

    # Normalized search + birth location
    assert parsed['search_full_name'] == 'justinjefferson'
    assert parsed['search_first_name'] == 'justin'
    assert parsed['search_last_name'] == 'jefferson'
    assert parsed['birth_city'] == 'St. Rose'
    assert parsed['birth_state'] == 'LA'
    assert parsed['birth_country'] == 'USA'

    # External IDs (string coercion for ints, blank coercion for empties)
    assert parsed['espn_id'] == '4262921'
    assert parsed['yahoo_id'] == '32692'
    assert parsed['stats_id'] == '4262921'
    assert parsed['gsis_id'] == '00-0036900'
    assert parsed['sportradar_id'] == 'sr:player:9999'
    assert parsed['rotoworld_id'] == '15001'
    assert parsed['rotowire_id'] == 14820
    assert parsed['swish_id'] == 50012
    assert parsed['oddsjam_id'] == ''
    assert parsed['opta_id'] == ''
    assert parsed['pandascore_id'] == ''

    # JSON-serialized list / dict columns stay strings for Text columns
    assert isinstance(parsed['competitions'], str)
    assert parsed['competitions'] == '[]'
    assert isinstance(parsed['fantasy_positions'], str)
    assert isinstance(parsed['player_metadata'], str)

    # Datetime + epoch ms
    assert isinstance(parsed['team_changed_at'], datetime)
    assert parsed['news_updated'] == 1726000000000


def test_parse_team_changed_at_handles_epoch_millis_and_iso():
    iso = SleeperScraper._parse_team_changed_at('2024-08-21T15:30:00Z')
    assert isinstance(iso, datetime)
    assert iso.tzinfo is not None

    epoch = SleeperScraper._parse_team_changed_at(1726000000000)
    assert isinstance(epoch, datetime)
    assert epoch.tzinfo == UTC

    assert SleeperScraper._parse_team_changed_at(None) is None
    assert SleeperScraper._parse_team_changed_at('') is None
    assert SleeperScraper._parse_team_changed_at('not-a-date') is None
