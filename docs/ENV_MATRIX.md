# Sentinel AI Production Env Matrix

> **Railway worker deploy**: see `获客系统/automation/specs/railway-worker-deploy.md`
> for the production checklist (env grouping, startup log expectations,
> dry-run → live cutover, rollback path).


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
| `WHOP_APP_ID` | Recommended | `app_xxx` | Whop app identifier. |
| `WHOP_API_KEY` | Yes | `whop_xxx` | Used for forum publisher and server-side Whop calls. |
| `WHOP_WEBHOOK_SECRET` | Yes | random secret | Secret configured on the Whop webhook. |
| `WHOP_PRODUCT_ID_PRO` | Yes | `prod_xxx` | Pro product id used to identify paid memberships. |
| `WHOP_PLAN_ID_PRO` | Yes | `plan_xxx` | Pro plan id used to identify paid memberships. |
| `WHOP_PRO_MONTHLY_PRICE_USD` | No | `39` | Used for MRR estimate in admin stats. |
| `NEXT_PUBLIC_WHOP_CHECKOUT_URL_PRO` | Yes | `https://whop.com/checkout/...` | Hosted Whop checkout URL. |
| `TELEGRAM_BOT_TOKEN` | Yes | `123:abc` | Used to issue VIP invite links after Whop activation. |
| `TELEGRAM_GROUP_ID_VIP` | Yes | `-100...` | VIP group id for one-time invite links. |
| `ADMIN_API_KEY` or `CRON_SECRET` | Recommended | random secret | Protects `/api/admin/*` routes and Vercel Cron. |
| `OPS_ALERT_WEBHOOK_URL` | Recommended | `https://hooks.slack.com/...` | Receives high-priority stale-task alerts. |
| `REAP_STALE_MINUTES` | No | `45` | Stale task cutoff. |
| `REAP_ALERT_FAILURE_RATE_THRESHOLD` | No | `0.2` | Alert if stale reaps exceed 20% of daily tasks. |
| `RESEND_FROM_EMAIL` | Yes | `Sentinel AI <noreply@mail.jilo.ai>` | Must use a verified Resend domain/subdomain (see `docs/RESEND_DNS.md`). |

## Worker / Railway

