from copy import copy as shallow_copy
from datetime import datetime, UTC
from flask import jsonify
from functools import wraps
from utils import setup_logging

logger = setup_logging()


def with_error_handling(f):
    """Decorator for consistent error handling."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except Exception as e:
            logger.error("Unexpected error in %s: %s", f.__name__, e)
            return jsonify({
                'status': 'error',
                'error': 'Internal server error',
                'details': str(e),
                'timestamp': datetime.now(UTC).isoformat()
            }), 500
    return decorated_function


def _copy_ktc_values_block(values_dict):
    """
    Shallow copy of oneQB/superflex values dict so we can set value/rank/etc.
    from tep/tepp/teppp without mutating shared references from ORM/to_dict.
    """
    if not values_dict or not isinstance(values_dict, dict):
        return values_dict
    block = shallow_copy(values_dict)
    # Nested tep/tepp/teppp are read-only for our mutations; top-level keys
    # we overwrite are value, rank, positionalRank, overallTier, positionalTier
    return block


def filter_players_by_format(players, league_format, tep_level):
    """Helper function to filter players based on league format and TEP level."""
    filtered_players = []
    for player in players:
        # Support both SQLAlchemy model instances and plain dicts.
        # Avoid deepcopy: to_dict() already builds fresh dicts; we only need
        # shallow copies of the ktc value blocks we mutate.
        if hasattr(player, 'to_dict'):
            player_dict = player.to_dict()
        else:
            player_dict = dict(player)

            if 'ktc' not in player_dict:
                player_dict['ktc'] = {
                    'age': player_dict.get('age'),
                    'rookie': player_dict.get('rookie'),
                    'oneQBValues': player_dict.get('oneqb_values'),
                    'superflexValues': player_dict.get('superflex_values')
                }

        if league_format == 'superflex':
            # Only include players with superflex values
            if player_dict.get('ktc', {}).get('superflexValues'):
                # Remove oneQB values from response
                if 'ktc' in player_dict and player_dict['ktc']:
                    player_dict['ktc']['oneQBValues'] = None

                # Apply TEP level filtering to superflex values
                superflex_values = player_dict['ktc']['superflexValues']
                if tep_level and superflex_values:
                    superflex_values = _copy_ktc_values_block(superflex_values)
                    player_dict['ktc']['superflexValues'] = superflex_values
                    if tep_level == 'tep' and superflex_values.get('tep', {}).get('value'):
                        superflex_values['value'] = superflex_values['tep']['value']
                        superflex_values['rank'] = superflex_values['tep']['rank']
                        superflex_values['positionalRank'] = superflex_values['tep']['positionalRank']
                        superflex_values['overallTier'] = superflex_values['tep']['overallTier']
                        superflex_values['positionalTier'] = superflex_values['tep']['positionalTier']
                    elif tep_level == 'tepp' and superflex_values.get('tepp', {}).get('value'):
                        superflex_values['value'] = superflex_values['tepp']['value']
                        superflex_values['rank'] = superflex_values['tepp']['rank']
                        superflex_values['positionalRank'] = superflex_values['tepp']['positionalRank']
                        superflex_values['overallTier'] = superflex_values['tepp']['overallTier']
                        superflex_values['positionalTier'] = superflex_values['tepp']['positionalTier']
                    elif tep_level == 'teppp' and superflex_values.get('teppp', {}).get('value'):
                        superflex_values['value'] = superflex_values['teppp']['value']
                        superflex_values['rank'] = superflex_values['teppp']['rank']
                        superflex_values['positionalRank'] = superflex_values['teppp']['positionalRank']
                        superflex_values['overallTier'] = superflex_values['teppp']['overallTier']
                        superflex_values['positionalTier'] = superflex_values['teppp']['positionalTier']

                filtered_players.append(player_dict)
        else:  # 1qb
            # Only include players with oneQB values
            if player_dict.get('ktc', {}).get('oneQBValues'):
                # Remove superflex values from response
                if 'ktc' in player_dict and player_dict['ktc']:
                    player_dict['ktc']['superflexValues'] = None

                # Apply TEP level filtering to oneQB values
                oneqb_values = player_dict['ktc']['oneQBValues']
                if tep_level and oneqb_values:
                    oneqb_values = _copy_ktc_values_block(oneqb_values)
                    player_dict['ktc']['oneQBValues'] = oneqb_values
                    if tep_level == 'tep' and oneqb_values.get('tep', {}).get('value'):
                        oneqb_values['value'] = oneqb_values['tep']['value']
                        oneqb_values['rank'] = oneqb_values['tep']['rank']
                        oneqb_values['positionalRank'] = oneqb_values['tep']['positionalRank']
                        oneqb_values['overallTier'] = oneqb_values['tep']['overallTier']
                        oneqb_values['positionalTier'] = oneqb_values['tep']['positionalTier']
                    elif tep_level == 'tepp' and oneqb_values.get('tepp', {}).get('value'):
                        oneqb_values['value'] = oneqb_values['tepp']['value']
                        oneqb_values['rank'] = oneqb_values['tepp']['rank']
                        oneqb_values['positionalRank'] = oneqb_values['tepp']['positionalRank']
                        oneqb_values['overallTier'] = oneqb_values['tepp']['overallTier']
                        oneqb_values['positionalTier'] = oneqb_values['tepp']['positionalTier']
                    elif tep_level == 'teppp' and oneqb_values.get('teppp', {}).get('value'):
                        oneqb_values['value'] = oneqb_values['teppp']['value']
                        oneqb_values['rank'] = oneqb_values['teppp']['rank']
                        oneqb_values['positionalRank'] = oneqb_values['teppp']['positionalRank']
                        oneqb_values['overallTier'] = oneqb_values['teppp']['overallTier']
                        oneqb_values['positionalTier'] = oneqb_values['teppp']['positionalTier']

                filtered_players.append(player_dict)

    return filtered_players
