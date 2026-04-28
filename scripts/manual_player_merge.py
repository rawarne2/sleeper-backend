"""
Manual Player Merge Utility

This script handles manual merging of players that have different name variations
between KTC and Sleeper data sources that the automatic matching doesn't catch.

Examples:
- "Cam Ward" vs "Cameron Ward"
- "Kenneth Walker III" vs "Kenneth Walker"
- Other similar name variations

Usage:
    python scripts/manual_player_merge.py
"""

from data_types.normalization import normalize_name_for_matching
from utils.helpers import create_player_match_key
from models.extensions import db
from models.entities import Player, PlayerKTCOneQBValues, PlayerKTCSuperflexValues
from app import app
import logging
import os
import sys
from typing import Dict, List, Optional, Set
from datetime import datetime, UTC

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Manual merge mappings - Add players that need manual merging here
# Format: (ktc_name, sleeper_name, position)
MANUAL_MERGE_MAPPINGS = [
    # QB mappings
    ("Cam Ward", "Cameron Ward", "QB"),

    # RB mappings
    ("Kenneth Walker III", "Kenneth Walker", "RB"),

    # WR mappings
    ("Marquise Brown", "Hollywood Brown", "WR"),  # Hollywood is his nickname
    ("Calvin Austin III", "Calvin Austin", "WR"),
    ("Gabriel Davis", "Gabe Davis", "WR"),

    # TE mappings
    ("Chigoziem Okonkwo", "Chig Okonkwo", "TE"),

    # Add more mappings as needed
    # ("KTC Name", "Sleeper Name", "Position"),
]

_ROMAN_NAME_SUFFIXES = frozenset({'jr', 'sr', 'ii', 'iii', 'iv'})


def _roman_suffix_token(name: Optional[str]) -> Optional[str]:
    """Return jr/sr/ii/iii/iv if name ends with that token, else None."""
    if not name or not name.strip():
        return None
    parts = name.replace(',', ' ').split()
    if not parts:
        return None
    last = parts[-1].strip('.,').lower()
    return last if last in _ROMAN_NAME_SUFFIXES else None


def _first_name_compatible(label: str, player: Player) -> bool:
    """True if first tokens look like the same person (Cam vs Cameron)."""
    lt = (label.split() or [''])[0].lower()
    if not lt:
        return False
    for attr in ('player_name', 'full_name', 'search_full_name'):
        raw = getattr(player, attr, None)
        if not raw:
            continue
        ft = (raw.split() or [''])[0].lower().strip('.,')
        if not ft:
            continue
        if ft == lt or ft.startswith(lt) or lt.startswith(ft):
            return True
    return False


def _best_match_for_label(cluster: List[Player], label: str) -> Optional[Player]:
    """
    Pick the cluster row that best matches the mapping label (display string).

    Handles suffix-stripped normalization: Walker vs Walker III share match_key but must
    map to different rows using exact text and generational-suffix rules.
    """
    if not cluster:
        return None

    exact = [
        p for p in cluster
        if p.player_name == label or p.full_name == label
        or (p.player_name and p.player_name.lower() == label.lower())
        or (p.full_name and p.full_name.lower() == label.lower())
    ]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        return min(exact, key=lambda p: p.id)

    label_suffix = _roman_suffix_token(label)
    if label_suffix is not None:
        suffixed = []
        for p in cluster:
            ps = _roman_suffix_token(p.player_name) or _roman_suffix_token(p.full_name)
            if ps == label_suffix:
                suffixed.append(p)
        if len(suffixed) == 1:
            return suffixed[0]
        if len(suffixed) > 1:
            return min(suffixed, key=lambda p: p.id)

    nosuf = [
        p for p in cluster
        if not _roman_suffix_token(p.player_name)
        and not _roman_suffix_token(p.full_name)
    ]
    if len(nosuf) == 1:
        return nosuf[0]
    if len(nosuf) > 1:
        return min(nosuf, key=lambda p: (len(p.player_name or ''), p.id))

    compat = [p for p in cluster if _first_name_compatible(label, p)]
    if len(compat) == 1:
        return compat[0]
    if len(compat) > 1:
        return min(compat, key=lambda p: p.id)

    nl = normalize_name_for_matching(label)
    norm_hits = [
        p for p in cluster
        if p.player_name and normalize_name_for_matching(p.player_name) == nl
    ]
    if len(norm_hits) == 1:
        return norm_hits[0]

    logger.warning(
        "Could not disambiguate label '%s' within cluster ids %s",
        label, [p.id for p in cluster])
    return None


