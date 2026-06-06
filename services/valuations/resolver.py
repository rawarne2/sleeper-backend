# services/valuations/resolver.py
from __future__ import annotations
from typing import Dict, Optional
from utils.helpers import create_player_match_key


def build_sleeper_index(players) -> Dict[str, int]:
    """sleeper_player_id -> canonical Player.id."""
    index: Dict[str, int] = {}
    for p in players:
        sid = getattr(p, "sleeper_player_id", None)
        pid = getattr(p, "id", None)
        if sid and pid and sid not in index:
            index[sid] = pid
    return index


def build_name_index(players) -> Dict[str, int]:
    """match_key -> canonical Player.id (fallback when a source has no Sleeper id)."""
    index: Dict[str, int] = {}
    for p in players:
        key = getattr(p, "match_key", None)
        pid = getattr(p, "id", None)
        if key and pid and key not in index:
            index[key] = pid
    return index


def resolve_player_id(*, sleeper_id, name, position, sleeper_index, name_index) -> Optional[int]:
    """Prefer exact Sleeper-id match; fall back to normalized name+position."""
    if sleeper_id and sleeper_id in sleeper_index:
        return sleeper_index[sleeper_id]
    return name_index.get(create_player_match_key(name, position))
