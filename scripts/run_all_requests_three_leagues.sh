#!/usr/bin/env bash
#
# HTTP integration / smoke: curl against a *running* backend (see BASE_URL). Uses
# CRON_SECRET / DAILY_REFRESH_SECRET from .env for maintenance routes. This is NOT
# a database seed.
#
# For in-process KTC + league + research + weekly stats (no HTTP server), use:
#   python scripts/seed_three_leagues.py
#   ./scripts/seed_three_leagues.sh
#
# Run requests.http-equivalent calls for three default leagues; skip 2026 weekly stats.
set -uo pipefail

BASE="${BASE_URL:-http://127.0.0.1:5001}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT" || exit 1

CRON_SECRET=$(grep '^CRON_SECRET=' .env 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'")
DAILY_REFRESH_SECRET=$(grep '^DAILY_REFRESH_SECRET=' .env 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'")

KTC_SF_DYN="tep_level=tep&is_redraft=false&league_format=superflex"
KTC_1QB_DYN="tep_level=tep&is_redraft=false&league_format=1qb"
KTC_SF_RD="tep_level=&is_redraft=true&league_format=superflex"

# league_id:season (2026 league: no /stats/*)
LEAGUES=(
  "1050831680350568448:2024"
  "1210364682523656192:2025"
  "1333945997071515648:2026"
)

LEAGUE_TYPE="dynasty"
WEEK=1
HDR_JSON=(-H "Accept: application/json" -H "Content-Type: application/json")

FAILED=()
BODY="/tmp/sleeper_req_body_$$.json"
ERR="/tmp/sleeper_req_err_$$.txt"

cleanup() { rm -f "$BODY" "$ERR" 2>/dev/null; }
trap cleanup EXIT

record_fail() {
  FAILED+=("$1")
}

# args: name, max_seconds, curl_args...
req() {
  local name="$1"
  local maxt="$2"
  shift 2
  local code
  code=$(curl -sS -o "$BODY" -w "%{http_code}" --max-time "$maxt" "$@" 2>"$ERR" || echo "000")
  if [[ "$code" =~ ^(200|201|202|204)$ ]]; then
    echo "OK  $code  $name"
    return 0
  fi
  echo "FAIL $code  $name"
  if [[ -s "$ERR" ]]; then
    echo "     curl: $(head -1 "$ERR")"
  fi
  if [[ -s "$BODY" ]]; then
    echo "     body: $(head -c 400 "$BODY" | tr '\n' ' ')"
  fi
  record_fail "$name (HTTP $code)"
  return 1
}

league_name_for() {
  local lid="$1"
  curl -sS --max-time 120 "${HDR_JSON[@]}" "$BASE/api/sleeper/league/$lid" | jq -r '
    (.data.league.name // .data.league_info.name // .data.name // empty)
    | if . == null or . == "" then "Fantasy League" else . end
  ' 2>/dev/null || echo "Fantasy League"
}

echo "=== BASE=$BASE ==="

req "GET /api/maintenance/health" 60 "$BASE/api/maintenance/health" "${HDR_JSON[@]}"

req "GET /api/maintenance/nightly-sync" 3600 \
  -H "Accept: application/json" \
  -H "Authorization: Bearer ${CRON_SECRET}" \
  "$BASE/api/maintenance/nightly-sync"

req "POST /api/maintenance/daily-refresh" 3600 \
  "${HDR_JSON[@]}" \
  -H "X-Daily-Refresh-Secret: ${DAILY_REFRESH_SECRET}" \
  -d '{}' \
  "$BASE/api/maintenance/daily-refresh"

req "GET /api/ktc/health" 60 "$BASE/api/ktc/health" "${HDR_JSON[@]}"

req "POST /api/sleeper/refresh" 900 "${HDR_JSON[@]}" -d '{}' -X POST "$BASE/api/sleeper/refresh"

for pair in "${LEAGUES[@]}"; do
  LID="${pair%%:*}"
  SEASON="${pair##*:}"
  echo "--- League $LID season $SEASON ---"

  NAME="$(league_name_for "$LID")"
  echo "    league_name=$NAME"

  req "GET dashboard league=$LID season=$SEASON" 120 \
    "${HDR_JSON[@]}" \
    "$BASE/api/dashboard/league/${LID}?season=${SEASON}&${KTC_SF_DYN}"

  req "GET /api/sleeper/league/$LID" 120 "${HDR_JSON[@]}" "$BASE/api/sleeper/league/$LID"

  req "PUT /api/sleeper/league/$LID" 300 "${HDR_JSON[@]}" -X PUT -d '{}' "$BASE/api/sleeper/league/$LID"

  req "POST /api/sleeper/league/$LID" 300 "${HDR_JSON[@]}" -X POST -d '{}' "$BASE/api/sleeper/league/$LID"

  req "GET rosters $LID" 120 "${HDR_JSON[@]}" "$BASE/api/sleeper/league/$LID/rosters"

  req "GET users $LID" 120 "${HDR_JSON[@]}" "$BASE/api/sleeper/league/$LID/users"

  req "GET research season=$SEASON" 120 \
    "${HDR_JSON[@]}" \
    "$BASE/api/sleeper/players/research/${SEASON}?week=${WEEK}&league_type=${LEAGUE_TYPE}"

  req "POST research season=$SEASON" 300 \
    "${HDR_JSON[@]}" \
    -X POST -d '{}' \
    "$BASE/api/sleeper/players/research/${SEASON}?week=${WEEK}&league_type=${LEAGUE_TYPE}"

  req "PUT research season=$SEASON" 300 \
    "${HDR_JSON[@]}" \
    -X PUT -d '{}' \
    "$BASE/api/sleeper/players/research/${SEASON}?week=${WEEK}&league_type=${LEAGUE_TYPE}"

  if [[ "$SEASON" == "2026" ]]; then
    echo "    (skip weekly stats for 2026)"
    continue
  fi

  jq -n \
    --arg n "$NAME" \
    --arg s "$SEASON" \
    --arg t "$LEAGUE_TYPE" \
    '{league_name: $n, season: $s, league_type: $t}' >"$BODY"

  req "POST stats/seed league=$LID" 300 \
    "${HDR_JSON[@]}" \
    -d @"$BODY" \
    "$BASE/api/sleeper/league/$LID/stats/seed"

  req "PUT stats/week/$WEEK league=$LID season=$SEASON" 300 \
    "${HDR_JSON[@]}" \
    -X PUT -d '{}' \
    "$BASE/api/sleeper/league/$LID/stats/week/${WEEK}?season=${SEASON}&league_type=${LEAGUE_TYPE}"

  req "POST stats/week/$WEEK league=$LID season=$SEASON" 300 \
    "${HDR_JSON[@]}" \
    -X POST -d '{}' \
    "$BASE/api/sleeper/league/$LID/stats/week/${WEEK}?season=${SEASON}&league_type=${LEAGUE_TYPE}"

  req "GET stats/week/$WEEK league=$LID" 120 \
    "${HDR_JSON[@]}" \
    "$BASE/api/sleeper/league/$LID/stats/week/${WEEK}?season=${SEASON}&league_type=${LEAGUE_TYPE}"

  req "GET stats/week/$WEEK average league=$LID" 120 \
    "${HDR_JSON[@]}" \
    "$BASE/api/sleeper/league/$LID/stats/week/${WEEK}?season=${SEASON}&league_type=${LEAGUE_TYPE}&average=true"
done

req "POST /api/ktc/refresh/all" 1800 "${HDR_JSON[@]}" -X POST -d '{}' "$BASE/api/ktc/refresh/all"

req "POST /api/ktc/refresh superflex dyn tep" 900 \
  "${HDR_JSON[@]}" -X POST -d '{}' \
  "$BASE/api/ktc/refresh?${KTC_SF_DYN}"

req "POST /api/ktc/refresh 1qb dyn tep" 900 \
  "${HDR_JSON[@]}" -X POST -d '{}' \
  "$BASE/api/ktc/refresh?${KTC_1QB_DYN}"

req "POST /api/ktc/refresh superflex redraft" 900 \
  "${HDR_JSON[@]}" -X POST -d '{}' \
  "$BASE/api/ktc/refresh?${KTC_SF_RD}"

req "GET /api/ktc/rankings" 120 "${HDR_JSON[@]}" "$BASE/api/ktc/rankings?${KTC_SF_DYN}"

req "POST /api/ktc/cleanup" 300 "${HDR_JSON[@]}" -X POST -d '{}' "$BASE/api/ktc/cleanup?${KTC_SF_DYN}"

echo ""
if ((${#FAILED[@]})); then
  echo "=== FAILURES (${#FAILED[@]}) ==="
  for f in "${FAILED[@]}"; do echo " - $f"; done
  exit 1
fi
echo "=== ALL OK ==="
exit 0