| Variable | Required | Example | Notes |
| --- | --- | --- | --- |
| `WORKER_INTERNAL_TOKEN` | Yes | same as Vercel | Auth for internal analyze requests. |
| `WORKER_PUBLIC_URL` | Yes | `https://sentinel-worker.up.railway.app` | Used for poll and SSE URLs. |
| `NEXT_PUBLIC_WORKER_URL` | Optional | same as above | Optional fallback. |
| `WORKER_CORS_ALLOWED_ORIGINS` | Yes | `https://sentinel.example.com` | Comma-separated frontend origins allowed to open worker SSE. |
| `RESEND_API_KEY` | Recommended | `re_xxx` | Required for real email delivery. |
| `RESEND_FROM_EMAIL` | Yes | `Sentinel AI <noreply@mail.jilo.ai>` | Must match verified Resend domain (see `docs/RESEND_DNS.md`). |
| `PYTHON_SKILL_DIR` | Yes | `./skills/xiangyu-finance-stock-analyzing/scripts/python` | Python analyzer location. |
| `PYTHON_EXECUTABLE` | No | `python` | Override if Railway image differs. |
| `PLAYWRIGHT_CHROMIUM_EXECUTABLE` | Optional | absolute path | Needed only if PDF generation cannot find Chromium automatically. |
| `FMP_API_KEY` | Recommended | rotated secret | Inject only the new rotated key. |
| `SEC_USER_AGENT` | Recommended | `Sentinel AI ops@example.com` | SEC requests should identify the service. |
| `DATABASE_URL` | Yes if bot enabled | `postgresql://...` | Required for Telegram profile, queue, and alert-log tables. |
| `TELEGRAM_BOT_TOKEN` | Yes if bot enabled | `123:abc` | Bot polling and public/private alert delivery. |
| `TELEGRAM_BOT_USERNAME` | Yes if bot enabled | `SentinelAIProChannelBot` | Used to build Telegram deep links. |
| `TELEGRAM_CHANNEL_ID_PUBLIC` or `TELEGRAM_CHANNEL_HANDLE` | Yes if public channel enabled | `@SentinelAI_signals` | Public channel target. |
| `TELEGRAM_GROUP_ID_VIP` | Yes if Whop VIP enabled | `-100...` | VIP group id. |
| `BOT_ENABLED` | No | `true` | Enables Telegram bot polling and bot scheduler jobs. |
| `BOT_POLLING_ENABLED` | No | `false` | Set `false` when another instance owns Telegram `getUpdates`; scheduled channel/email jobs still run via `BOT_ENABLED=true`. |
| `SCANNER_ENABLED` | No | `true` | Enables public movement scanner jobs. |
| `WHOP_API_KEY` | Yes if forum publisher enabled | `whop_xxx` | Whop forum post publisher. |
| `WHOP_FORUM_EXPERIENCE_ID` | Yes if forum publisher enabled | `exp_xxx` | Whop forum experience id. |
| `WHOP_COMPANY_ID` | Optional | `biz_xxx` | Passed to Whop SDK if required. |
| `MARKETING_ENABLED` | No | `true` | Registers `[marketing] X dispatch` cron jobs after each scanner session. |
| `MARKETING_SCORE_THRESHOLD` | No | `80` | Minimum signal score to publish on X (`signals.score_from_move`). |
| `MARKETING_SOURCE_LABEL` | No | `xtw` | Attribution tag written into deep-link payload (consumed by `signup_source`). |
| `BOT_USERNAME` | Yes if marketing enabled | `SentinelAIProChannelBot` | Telegram bot handle in deep-links; mirrors `TELEGRAM_BOT_USERNAME`. |
| `ANTHROPIC_API_KEY` | Yes if marketing enabled | `sk-ant-...` | Claude Sonnet 4.6 composer; falls back to Mock Mode without it. |
| `X_DRY_RUN` | No | `true` | When `false`, tweepy posts live via OAuth 1.0a User Context. |
| `X_API_KEY` | Yes for live posting | from developer.x.com | OAuth 1.0a Consumer Key (App permission must be Read+Write). |
| `X_API_SECRET` | Yes for live posting | from developer.x.com | OAuth 1.0a Consumer Secret. |
| `X_ACCESS_TOKEN` | Yes for live posting | from developer.x.com | OAuth 1.0a Access Token (per-account). |
| `X_ACCESS_TOKEN_SECRET` | Yes for live posting | from developer.x.com | OAuth 1.0a Access Token Secret. |
| `X_BEARER_TOKEN` | Optional | from developer.x.com | OAuth 2.0 App-only Bearer for read-only intel/search. |

## Growth OS · Conversion Foundation (Next.js)

| Variable | Required | Example | Notes |
| --- | --- | --- | --- |
| `GROWTH_OS_PUBLIC_URL` | Production REQUIRED | `https://sentinelai.com` | Public product origin used by marketing/email links. Worker refuses to start with `ENV=production` if missing or set to localhost. |
| `NEXT_PUBLIC_TELEGRAM_FREE_URL` | No | `https://t.me/SentinelAI_signals` | Secondary CTA target on stock and analysis pages. |

## Growth OS · Marketing X (Worker)

| Variable | Required | Example | Notes |
| --- | --- | --- | --- |
| `MARKETING_ENABLED` | No | `false` | Enables X dispatch cron jobs. |
| `MARKETING_REVIEW_REQUIRED` | No | `true` | Requires Feishu approval before publish. |
| `MARKETING_SCORE_THRESHOLD` | No | `80` | Minimum signal score to queue content. |
| `X_DRY_RUN` | No | `true` | Set `false` to enable live X posting. |
| `X_BEARER_TOKEN` | No | — | App-only read/search. |
| `X_API_KEY` | Yes (live) | — | OAuth 1.0a consumer key. |
| `X_API_SECRET` | Yes (live) | — | OAuth 1.0a consumer secret. |
| `X_ACCESS_TOKEN` | Yes (live) | — | OAuth 1.0a access token. |
| `X_ACCESS_TOKEN_SECRET` | Yes (live) | — | OAuth 1.0a access token secret. |

