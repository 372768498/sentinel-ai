#!/usr/bin/env bash
# Flip Sentinel AI worker from "review-only" to "live delivery" mode on Railway.
#
# Idempotent — safe to re-run. Sets exactly the flags that gate user-facing
# delivery (Telegram broadcasts + daily email radar). Does NOT touch secrets,
# domain config, or scheduler intervals — those belong in
# scripts/railway_push_env.sh and the Railway dashboard.
#
# Usage: bash scripts/railway_go_live_flags.sh
# Prereq: railway login + railway link to the target service first.
#
# To re-enter review-only mode (e.g. pause delivery during incident), run
# bash scripts/railway_go_live_flags.sh --off
set -euo pipefail

SERVICE="sentinel-ai"
MODE="on"
if [ "${1:-}" = "--off" ]; then
  MODE="off"
fi

declare -a FLAGS_ON=(
  "BOT_ENABLED=true"
  "BOT_POLLING_ENABLED=true"
  "MARKETING_EMAIL_DAILY_ENABLED=true"
  "MARKETING_EMAIL_DAILY_DRY_RUN=false"
  "MARKETING_DAILY_DIGEST_ENABLED=true"
  "MARKETING_DAILY_DRAFT_ENABLED=true"
)

declare -a FLAGS_OFF=(
  "BOT_ENABLED=false"
  "BOT_POLLING_ENABLED=false"
  "MARKETING_EMAIL_DAILY_ENABLED=false"
  "MARKETING_EMAIL_DAILY_DRY_RUN=true"
  "MARKETING_DAILY_DIGEST_ENABLED=false"
  "MARKETING_DAILY_DRAFT_ENABLED=false"
)

if [ "$MODE" = "on" ]; then
  FLAGS=("${FLAGS_ON[@]}")
  echo "[go-live] flipping flags ON (live delivery)"
else
  FLAGS=("${FLAGS_OFF[@]}")
  echo "[go-live] flipping flags OFF (review-only mode)"
fi

set_var() {
  local key="$1"
  local value="$2"
  printf '%s' "$value" \
    | railway variable set "$key" --stdin --skip-deploys --service "$SERVICE" >/dev/null 2>&1 \
    || { echo "  FAIL  $key"; return 1; }
  echo "  ok    $key=$value"
}

for kv in "${FLAGS[@]}"; do
  key="${kv%%=*}"
  value="${kv#*=}"
  set_var "$key" "$value"
done

echo ""
echo "done. one redeploy required for the worker to pick the new env:"
echo "  railway redeploy --service $SERVICE"
echo ""
echo "then verify with docs/SMOKETEST.md §15 (Production Go-Live Flags)."