def _match_keys_for_pair(ktc_name: str, sleeper_name: str, position: str) -> Set[str]:
    pos = position.upper()
    keys = {
        create_player_match_key(ktc_name, pos),
        create_player_match_key(sleeper_name, pos),
    }
    keys.discard('')
    return keys


class ManualPlayerMerger:
    """Handles manual merging of specific player records."""

    def __init__(self):
        self.app = app
        self.merged_count = 0
        self.error_count = 0
        self.errors = []

    def find_player_by_name_and_position(self, name: str, position: str) -> Optional[Player]:
        """
        Find a player by name and position using various matching strategies.

        Args:
            name: Player name to search for
            position: Player position

        Returns:
            Player record if found, None otherwise
        """
        position = position.upper()

        # Try exact match first
        player = Player.query.filter_by(
            player_name=name, position=position).first()
        if player:
            return player

        # Try match using full_name field
        player = Player.query.filter_by(
            full_name=name, position=position).first()
        if player:
            return player

        # Try normalized name matching
        match_key = create_player_match_key(name, position)
        player = Player.query.filter_by(match_key=match_key).first()
        if player:
            return player

        # Try fuzzy matching on normalized names
        normalized_search = normalize_name_for_matching(name)
        players = Player.query.filter_by(position=position).all()

        for player in players:
            # Check player_name
            if player.player_name and normalize_name_for_matching(player.player_name) == normalized_search:
                return player
            # Check full_name
            if player.full_name and normalize_name_for_matching(player.full_name) == normalized_search:
                return player
            # Check search_full_name
            if player.search_full_name and normalize_name_for_matching(player.search_full_name) == normalized_search:
                return player

        return None

    def find_cluster_for_mapping(
            self, ktc_name: str, sleeper_name: str, position: str) -> List[Player]:
        """
        All Player rows at this position that share a match_key with either mapping name.

        KTC and Sleeper often use different spellings (Cam vs Cameron) or suffixes that
        normalize to the same key; fuzzy .first() lookups then return the same row twice
        and leave real duplicates untouched.
        """
        pos = position.upper()
        keys = _match_keys_for_pair(ktc_name, sleeper_name, pos)
        by_id: Dict[int, Player] = {}
        for mk in keys:
            for p in Player.query.filter_by(position=pos, match_key=mk).all():
                by_id[p.id] = p
        for p in Player.query.filter_by(position=pos).all():
            if p.id in by_id:
                continue
            if not (p.player_name or '').strip():
                continue
            inferred = (p.match_key or '').strip() or create_player_match_key(
                p.player_name, pos)
            if inferred in keys:
                by_id[p.id] = p
        # Stale/wrong match_key rows (e.g. kennethwalkeri-RB vs kennethwalker-RB) still
        # normalize to the same person as the mapping labels.
        nl_targets = {
            normalize_name_for_matching(ktc_name),
            normalize_name_for_matching(sleeper_name),
        }
        nl_targets.discard('')
        for p in Player.query.filter_by(position=pos).all():
            if p.id in by_id:
                continue
            pn = normalize_name_for_matching(p.player_name or '')
            if pn and pn in nl_targets:
                by_id[p.id] = p
        # Same KTC id twice = duplicate rows from saves; fold together.
        for _ in range(4):
            before = len(by_id)
            kid_set = {p.ktc_player_id for p in by_id.values() if p.ktc_player_id}
            for kid in kid_set:
                for p in Player.query.filter_by(position=pos, ktc_player_id=kid).all():
                    by_id[p.id] = p
            if len(by_id) == before:
                break
        if not by_id:
            for label in (ktc_name, sleeper_name):
                pl = self.find_player_by_name_and_position(label, pos)
                if pl:
                    by_id[pl.id] = pl
        return sorted(by_id.values(), key=lambda p: p.id)

    def merge_player_records(self, ktc_player: Player, sleeper_player: Player) -> bool:
        """
        Merge two player records by combining their data into the Sleeper-based record
        and deleting the KTC-only record.

        Args:
            ktc_player: Player record from KTC data (to be merged and deleted)
            sleeper_player: Player record from Sleeper data (to be kept and updated)

        Returns:
            True if successful, False otherwise
        """
        try:
            if ktc_player.id == sleeper_player.id:
                logger.info("Skip merge: same row id=%s", ktc_player.id)
                return True

            logger.info("Merging players: KTC='%s' (%d) -> Sleeper='%s' (%d)",
                        ktc_player.player_name, ktc_player.id,
                        sleeper_player.player_name, sleeper_player.id)

            # Transfer KTC-specific data to the Sleeper record
            if ktc_player.ktc_player_id and not sleeper_player.ktc_player_id:
                sleeper_player.ktc_player_id = ktc_player.ktc_player_id

            if ktc_player.age and not sleeper_player.age:
                sleeper_player.age = ktc_player.age

            if ktc_player.rookie and not sleeper_player.rookie:
                sleeper_player.rookie = ktc_player.rookie

            # Transfer KTC fields
            ktc_fields = [
                'slug', 'positionID', 'seasonsExperience',
                'pickRound', 'pickNum', 'isFeatured', 'isStartSitFeatured', 'isTrending',
                'isDevyReturningToSchool', 'isDevyYearDecrement', 'teamLongName',
                'draftYear', 'byeWeek', 'injury'
            ]

            for field in ktc_fields:
                ktc_value = getattr(ktc_player, field, None)
                sleeper_value = getattr(sleeper_player, field, None)
                if ktc_value and not sleeper_value:
                    setattr(sleeper_player, field, ktc_value)

            # Transfer KTC ranking values (drop duplicate child rows if both exist)
            if ktc_player.oneqb_values and sleeper_player.oneqb_values:
                db.session.delete(ktc_player.oneqb_values)
                db.session.flush()
            if ktc_player.superflex_values and sleeper_player.superflex_values:
                db.session.delete(ktc_player.superflex_values)
                db.session.flush()

            if ktc_player.oneqb_values and not sleeper_player.oneqb_values:
                ktc_player.oneqb_values.player_id = sleeper_player.id
                sleeper_player.oneqb_values = ktc_player.oneqb_values

            if ktc_player.superflex_values and not sleeper_player.superflex_values:
                ktc_player.superflex_values.player_id = sleeper_player.id
                sleeper_player.superflex_values = ktc_player.superflex_values

            # Ensure match_key is set for efficient future lookups
            if not sleeper_player.match_key:
                sleeper_player.match_key = create_player_match_key(
                    sleeper_player.player_name, sleeper_player.position)

            # Update timestamp
            sleeper_player.last_updated = datetime.now(UTC)

            # Delete the KTC-only record
            db.session.delete(ktc_player)

            # Commit the changes
            db.session.commit()

            logger.info("Successfully merged players: '%s' -> '%s'",
                        ktc_player.player_name, sleeper_player.player_name)
            return True

        except Exception as e:
            logger.error("Failed to merge players '%s' and '%s': %s",
                         ktc_player.player_name, sleeper_player.player_name, e)
            db.session.rollback()
            return False

    def process_manual_merges(self) -> Dict[str, any]:
        """
        Process all manual merge mappings.

        Returns:
            Dictionary with merge results
        """
        results = {
            'total_mappings': len(MANUAL_MERGE_MAPPINGS),
            'successful_merges': 0,
            'failed_merges': 0,
            'not_found': 0,
            'already_merged': 0,
            'errors': [],
            'merged_players': []
        }

        with self.app.app_context():
            for ktc_name, sleeper_name, position in MANUAL_MERGE_MAPPINGS:
                try:
                    logger.info("Processing mapping: KTC='%s' -> Sleeper='%s' (%s)",
                                ktc_name, sleeper_name, position)

                    cluster = self.find_cluster_for_mapping(
                        ktc_name, sleeper_name, position)
                    if not cluster:
                        logger.warning(
                            "No players found for mapping: KTC='%s', Sleeper='%s' (%s)",
                            ktc_name, sleeper_name, position)
                        results['not_found'] += 1
                        continue

                    canonical = _best_match_for_label(cluster, sleeper_name)
                    if not canonical:
                        logger.warning(
                            "Could not resolve canonical row for '%s' (%s)",
                            sleeper_name, position)
                        results['not_found'] += 1
                        continue

                    ids_to_fold = sorted({p.id for p in cluster} - {canonical.id})
                    if not ids_to_fold:
                        logger.info(
                            "Already consolidated: '%s' / '%s' (%s)",
                            ktc_name, sleeper_name, position)
                        results['already_merged'] += 1
                        continue

                    for pid in ids_to_fold:
                        row = db.session.get(Player, pid)
                        if row is None:
                            continue
                        if row.id == canonical.id:
                            continue
                        if self.merge_player_records(row, canonical):
                            results['successful_merges'] += 1
                            results['merged_players'].append({
                                'ktc_name': ktc_name,
                                'sleeper_name': sleeper_name,
                                'position': position,
                                'merged_into': canonical.player_name,
                                'folded_id': pid,
                            })
                        else:
                            results['failed_merges'] += 1

                except Exception as e:
                    error_msg = f"Error processing mapping {ktc_name} -> {sleeper_name}: {e}"
                    logger.error(error_msg)
                    results['errors'].append(error_msg)
                    results['failed_merges'] += 1
                    continue

        return results

    def find_potential_duplicates(self, limit: int = 50) -> List[Dict[str, any]]:
        """
        Find potential duplicate players that might need manual merging.

        Args:
            limit: Maximum number of potential duplicates to return

        Returns:
            List of potential duplicate groups
        """
        with self.app.app_context():
            # Find players with similar normalized names in the same position
            duplicates = []

            # Get all players grouped by position
            positions = ['QB', 'RB', 'WR', 'TE']

            for position in positions:
                players = Player.query.filter_by(position=position).all()

                # Group by match_key (suffix-stripped, same as merge pipeline)
                name_groups = {}
                for player in players:
                    if not player.player_name:
                        continue
                    mk = (player.match_key or '').strip() or create_player_match_key(
                        player.player_name, position)
                    if mk not in name_groups:
                        name_groups[mk] = []
                    if player not in name_groups[mk]:
                        name_groups[mk].append(player)

                # Find groups with multiple players
                for mk_key, group_players in name_groups.items():
                    if len(group_players) > 1:
                        # Check if they're actually different players (different sleeper_player_ids)
                        sleeper_ids = set()
                        for p in group_players:
                            if p.sleeper_player_id:
                                sleeper_ids.add(p.sleeper_player_id)

                        # If they have different Sleeper IDs, they're different people
                        if len(sleeper_ids) > 1:
                            continue

                        # If some have no Sleeper ID, they might be duplicates
                        duplicates.append({
                            'match_key': mk_key,
                            'position': position,
                            'players': [
                                {
                                    'id': p.id,
                                    'player_name': p.player_name,
                                    'full_name': p.full_name,
                                    'sleeper_player_id': p.sleeper_player_id,
                                    'ktc_player_id': p.ktc_player_id,
                                    'has_oneqb': bool(p.oneqb_values),
                                    'has_superflex': bool(p.superflex_values)
                                }
                                for p in group_players
                            ]
                        })

                        if len(duplicates) >= limit:
                            break

                if len(duplicates) >= limit:
                    break

            return duplicates[:limit]