## Growth OS · Signal + Content Factory (Week 3 + 8.5 fallback)

Daily review-draft generation. Scheduler uses `America/New_York` (US stock
market local time) and runs Mon–Fri only — independent of host timezone.

| Variable | Required | Example | Notes |
| --- | --- | --- | --- |
| `MARKETING_DAILY_DRAFT_ENABLED` | No | `false` | Enables the 09:00 ET cron that scans + generates drafts. |
| `MARKETING_DAILY_DRAFT_HOUR_ET` | No | `9` | Hour-of-day in ET (0-23). Default 9 = pre-market. |
| `MARKETING_ALWAYS_ON_DRAFT_ENABLED` | No | `false` | Enables recurring Growth Content Pack generation for 24h social acquisition. Uses hour-level content ids to avoid overwriting daily drafts. |
| `MARKETING_ALWAYS_ON_DRAFT_INTERVAL_MINUTES` | No | `180` | Recurring draft cadence. Floor 60 minutes. |
| `MARKETING_ACQUISITION_OPERATOR_ENABLED` | No | `true` after local smoke | Enables the daily operator that generates Growth Content Pack drafts, Shorts/TikTok asset packs, and local run summaries. Keep `false` only while API keys are incomplete. |
| `MARKETING_ACQUISITION_OPERATOR_HOUR_ET` | No | `9` | Hour-of-day in ET (0-23). Runs at `:15` to avoid colliding with the draft cron. |
| `MARKETING_ACQUISITION_OPERATOR_OUTPUT_DIR` | No | `docs/growth-runs` | Local directory for `growth_run_summary.json`, review summaries, blocked items, next actions, and video packs. |
| `MARKETING_ACQUISITION_OPERATOR_KPI_LOOKBACK_DAYS` | No | `7` | KPI lookback window for Scale / Keep / Rewrite / Pause decisions. Min 1, max 30. |
| `MARKETING_TOP_OPPORTUNITIES_PER_DAY` | No | `5` | Cap on opportunities promoted to draft generation. |
| `MARKETING_MIN_OPPORTUNITY_SCORE` | No | `70` | Filter — only opportunities scoring ≥ this become drafts. |
| `ANTHROPIC_API_KEY` | Yes (drafts) | `sk-ant-...` | Required for live draft generation. **Mock content NEVER reaches Feishu** — if key is missing, the job aborts. |
| `MARKETING_COMPOSER_MODEL` | No | `claude-sonnet-4-6` | Override the Anthropic model used by `MultiPlatformComposer`. |
| `MARKETING_FALLBACK_API_KEY` | No | `sk-...` | **Toggles `FallbackComposer`.** Activates OpenAI-compatible fallback when primary is rate-limited. Fallback output still runs through redline + Feishu review. |
| `MARKETING_FALLBACK_BASE_URL` | No | `https://api.fox.com/v1` | OpenAI-Chat-Completions endpoint used by the fallback. Required when proxy is non-OpenAI. |
| `MARKETING_FALLBACK_MODEL` | No | `gpt-5.5` | Model name passed to the fallback chat-completions call. |
| `FMP_API_KEY` | No | rotated secret | Financial Modeling Prep — market movers / fundamentals. |
| `SEC_API_KEY` | No | — | SEC API filings provider (alternative to direct EDGAR). |
| `YOUTUBE_DATA_API_KEY` | No | — | Reserved for Week 4 YouTube adapter. |
| `TIKHUB_API_KEY` | No | — | Reserved for TikTok intel adapter. |
| `APIFY_API_TOKEN` | No | — | Reserved for Apify scraper adapter. |
| `TAVILY_API_KEY` | No | — | Reserved for Tavily web search enrichment. |
| `JINA_API_KEY` | No | — | Reserved for Jina reranker. |
| `DATAFORSEO_LOGIN` | No | — | Reserved for DataForSEO search rank. |
| `DATAFORSEO_PASSWORD` | No | — | Reserved for DataForSEO search rank. |
| `FIRECRAWL_API_KEY` | No | — | Reserved for Firecrawl scrape adapter. |
| `PEXELS_API_KEY` | No | — | Reserved for Shorts asset fetching. |

