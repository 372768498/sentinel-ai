#!/usr/bin/env bash
# Push Railway env vars from local .env.local (initial provisioning helper).
#
# Reads .env.local line-by-line, filters to a worker-side allowlist, then
# uses --stdin so values never appear in argv (cleaner for transcripts /
# secret hygiene). Hardcodes a SAFE STARTING set of review-only flags so a
# fresh service never auto-publishes before ops has flipped the go-live
# switches.
#
# IMPORTANT — production go-live flags are NOT set here.
# After this script + first deploy, run scripts/railway_go_live_flags.sh
# (or flip via the Railway dashboard) to enable:
#   BOT_ENABLED, BOT_POLLING_ENABLED,
#   MARKETING_EMAIL_DAILY_ENABLED, MARKETING_EMAIL_DAILY_DRY_RUN=false
# See docs/SMOKETEST.md §15 for the full go-live checklist.
#
# Usage: bash scripts/railway_push_env.sh
# Prereq: railway login + railway link to the target service first.
set -euo pipefail

ENV_FILE=".env.local"
SERVICE="sentinel-ai"

if [ ! -f "$ENV_FILE" ]; then
  echo "missing $ENV_FILE — aborting" >&2
  exit 1
fi

ALLOWED='^(DATABASE_URL|WORKER_INTERNAL_TOKEN|WORKER_CORS_ALLOWED_ORIGINS|INTERNAL_CALLBACK_SECRET|APP_URL|FEISHU_APP_ID|FEISHU_APP_SECRET|FEISHU_BITABLE_APP_TOKEN|FEISHU_CAMPAIGNS_TABLE_ID|FEISHU_CONTENT_QUEUE_TABLE_ID|FEISHU_PERFORMANCE_TABLE_ID|FEISHU_REVIEW_CHAT_ID|ANTHROPIC_API_KEY|ANTHROPIC_BASE_URL|MARKETING_COMPOSER_MODEL|MARKETING_FALLBACK_API_KEY|MARKETING_FALLBACK_BASE_URL|MARKETING_FALLBACK_MODEL|MARKETING_ALWAYS_ON_DRAFT_ENABLED|MARKETING_ALWAYS_ON_DRAFT_INTERVAL_MINUTES|MARKETING_ACQUISITION_OPERATOR_ENABLED|MARKETING_ACQUISITION_OPERATOR_INTERVAL_MINUTES|MARKETING_TOP_OPPORTUNITIES_PER_DAY|FMP_API_KEY|SEC_USER_AGENT|DATAFORSEO_LOGIN|DATAFORSEO_PASSWORD|TAVILY_API_KEY|TELEGRAM_BOT_TOKEN|TELEGRAM_BOT_USERNAME|TELEGRAM_CHANNEL_ID_PUBLIC|TELEGRAM_CHANNEL_HANDLE|TELEGRAM_GROUP_ID_VIP|WHOP_API_KEY|WHOP_APP_ID|WHOP_COMPANY_ID|WHOP_FORUM_EXPERIENCE_ID|WHOP_PLAN_ID_PRO|WHOP_PRO_MONTHLY_PRICE_USD|WHOP_PRODUCT_ID_PRO|WHOP_WEBHOOK_SECRET|RESEND_API_KEY|SCANNER_ENABLED|X_DRY_RUN|X_BEARER_TOKEN|PYTHON_SKILL_DIR|PYTHON_EXECUTABLE|SENTINEL_DESK_INQUIRY_EMAIL|SENTINEL_DESK_PRICE_USD)='

set_var() {
  local key="$1"
  local value="$2"
  if [ -z "$value" ]; then
    echo "  skip  $key  (empty)"
    return 0
  fi
  printf '%s' "$value" \
    | railway variable set "$key" --stdin --skip-deploys --service "$SERVICE" >/dev/null 2>&1 \
    || { echo "  FAIL  $key"; return 1; }
  echo "  ok    $key"
}

echo "[1/2] pushing allowlisted vars from $ENV_FILE ..."
grep -E "$ALLOWED" "$ENV_FILE" | while IFS='=' read -r key rest; do
  # Strip surrounding double or single quotes if present
  value="$rest"
  if [[ "$value" =~ ^\".*\"$ ]] || [[ "$value" =~ ^\'.*\'$ ]]; then
    value="${value:1:-1}"
  fi
  set_var "$key" "$value"
done

echo ""
echo "[2/2] pushing safe-default flags (review-only, NOT production go-live) ..."
echo "  ⚠  delivery-critical flags (BOT_*, EMAIL_DAILY_*) are owned by"
echo "  ⚠  scripts/railway_go_live_flags.sh — see docs/SMOKETEST.md §15."
HARDCODED=(
  "ENV=production"
  "GROWTH_OS_PUBLIC_URL=https://app.jilo.ai"
  "RESEND_FROM_EMAIL=Sentinel AI <noreply@mail.jilo.ai>"
  "MARKETING_ENABLED=false"
  "MARKETING_REVIEW_REQUIRED=true"
  "MARKETING_PUBLISH_DRY_RUN=true"
  "MARKETING_QUEUE_POLL_ENABLED=false"
  "MARKETING_QUEUE_POLL_INTERVAL_SECONDS=300"
  "MARKETING_DAILY_DIGEST_HOUR_ET=16"
  "MARKETING_DAILY_DIGEST_MINUTE_ET=30"
  "MARKETING_ALWAYS_ON_DRAFT_ENABLED=true"
  "MARKETING_ALWAYS_ON_DRAFT_INTERVAL_MINUTES=180"
  "MARKETING_ACQUISITION_OPERATOR_ENABLED=true"
  "MARKETING_ACQUISITION_OPERATOR_INTERVAL_MINUTES=180"
  "MARKETING_EMAIL_DAILY_ALLOW_BULK=false"
  "MARKETING_EMAIL_DAILY_HOUR_ET=8"
  "MARKETING_EMAIL_DAILY_MINUTE_ET=15"
  "FEISHU_REVIEW_ENABLED=true"
)
for kv in "${HARDCODED[@]}"; do
  key="${kv%%=*}"
  value="${kv#*=}"
  set_var "$key" "$value"
done

echo ""
echo "done. next steps:"
echo "  1. railway redeploy --service $SERVICE   (or wait for GitHub auto-deploy)"
echo "  2. when ready to go live: bash scripts/railway_go_live_flags.sh"
echo "  3. follow docs/SMOKETEST.md §15 to verify delivery."