def main():
    """Main function to run manual player merging."""
    print("=== Manual Player Merge Utility ===")
    print(f"Processing {len(MANUAL_MERGE_MAPPINGS)} manual merge mappings...")

    merger = ManualPlayerMerger()

    # Process manual merges
    results = merger.process_manual_merges()

    # Print results
    print("\n=== Merge Results ===")
    print(f"Total mappings processed: {results['total_mappings']}")
    print(f"Successful merges: {results['successful_merges']}")
    print(f"Failed merges: {results['failed_merges']}")
    print(f"Players not found: {results['not_found']}")
    print(f"Already merged: {results['already_merged']}")

    if results['merged_players']:
        print("\n=== Successfully Merged Players ===")
        for merge in results['merged_players']:
            print(
                f"  • {merge['ktc_name']} -> {merge['sleeper_name']} ({merge['position']}) = {merge['merged_into']}")

    if results['errors']:
        print("\n=== Errors ===")
        for error in results['errors']:
            print(f"  • {error}")

    # Find potential duplicates for review
    print("\n=== Finding Potential Duplicates ===")
    duplicates = merger.find_potential_duplicates(limit=10)

    if duplicates:
        print(f"Found {len(duplicates)} potential duplicate groups:")
        for dup in duplicates:
            print(
                f"\nPosition: {dup['position']}, match_key: '{dup['match_key']}'")
            for player in dup['players']:
                sleeper_id = player['sleeper_player_id'] or 'None'
                ktc_id = player['ktc_player_id'] or 'None'
                values = []
                if player['has_oneqb']:
                    values.append('1QB')
                if player['has_superflex']:
                    values.append('SF')
                values_str = ','.join(values) if values else 'No values'

                print(f"  • ID:{player['id']} '{player['player_name']}' (full: '{player['full_name']}') "
                      f"Sleeper:{sleeper_id} KTC:{ktc_id} Values:{values_str}")
    else:
        print("No potential duplicates found.")

    print("\n=== Manual Merge Complete ===")


if __name__ == "__main__":
    main()