**This phase's required keys**: `ANTHROPIC_API_KEY` (drafts) + `X_BEARER_TOKEN`
(signal scan). Everything else is reserved env for future adapters and can
stay empty until needed.

## Growth OS · Publish Queue (Week 4)

Real-platform distribution. X and Telegram are live-capable in this phase.
Reddit / TikTok / YouTube / Email are not registered as publishers yet; if
approved, the poller marks them `Failed` with `missing_publisher:*` so they are
not mistaken for distributed content.

| Variable | Required | Example | Notes |
| --- | --- | --- | --- |
| `MARKETING_PUBLISH_DRY_RUN` | No | `true` | **Master kill-switch.** Defaults to `true` (safe). Set `false` to allow live-capable publishers to post. |
| `MARKETING_QUEUE_POLL_ENABLED` | No | `false` | When `true`, scheduler registers a poller every `MARKETING_QUEUE_POLL_INTERVAL_SECONDS`. |
| `MARKETING_QUEUE_POLL_INTERVAL_SECONDS` | No | `300` | Poll cadence. Floor 30s. Default 5 min. |
| `X_DRY_RUN` | No | `true` | X-specific kill-switch. X only posts live when `MARKETING_PUBLISH_DRY_RUN=false` AND `X_DRY_RUN=false`. |
| `X_API_KEY` / `X_API_SECRET` / `X_ACCESS_TOKEN` / `X_ACCESS_TOKEN_SECRET` | Yes (live X) | — | OAuth 1.0a User Context keys for approved X text posts. |
| `TELEGRAM_BOT_TOKEN` | Yes (live Telegram) | `123:abc` | Reuses existing bot token. |
| `TELEGRAM_CHANNEL_ID_PUBLIC` | Yes (live Telegram) | `-100...` | Numeric chat id — preferred over handle. |
| `TELEGRAM_CHANNEL_HANDLE` | No | `@SentinelAI_signals` | Used to build the `https://t.me/.../message_id` URL written back to Bitable. Falls back if `TELEGRAM_CHANNEL_ID_PUBLIC` is unset. |

**Activation checklist (Telegram live)**:

1. Set `TELEGRAM_BOT_TOKEN` (already in repo).
2. Set `TELEGRAM_CHANNEL_ID_PUBLIC` AND/OR `TELEGRAM_CHANNEL_HANDLE`.
3. Add the bot as an admin of the channel with **Post Messages** permission.
4. Set `MARKETING_PUBLISH_DRY_RUN=false`.
5. Optionally enable `MARKETING_QUEUE_POLL_ENABLED=true` so the worker polls every 5 min instead of needing manual `scripts/feishu/poll_review_status.py`.

## Growth OS · Market Intelligence Layer (Week 6 / 8.5)

Data source adapters for `worker/app/marketing/intelligence.py::build_daily_profiles`.
Each adapter handles its own key check. **All keys are optional in this phase**
— missing keys lower `sources_used` in the profile but never abort the run.

**FMP adapter (Week 8.5 update)**: uses `/stable/*` exclusively (the legacy
`/api/v3/*` paths were deprecated by FMP on 2025-08-31). Quote enrichment
issues one HTTP call per ticker because the free tier returns HTTP 402 on
batch (`/stable/quote?symbol=A,B,C`). `build_daily_profiles` now invokes
`fetch_quotes_for_tickers(tickers)` instead of `fetch_market_movers(limit=…)`.

