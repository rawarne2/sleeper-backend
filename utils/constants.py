"""Shared constants and environment-derived configuration."""
import os

VALID_TEP_LEVELS = ['tep', 'tepp', 'teppp']

DYNASTY_URL = "https://keeptradecut.com/dynasty-rankings"
FANTASY_URL = "https://keeptradecut.com/fantasy-rankings"
SLEEPER_API_URL = "https://api.sleeper.app/v1/players/nfl"

PLAYER_NAME_KEY = "playerName"
POSITION_KEY = "position"
TEAM_KEY = "team"
AGE_KEY = "age"
ROOKIE_KEY = "rookie"

# Sleeper uses this search_rank for non-player / draft-pick style rows; exclude from DB and merge.
SLEEPER_SEARCH_RANK_EXCLUDE = 9_999_999

# Rookie/draft pick rows — often inactive and/or use the search_rank sentinel; still persist.
SLEEPER_POSITION_RDP = "RDP"

# Fantasy weeks included in season aggregates (dashboard per-player stats, ``average=true`` GET stats).
# Week 18 is excluded so end-of-regular-season rests, tanking, and soft matchups skew averages less.
SLEEPER_STATS_AGGREGATE_WEEK_MIN = 1
SLEEPER_STATS_AGGREGATE_WEEK_MAX = 17

DATABASE_URI = os.getenv(
    'TEST_DATABASE_URI',
    os.getenv('DATABASE_URL',
              'postgresql://postgres:password@localhost:5433/sleeper_db?sslmode=disable')
)

if DATABASE_URI and DATABASE_URI.startswith('postgres://'):
    DATABASE_URI = DATABASE_URI.replace('postgres://', 'postgresql://', 1)
