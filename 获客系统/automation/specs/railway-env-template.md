# Railway Env Template · Sentinel AI Worker (Week 8)

> Copy-paste ready. Drop these into Railway dashboard → Variables.
> **All values blank below** — fill from `.env.local` (already gitignored).
> **NEVER commit real keys into this file.**
>
> Companion checklist: `railway-worker-deploy.md` §2 (variable purpose) + §5
> (9-step pre-live verification). Reference matrix: `docs/ENV_MATRIX.md`.

Markers:
- **R** = Required for first deploy (worker won't start cleanly without it)
- **D** = Required for Dry-run mode (default phase)
- **L** = Required only when flipping `MARKETING_PUBLISH_DRY_RUN=false` (LIVE)
- **O** = Optional / future adapter — fine to leave empty

---

## §1 Core Worker (R)

These mirror existing Vercel↔Worker shared secrets. **Do not regenerate** —
must match what Vercel has, otherwise analyze callbacks break.

```dotenv
DATABASE_URL=
WORKER_INTERNAL_TOKEN=
WORKER_PUBLIC_URL=
WORKER_CORS_ALLOWED_ORIGINS=
INTERNAL_CALLBACK_SECRET=
```

| Var | Tier | Note |
|-----|------|------|
| `DATABASE_URL` | R | Same Postgres Prisma migrates against |
| `WORKER_INTERNAL_TOKEN` | R | Match Vercel exactly |
| `WORKER_PUBLIC_URL` | R | Railway-issued URL of this worker |
| `WORKER_CORS_ALLOWED_ORIGINS` | R | Production Vercel origin |
| `INTERNAL_CALLBACK_SECRET` | R | Analyze callback auth |

## §2 Feishu Review Hub (R)

```dotenv
FEISHU_REVIEW_ENABLED=true
FEISHU_APP_ID=
FEISHU_APP_SECRET=
FEISHU_REVIEW_CHAT_ID=oc_7aea4cc3f3441ca7cc04b1b8f1839d13
FEISHU_BITABLE_APP_TOKEN=
FEISHU_CAMPAIGNS_TABLE_ID=
FEISHU_CONTENT_QUEUE_TABLE_ID=
FEISHU_PERFORMANCE_TABLE_ID=
```

Production constants (already provisioned):
- `FEISHU_REVIEW_CHAT_ID=oc_7aea4cc3f3441ca7cc04b1b8f1839d13`
- `FEISHU_BITABLE_APP_TOKEN=I7X0bjghIaIrYtsfENHceXgfnAb`
- `FEISHU_CAMPAIGNS_TABLE_ID=tblwL5rGdEmzqCQA`
- `FEISHU_CONTENT_QUEUE_TABLE_ID=tblWeS9rb9UaeK32`
- `FEISHU_PERFORMANCE_TABLE_ID=tblpahcZSdQCDCw8`

## §3 LLM Composer (R for daily-draft; D for manual_brief)

```dotenv
ANTHROPIC_API_KEY=
ANTHROPIC_BASE_URL=
MARKETING_COMPOSER_MODEL=
GROWTH_OS_PUBLIC_URL=

# OpenAI-compatible fallback composer (Week 8.5)
# Activates automatically when MARKETING_FALLBACK_API_KEY is set.
# Used only when the primary (Anthropic) composer raises a rate-limit error;
# every fallback output still goes through redline scan + Feishu review.
MARKETING_FALLBACK_API_KEY=
MARKETING_FALLBACK_BASE_URL=
MARKETING_FALLBACK_MODEL=
```

| Var | Tier | Note |
|-----|------|------|
| `ANTHROPIC_API_KEY` | R | content_factory refuses to run without it (no mock to Feishu) |
| `ANTHROPIC_BASE_URL` | O | Proxy override (e.g. `https://code.newcli.com/claude/aws`) |
| `MARKETING_COMPOSER_MODEL` | O | Override default `claude-sonnet-4-6` (e.g. `claude-sonnet-4-5` for proxies) |
| `GROWTH_OS_PUBLIC_URL` | R | Hostname stamped into CTA UTM links — set to production Vercel origin |
| `MARKETING_FALLBACK_API_KEY` | O | Presence of this key toggles `FallbackComposer`. Leave blank to disable fallback. |
| `MARKETING_FALLBACK_BASE_URL` | O | OpenAI-Chat-Completions endpoint (e.g. fox / OpenRouter / vLLM). Required when proxy is non-OpenAI. |
| `MARKETING_FALLBACK_MODEL` | O | Override default `gpt-5.5` (e.g. `gpt-4o-mini`, `gpt-4.1`). |

**Fallback contract** (`worker/app/marketing/content_factory.py:FallbackComposer`):
- Triggered ONLY on `anthropic.RateLimitError` / `APIStatusError(429)` / message
  containing "rate limit" / "too many requests" / "请求过于频繁". Other errors
  propagate from primary — fallback never masks real bugs.
- Output is still scanned by `redline.scan(require_source, require_disclaimer)`.
- Output is still submitted to Feishu Content Queue for human approval.
- There is **no `_ENABLED=true` flag** — env-key presence is the toggle.

## §4 Telegram Publisher (D for dry-run, L for live)

```dotenv
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHANNEL_ID_PUBLIC=
TELEGRAM_CHANNEL_HANDLE=@SentinelAI_signals
NEXT_PUBLIC_TELEGRAM_FREE_URL=https://t.me/SentinelAI_signals
```

| Var | Tier | Note |
|-----|------|------|
| `TELEGRAM_BOT_TOKEN` | D | Reuse bot scheduler's existing token |
| `TELEGRAM_CHANNEL_ID_PUBLIC` | L | Numeric `-100…` chat id — required for live posting |
| `TELEGRAM_CHANNEL_HANDLE` | D | Used to build `https://t.me/handle/message_id` URLs |
| `NEXT_PUBLIC_TELEGRAM_FREE_URL` | D | Frontend secondary-CTA target |

## §5 Marketing Master Flags (Week 8 Dry-Run Defaults)

```dotenv
MARKETING_ENABLED=true
MARKETING_REVIEW_REQUIRED=true
MARKETING_PUBLISH_DRY_RUN=true
MARKETING_QUEUE_POLL_ENABLED=true
MARKETING_QUEUE_POLL_INTERVAL_SECONDS=300
MARKETING_DAILY_DIGEST_ENABLED=true
MARKETING_DAILY_DIGEST_HOUR_ET=16
MARKETING_DAILY_DIGEST_MINUTE_ET=30
MARKETING_DAILY_DRAFT_ENABLED=false
MARKETING_ACQUISITION_OPERATOR_ENABLED=true
MARKETING_ACQUISITION_OPERATOR_HOUR_ET=9
MARKETING_ACQUISITION_OPERATOR_OUTPUT_DIR=docs/growth-runs
MARKETING_ACQUISITION_OPERATOR_KPI_LOOKBACK_DAYS=7

# Content & Notification optimization wire-up (Sprint 1, Telegram only)
USE_NEW_TEMPLATES=false
```

| Var | Week 8 value | Tier | Note |
|-----|--------------|------|------|
| `MARKETING_ENABLED` | `true` | D | Enables existing X-alert path (no-op without X creds) |
| `MARKETING_REVIEW_REQUIRED` | `true` | D | Hard-coded Week 2 contract |
| `MARKETING_PUBLISH_DRY_RUN` | **`true`** | D | **DO NOT FLIP YET.** Stays true through Week 8 |
| `MARKETING_QUEUE_POLL_ENABLED` | `true` | D | 5-min cron that consumes Approved Bitable rows |
| `MARKETING_QUEUE_POLL_INTERVAL_SECONDS` | `300` | D | Floor 30s, default 5 min |
| `MARKETING_DAILY_DIGEST_ENABLED` | `true` | D | 16:30 ET post-close digest |
| `MARKETING_DAILY_DIGEST_HOUR_ET` | `16` | D | ET hour 0-23 |
| `MARKETING_DAILY_DIGEST_MINUTE_ET` | `30` | D | |
| `MARKETING_DAILY_DRAFT_ENABLED` | **`false`** | O | Leave off — depends on X scanner which is currently SUSPENDED |
| `MARKETING_ACQUISITION_OPERATOR_ENABLED` | **`true`** | O | Daily CEO-operator layer. Generates review drafts, Shorts/TikTok asset packs, blocked-item reports, and next actions. If API keys are incomplete, keep false until `scripts/run_acquisition_operator.py --fixture` and a real Feishu dry-run pass. |
| `MARKETING_ACQUISITION_OPERATOR_HOUR_ET` | `9` | O | Runs at `:15` ET when enabled. |
| `MARKETING_ACQUISITION_OPERATOR_OUTPUT_DIR` | `docs/growth-runs` | O | Artifact directory for operator summaries and video packs. |
| `MARKETING_ACQUISITION_OPERATOR_KPI_LOOKBACK_DAYS` | `7` | O | KPI lookback window for Scale / Keep / Rewrite / Pause decisions. Min 1, max 30. |
| `USE_NEW_TEMPLATES` | **`false`** | O | Sprint 1 wire-up flag. When `true`, free Telegram drafts come from the deterministic `free_telegram_anomaly` template (no LLM call). X and YouTube Shorts always use the LLM. Run `scripts/preview_new_templates.py` before flipping; expect 7-day gray-out under `MARKETING_PUBLISH_DRY_RUN=true` before promoting to live posts. |

## §6 Market Intelligence Layer P0 (O — none required for Week 8)

```dotenv
FMP_API_KEY=
SEC_API_KEY=
SEC_USER_AGENT=Sentinel AI ops@yourdomain.com
DATAFORSEO_LOGIN=
DATAFORSEO_PASSWORD=
TAVILY_API_KEY=
YOUTUBE_DATA_API_KEY=
```

All optional in Week 8 dry-run. The Intelligence Layer has graceful fallback —
missing keys lower `sources_used` in profiles but never abort the run.

**FMP usage notes (Week 8.5)**:
- FMP deprecated `/api/v3/*` on 2025-08-31. The adapter now uses `/stable/*`
  exclusively (`/stable/biggest-gainers`, `/stable/biggest-losers`,
  `/stable/most-actives`, `/stable/quote`).
- FMP free tier returns **HTTP 402 on batch quote** (`/stable/quote?symbol=A,B,C`).
  `intelligence.build_daily_profiles` now drives FMP via
  `fetch_quotes_for_tickers` which issues one request **per ticker** (5/day
  on the default seed list ≈ 5/250 daily quota — well under the free tier cap).
- Missing key → adapter returns `[]` silently; HTTP 402/403/non-200 → logged
  warning then `[]`. Never raises.

Recommended Phase 9 minimum (after first live Telegram post):
`FMP_API_KEY` + `DATAFORSEO_LOGIN`+`DATAFORSEO_PASSWORD` + `YOUTUBE_DATA_API_KEY`.

## §7 Intelligence P1 / Reserved (L — future adapters)

```dotenv
JINA_API_KEY=
FIRECRAWL_API_KEY=
APIFY_API_TOKEN=
TIKHUB_API_KEY=
PEXELS_API_KEY=
```

Adapters exist in code as interface stubs; not wired this phase.

## §8 X Official API (currently SUSPENDED, leave blank)

```dotenv
X_BEARER_TOKEN=
X_API_KEY=
X_API_SECRET=
X_ACCESS_TOKEN=
X_ACCESS_TOKEN_SECRET=
X_DRY_RUN=true
```

The previously-registered X app `2024701919781146624miao33kv` is SUSPENDED.
Free tier `search/recent` is not sufficient anyway. Leave blank, keep
`X_DRY_RUN=true` so any orphan code path stays safe.

## §9 Bot / Scanner (D — reuse existing config)

```dotenv
BOT_ENABLED=true
SCANNER_ENABLED=true
TELEGRAM_BOT_USERNAME=SentinelAIProChannelBot
TELEGRAM_CHANNEL_HANDLE=@SentinelAI_signals
TELEGRAM_GROUP_ID_VIP=
WHOP_API_KEY=
WHOP_FORUM_EXPERIENCE_ID=
WHOP_COMPANY_ID=
```

These keep the existing analyze/bot/whop schedulers alive. Disable any of
them only if you intentionally want to stop that subsystem on Railway.

## §10 Resend (D — magic links + report emails)

```dotenv
RESEND_API_KEY=
RESEND_FROM_EMAIL=Sentinel AI <briefing@yourdomain.com>
```

Required for the Week 1 conversion funnel (magic-link email after capture).

---

## Bulk apply checklist

After pasting variables into Railway:

1. **Mark sensitive vars as Sealed** in Railway UI: `FEISHU_APP_SECRET`,
   `ANTHROPIC_API_KEY`, `WORKER_INTERNAL_TOKEN`, `INTERNAL_CALLBACK_SECRET`,
   `WHOP_API_KEY`, `RESEND_API_KEY`, `TELEGRAM_BOT_TOKEN`.
2. **Trigger redeploy** so new vars take effect.
3. **Tail Railway logs**, expect the following lines within 60s:
   ```
   [marketing] X dispatch after Pre-market at 09:03 ET (mon-fri)
   [marketing] review-queue poller every 300s — Telegram publisher DRY-RUN (MARKETING_PUBLISH_DRY_RUN=true)
   [marketing] daily growth digest at 16:30 ET (mon-fri)
   ```
4. **Run post-deploy smoke**: see `railway-post-deploy-smoke.md`.
