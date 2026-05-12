#!/usr/bin/env bash
# One-off Vercel env push for sentinel-ai (Next.js side).
#
# Reads .env.local + Railway Postgres public URL, filters to a Next.js-side
# allowlist, then pipes values to `vercel env add --yes --force` via stdin
# (values never appear in argv — cleaner transcripts).
#
# Requires: VERCEL_TOKEN env, .vercel/repo.json (from vercel link), railway
# CLI logged in.
set -euo pipefail

ENV_FILE=".env.local"
WORKER_URL="https://sentinel-ai-production-7c2d.up.railway.app"

if [ -z "${VERCEL_TOKEN:-}" ]; then
  echo "VERCEL_TOKEN required" >&2
  exit 1
fi
export VERCEL_TOKEN

# Allowlist (Next.js side only — DATABASE_URL handled separately so we use
# the PUBLIC Postgres URL, not the .env.local local-host value)
ALLOWED='^(APP_URL|NEXT_PUBLIC_APP_URL|WORKER_INTERNAL_TOKEN|INTERNAL_CALLBACK_SECRET|WHOP_APP_ID|WHOP_API_KEY|WHOP_WEBHOOK_SECRET|WHOP_PRODUCT_ID_PRO|WHOP_PLAN_ID_PRO|WHOP_PRO_MONTHLY_PRICE_USD|WHOP_COMPANY_ID|WHOP_FORUM_EXPERIENCE_ID|NEXT_PUBLIC_WHOP_CHECKOUT_URL_PRO|RESEND_API_KEY|RESEND_FROM_EMAIL|TELEGRAM_BOT_TOKEN|TELEGRAM_BOT_USERNAME|TELEGRAM_GROUP_ID_VIP|NEXT_PUBLIC_TELEGRAM_FREE_URL|SENTINEL_DESK_PRICE_USD|SENTINEL_DESK_INQUIRY_EMAIL)='

set_var() {
  local key="$1"
  local value="$2"
  if [ -z "$value" ]; then
    echo "  skip  $key  (empty)"
    return 0
  fi
  # First try add; if it fails (already exists), remove + re-add.
  if printf '%s' "$value" | vercel env add "$key" production --yes >/dev/null 2>&1; then
    echo "  ok    $key"
    return 0
  fi
  # exists — remove then re-add
  vercel env rm "$key" production --yes >/dev/null 2>&1 || true
  if printf '%s' "$value" | vercel env add "$key" production --yes >/dev/null 2>&1; then
    echo "  ok    $key  (replaced)"
  else
    echo "  FAIL  $key"
    return 1
  fi
}

echo "[1/3] pushing allowlisted vars from $ENV_FILE ..."
grep -E "$ALLOWED" "$ENV_FILE" | while IFS='=' read -r key rest; do
  value="$rest"
  if [[ "$value" =~ ^\".*\"$ ]] || [[ "$value" =~ ^\'.*\'$ ]]; then
    value="${value:1:-1}"
  fi
  set_var "$key" "$value"
done

echo ""
echo "[2/3] pushing Worker URLs ..."
set_var "WORKER_API_BASE_URL"     "$WORKER_URL"
set_var "NEXT_PUBLIC_WORKER_URL"  "$WORKER_URL"

echo ""
echo "[3/3] pushing DATABASE_URL (Railway Postgres PUBLIC) ..."
DB_PUBLIC=$(railway variables --service Postgres --json | python -c "import json,sys;print(json.load(sys.stdin)['DATABASE_PUBLIC_URL'])")
set_var "DATABASE_URL" "$DB_PUBLIC"

echo ""
echo "done. next: vercel --prod --yes"
