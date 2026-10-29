#!/usr/bin/env bash
#
# Run nightly-sync step(s) as one POST against a running backend. Used by
# .github/workflows/nightly-sync.yml (one request per step keeps each call under
# Vercel's function limit); also handy for manual re-runs.
#
# Usage: BACKEND_ORIGIN=https://sleeper-backend.vercel.app CRON_SECRET=... \
#          scripts/nightly_sync_step.sh <step> [<step>...]
# Steps: ktc leagues research weekly_stats nfl_stats injuries news valuations prewarm
#
# Exits non-zero on a non-2xx response, a timeout, or any entry in summary.errors.
set -euo pipefail

: "${BACKEND_ORIGIN:?set BACKEND_ORIGIN, e.g. https://sleeper-backend.vercel.app}"
: "${CRON_SECRET:?set CRON_SECRET}"
if [ "$#" -lt 1 ]; then
  echo "usage: $0 <step> [<step>...]" >&2
  exit 2
fi

steps_json=$(printf '"%s",' "$@")
body_file=$(mktemp)
trap 'rm -f "$body_file"' EXIT

if ! result=$(curl -sS -o "$body_file" -w '%{http_code} %{time_total}' \
  --max-time "${NIGHTLY_STEP_TIMEOUT:-330}" \
  -X POST "${BACKEND_ORIGIN%/}/api/maintenance/nightly-sync" \
  -H "Authorization: Bearer ${CRON_SECRET}" \
  -H "Content-Type: application/json" \
  -d "{\"steps\": [${steps_json%,}]}"); then
  echo "::error title=nightly-sync $*::request failed or timed out"
  exit 1
fi

python3 - "$body_file" "$result" "$*" <<'PY'
import json, sys

path, result, label = sys.argv[1:]
http, secs = result.split()
print(f"{label}: HTTP {http} in {float(secs):.1f}s")
try:
    with open(path) as f:
        body = json.load(f)
except ValueError:
    with open(path) as f:
        print(f.read()[:2000])
    sys.exit(1)

summary = body.get("summary") or {}
errors = summary.get("errors") or []
print(json.dumps(summary if summary else body, default=str)[:6000])
if not http.startswith("2"):
    print(f"::error title=nightly-sync {label}::HTTP {http}: {body.get('error') or body}")
for err in errors:
    print(f"::error title=nightly-sync {label}::{json.dumps(err, default=str)[:500]}")
sys.exit(0 if http.startswith("2") and not errors else 1)
PY
