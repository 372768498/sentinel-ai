# Sentinel AI Production Env Matrix

## Next.js / Vercel

| Variable | Required | Example | Notes |
| --- | --- | --- | --- |
| `NEXT_PUBLIC_APP_URL` | Yes | `https://sentinel.example.com` | Public frontend origin. |
| `APP_URL` | Yes | `https://sentinel.example.com` | Used by the API when building callback and redirect URLs. |
| `DATABASE_URL` | Yes | `postgresql://...` | Supabase / Postgres connection string for Prisma. |
| `NEXT_PUBLIC_WORKER_URL` | Yes | `https://sentinel-worker.up.railway.app` | Public worker base URL for browser SSE. |
| `WORKER_API_BASE_URL` | Yes | `https://sentinel-worker.up.railway.app` | Server-side worker URL used by `/api/analyze`. |
| `WORKER_INTERNAL_TOKEN` | Yes | random secret | Must match Railway worker. |
| `INTERNAL_CALLBACK_SECRET` | Yes | random secret | Must match Railway worker callback header. |
| `LEMON_SQUEEZY_API_KEY` | Yes | `ls_live_xxx` | Use live key in production. |
| `LEMON_SQUEEZY_STORE_ID` | Yes | `123456` | Live store ID in production. |
| `LEMON_SQUEEZY_PRO_VARIANT_ID` | Yes | `123456` | Live Pro variant ID in production. |
| `LEMON_SQUEEZY_WEBHOOK_SECRET` | Yes | random secret | Secret configured on the live webhook. |
| `LEMON_SQUEEZY_MODE` | Yes | `live` | `test` for local/dev only. Production must be `live`. |
| `LEMON_SQUEEZY_PRO_MONTHLY_PRICE_USD` | No | `19.9` | Used for MRR estimate in admin stats. |
| `NEXT_PUBLIC_LEMON_SQUEEZY_CHECKOUT_URL` | No | `https://...` | Fallback only if API checkout creation is unavailable. |
| `ADMIN_API_KEY` or `CRON_SECRET` | Recommended | random secret | Protects `/api/admin/*` routes and Vercel Cron. |
| `OPS_ALERT_WEBHOOK_URL` | Recommended | `https://hooks.slack.com/...` | Receives high-priority stale-task alerts. |
| `REAP_STALE_MINUTES` | No | `45` | Stale task cutoff. |
| `REAP_ALERT_FAILURE_RATE_THRESHOLD` | No | `0.2` | Alert if stale reaps exceed 20% of daily tasks. |
| `RESEND_FROM_EMAIL` | Yes | `Sentinel AI <briefing@updates.example.com>` | Must use a verified Resend domain/subdomain. |

## Worker / Railway

| Variable | Required | Example | Notes |
| --- | --- | --- | --- |
| `WORKER_INTERNAL_TOKEN` | Yes | same as Vercel | Auth for internal analyze requests. |
| `WORKER_PUBLIC_URL` | Yes | `https://sentinel-worker.up.railway.app` | Used for poll and SSE URLs. |
| `NEXT_PUBLIC_WORKER_URL` | Optional | same as above | Optional fallback. |
| `RESEND_API_KEY` | Recommended | `re_xxx` | Required for real email delivery. |
| `RESEND_FROM_EMAIL` | Yes | `Sentinel AI <briefing@updates.example.com>` | Must match verified Resend domain. |
| `PYTHON_SKILL_DIR` | Yes | `./skills/xiangyu-finance-stock-analyzing/scripts/python` | Python analyzer location. |
| `PYTHON_EXECUTABLE` | No | `python` | Override if Railway image differs. |
| `PLAYWRIGHT_CHROMIUM_EXECUTABLE` | Optional | absolute path | Needed only if PDF generation cannot find Chromium automatically. |
| `FMP_API_KEY` | Recommended | rotated secret | Inject only the new rotated key. |
| `SEC_USER_AGENT` | Recommended | `Sentinel AI ops@example.com` | SEC requests should identify the service. |

## Go-Live Checks

1. Production Vercel must use live Lemon credentials and `LEMON_SQUEEZY_MODE=live`.
2. Production webhook secret must come from the live webhook, not the test webhook.
3. `WORKER_INTERNAL_TOKEN` and `INTERNAL_CALLBACK_SECRET` must be long random strings and must match across services.
4. `RESEND_FROM_EMAIL` must use a verified Resend sending domain.
5. Rotate any previously exposed `FMP_API_KEY` / `SEC_API_KEY` values before injection.
