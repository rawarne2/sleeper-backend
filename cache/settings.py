"""Redis cache defaults and env-backed settings."""
import os

DEFAULT_KTC_RANKINGS_REDIS_TTL_SECONDS = 86400
# Bundle is invalidated explicitly on KTC refresh and league sync, so a long
# TTL fits nightly-sync (which ends with dashboard prewarm) on a Hobby-safe daily cron.
DEFAULT_DASHBOARD_LEAGUE_REDIS_TTL_SECONDS = 86400
# Full player universe changes only on KTC refresh (invalidated there), same as rankings.
DEFAULT_PLAYERS_ALL_REDIS_TTL_SECONDS = 86400


def ktc_rankings_redis_ttl_seconds() -> int:
    return int(
        os.getenv(
            "KTC_RANKINGS_REDIS_TTL_SECONDS",
            str(DEFAULT_KTC_RANKINGS_REDIS_TTL_SECONDS),
        )
    )


def players_all_redis_ttl_seconds() -> int:
    return int(
        os.getenv(
            "PLAYERS_ALL_REDIS_TTL_SECONDS",
            str(DEFAULT_PLAYERS_ALL_REDIS_TTL_SECONDS),
        )
    )


def dashboard_league_redis_ttl_seconds() -> int:
    return int(
        os.getenv(
            "DASHBOARD_LEAGUE_REDIS_TTL_SECONDS",
            str(DEFAULT_DASHBOARD_LEAGUE_REDIS_TTL_SECONDS),
        )
    )
