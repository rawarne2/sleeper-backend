"""Rules for which Sleeper / merged players may be persisted or used in KTC merge."""
from __future__ import annotations

from typing import Any, Dict

from utils.constants import (
    POSITION_KEY,
    SLEEPER_POSITION_RDP,
    SLEEPER_SEARCH_RANK_EXCLUDE,
)


def is_excluded_search_rank(search_rank: Any) -> bool:
    try:
        return int(search_rank) == SLEEPER_SEARCH_RANK_EXCLUDE
    except (TypeError, ValueError):
        return False


def sleeper_api_dict_should_persist(sleeper_data: Dict[str, Any]) -> bool:
    """False for draft placeholders and rows we cannot key (Sleeper search_rank sentinel)."""
    name = (sleeper_data.get("full_name") or sleeper_data.get("player_name") or "").strip()
    pos = (sleeper_data.get("position") or "").strip().upper()
    if pos == SLEEPER_POSITION_RDP:
        return bool(name)
    if is_excluded_search_rank(sleeper_data.get("search_rank")):
        return False
    return bool(name and pos)


def merged_player_row_should_save(player_data: Dict[str, Any]) -> bool:
    """Skip persisting merged KTC rows that map to non-rosterable Sleeper entities."""
    pos = (player_data.get(POSITION_KEY) or "").strip().upper()
    if pos == SLEEPER_POSITION_RDP:
        return True
    if is_excluded_search_rank(player_data.get("search_rank")):
        return False
    return True


def sqlalchemy_player_eligible_for_merge_filter():
    """SQLAlchemy boolean expression: players usable for KTC merge from DB."""
    from models.entities import Player
    from sqlalchemy import and_, or_

    return and_(
        Player.sleeper_player_id.isnot(None),
        Player.match_key.isnot(None),
        Player.match_key != "",
        or_(
            Player.search_rank.is_(None),
            Player.search_rank != SLEEPER_SEARCH_RANK_EXCLUDE,
        ),
    )
