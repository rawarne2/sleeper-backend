#!/usr/bin/env bash
# Thin wrapper: runs ``python scripts/seed_three_leagues.py`` from the repo root (or /app in Docker).
# For behavior and flags, see that script. Typical:
#   ./scripts/seed_three_leagues.sh
#   docker exec -it sleeper-backend ./scripts/seed_three_leagues.sh --skip-nfl
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT" || exit 1
exec python scripts/seed_three_leagues.py "$@"
