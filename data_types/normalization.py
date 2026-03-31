"""Name normalization for cross-source matching."""
import re
from typing import List


def normalize_name_for_matching(name: str) -> str:
    """
    Normalize a player name for matching purposes.

    This function mimics Sleeper's search_full_name normalization:
    - Convert to lowercase
    - Remove spaces
    - Remove special characters like apostrophes, periods, etc.
    - Handle Unicode escape sequences like \u0027 (apostrophe)

    Args:
        name: Player name to normalize

    Returns:
        Normalized name string
    """
    if not name:
        return ''

    # First, decode any Unicode escape sequences (like \u0027 for apostrophe).
    try:
        normalized = name.encode().decode('unicode_escape')
    except (UnicodeDecodeError, UnicodeEncodeError):
        normalized = name

    normalized = normalized.lower()

    # Convert punctuation/etc into spaces so "Walker III" and "WalkerIII"
    # normalize consistently.
    normalized = re.sub(r'[^0-9a-z]+', ' ', normalized)
    normalized = normalized.strip()
    if not normalized:
        return ''

    # Remove common suffix tokens at the end (JR/SR/II/III/IV) without doing
    # substring replacement (prevents "iii" -> "i" bugs).
    roman_suffixes = ('jr', 'sr', 'ii', 'iii', 'iv')

    tokens = [t for t in re.split(r'\s+', normalized) if t]
    out_tokens: List[str] = []
    for token in tokens:
        token = re.sub(rf'(?:{"|".join(roman_suffixes)})$', '', token)
        if token:
            out_tokens.append(token)

    return ''.join(out_tokens)