| Variable | Priority | Adapter | Notes |
| --- | --- | --- | --- |
| `FMP_API_KEY` | P0 | `data_sources/fmp.py` | Per-ticker `/stable/quote`. Free tier (250 calls/day) is plenty for the default 5-ticker seed. |
| `SEC_API_KEY` | P0 | `data_sources/sec_api.py` | sec-api.io path. Falls back to in-repo EDGAR scraper when missing. |
| `SEC_USER_AGENT` | P0 | EDGAR fallback | Existing env; SEC requires UA on every request. |
| `DATAFORSEO_LOGIN` + `DATAFORSEO_PASSWORD` | P0 | `data_sources/x_serp.py` | Primary X SERP query path — bypasses suspended official X API. |
| `TAVILY_API_KEY` | P0 | `data_sources/x_serp.py` + `enrichment.py` | Secondary X SERP path; also powers URL summarization. |
| `YOUTUBE_DATA_API_KEY` | P0 | `data_sources/youtube.py` | YouTube search.list for competitor benchmarks. Quota-aware (capped at 5 tickers/run). |
| `JINA_API_KEY` | P1 | reserved | Future fallback reader. |
| `FIRECRAWL_API_KEY` | P1 | reserved | Future fallback crawler. |
| `APIFY_API_TOKEN` | P1 | reserved | Future X actor fallback. |
| `TIKHUB_API_KEY` | P1 | reserved | Future TikTok intelligence. |
| `PEXELS_API_KEY` | P1 | reserved | Future Shorts asset fetcher. |

**Recommended minimum for production**: `FMP_API_KEY` + (`DATAFORSEO_LOGIN`+`DATAFORSEO_PASSWORD`) + `YOUTUBE_DATA_API_KEY`. Everything else is layered enrichment.

**Manual smoke** (any time):
```powershell
worker/.venv/Scripts/python.exe scripts/marketing_intelligence_smoke.py
worker/.venv/Scripts/python.exe scripts/marketing_intelligence_smoke.py --tickers NVDA TSLA --json
worker/.venv/Scripts/python.exe scripts/marketing_intelligence_smoke.py --no-external   # offline
```

## Growth OS · KPI Aggregator + Daily Digest (Week 5)

Reads from Postgres (`DATABASE_URL`) + writes Feishu Performance + sends a
digest card. Runs at `MARKETING_DAILY_DIGEST_HOUR_ET:MINUTE_ET` America/New_York
on Mon-Fri.

| Variable | Required | Example | Notes |
| --- | --- | --- | --- |
| `MARKETING_DAILY_DIGEST_ENABLED` | No | `false` | scheduler registers the digest cron. |
| `MARKETING_DAILY_DIGEST_HOUR_ET` | No | `16` | Default 16 = 4 PM ET (post-close). |
| `MARKETING_DAILY_DIGEST_MINUTE_ET` | No | `30` | Default 30. |
| `DATABASE_URL` | Yes | postgres://… | Existing — KPI reads VisitEvent / EmailLead / SubscriptionStatus. |
| `FEISHU_PERFORMANCE_TABLE_ID` | Yes | `tbl…` | Existing — upsert keyed by `content_id`. |
| `FEISHU_CONTENT_QUEUE_TABLE_ID` | Yes | `tbl…` | Existing — scanned for Pending / Blocked counts. |

**Manual run** (any time):
```powershell
worker/.venv/Scripts/python.exe scripts/feishu/push_daily_growth_digest.py
```

**Schema dependencies**: requires Prisma `VisitEvent.utmContent`,
`EmailLead.utmContent`, `EmailLead.verifiedAt`, `EmailLead.userId`,
`SubscriptionStatus.plan`, `SubscriptionStatus.state` — all already present.

## Growth OS · Email Daily Radar (Worker)

Free-tier email digest. Scans `EmailLead.verifiedAt IS NOT NULL`, renders
the `free_email_daily` template (anomaly / nothing branch), and sends via
Resend. **Default-off**; safety guards layered so a single env flip cannot
trigger bulk live email.

| Variable | Required | Example | Notes |
| --- | --- | --- | --- |
| `MARKETING_EMAIL_DAILY_ENABLED` | No | `false` | Master switch. When `true`, scheduler registers the cron — but the job itself still respects `DRY_RUN` + `ALLOW_BULK` below. |
| `MARKETING_EMAIL_DAILY_DRY_RUN` | No | `true` | When `true` (default) the cron renders payloads + logs subject/preview but does NOT POST to Resend. |
| `MARKETING_EMAIL_DAILY_HOUR_ET` | No | `7` | Hour-of-day in ET (0-23). Default `7` = pre-market. |
| `MARKETING_EMAIL_DAILY_MINUTE_ET` | No | `0` | Minute-of-hour (0-59). Default `0`. |
| `MARKETING_EMAIL_DAILY_LIMIT` | No | `50` | Max verified leads scanned per cron firing. Caps blast radius until ramp-up. |
| `MARKETING_EMAIL_DAILY_ALLOW_BULK` | No | `false` | Second key for bulk live send. The cron refuses to fan out unless this is `true` AND `DRY_RUN` is `false`. |
| `RESEND_API_KEY` | Yes (live) | `re_xxx` | Reused from §Worker. Missing key forces dry-run. |
| `RESEND_FROM_EMAIL` | Yes (live) | `Sentinel AI <noreply@mail.jilo.ai>` | Reused. Must be a verified Resend sender (see `docs/RESEND_DNS.md`). |

**Manual smoke** (single recipient — preferred for verification):

```powershell
worker/.venv/Scripts/python.exe scripts/marketing_send_email_digest.py \
    --live --only-email 372768498@qq.com
```

Dry-run (no Resend traffic), one recipient:

```powershell
worker/.venv/Scripts/python.exe scripts/marketing_send_email_digest.py \
    --only-email 372768498@qq.com
```

Dry-run over the next 50 verified leads (renders only, no send):

```powershell
worker/.venv/Scripts/python.exe scripts/marketing_send_email_digest.py --limit 50
```

Bulk live (requires three explicit flags as a "are you sure" check):

```powershell
worker/.venv/Scripts/python.exe scripts/marketing_send_email_digest.py \
    --live --allow-bulk --confirm-bulk --limit 50
```

The job never touches `MARKETING_PUBLISH_DRY_RUN` (Telegram kill-switch),
never publishes to Telegram or X, and never bypasses Feishu review.

## Growth OS · Feishu Review Hub (Week 2)

| Variable | Required | Example | Notes |
| --- | --- | --- | --- |
| `FEISHU_REVIEW_ENABLED` | No | `false` | Enables Feishu review pipeline. |
| `FEISHU_APP_ID` | Yes (Feishu) | `cli_xxx` | Self-built app identifier (open.feishu.cn). |
| `FEISHU_APP_SECRET` | Yes (Feishu) | — | Self-built app secret. Never log or print. |
| `FEISHU_REVIEW_CHAT_ID` | Yes (Feishu) | `oc_xxx` | Target chat ID for OpenAPI `im/v1/messages` push. |
| `FEISHU_BOT_WEBHOOK_URL` | No | `https://open.feishu.cn/.../hook/...` | Optional custom-bot webhook. When set, `feishu_client.send_text` skips OpenAPI. |
| `FEISHU_BOT_SIGN_SECRET` | No | — | Optional HMAC signing for custom-bot webhook. |
| `FEISHU_BITABLE_APP_TOKEN` | Yes (Feishu) | — | Bitable app token for Content Queue. |
| `FEISHU_CAMPAIGNS_TABLE_ID` | Yes (Feishu) | — | Campaigns table ID. |
| `FEISHU_CONTENT_QUEUE_TABLE_ID` | Yes (Feishu) | — | Content Queue table ID. |
| `FEISHU_PERFORMANCE_TABLE_ID` | Yes (Feishu) | — | Performance KPI table ID. |

## Go-Live Checks

1. Production Vercel must use live Whop credentials and the live Whop checkout URL.
2. Production webhook secret must come from the live Whop webhook.
3. `WORKER_INTERNAL_TOKEN` and `INTERNAL_CALLBACK_SECRET` must be long random strings and must match across services.
4. `RESEND_FROM_EMAIL` must use a verified Resend sending domain.
5. Rotate any previously exposed `FMP_API_KEY` / `SEC_API_KEY` values before injection.
