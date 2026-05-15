# Growth OS API Key Checklist

This is the fill-in list for Sentinel AI phase-1 automated acquisition.
Do not commit real values. Put secrets in `.env.local`, Railway, Vercel, or the
target platform secret store.

## P0 - Needed To Run The First Stable Loop

| Area | Env vars | Why |
| --- | --- | --- |
| Public app URL | `GROWTH_OS_PUBLIC_URL` | Builds UTM CTA links in every social draft. |
| LLM composer | `ANTHROPIC_API_KEY` | Generates X / Reddit / Shorts / TikTok draft packs. |
| Database | `DATABASE_URL` | Stores visits, leads, KPI attribution. |
| Feishu app | `FEISHU_APP_ID`, `FEISHU_APP_SECRET` | Review Hub API access. |
| Feishu review | `FEISHU_REVIEW_CHAT_ID`, `FEISHU_BITABLE_APP_TOKEN`, `FEISHU_CONTENT_QUEUE_TABLE_ID`, `FEISHU_PERFORMANCE_TABLE_ID` | Draft review queue, publishing handoff, KPI digest. |
| X read | `X_BEARER_TOKEN` | Official X search/signal adapter. |
| X publish | `X_API_KEY`, `X_API_SECRET`, `X_ACCESS_TOKEN`, `X_ACCESS_TOKEN_SECRET` | Approved X text posts. Live only when `MARKETING_PUBLISH_DRY_RUN=false` and `X_DRY_RUN=false`. |
| Market data | `FMP_API_KEY`, `SEC_USER_AGENT` | Market movement + SEC fallback evidence. |
| X SERP fallback | `DATAFORSEO_LOGIN`, `DATAFORSEO_PASSWORD` | X/Google SERP signal when official X read is limited. |
| Web enrichment fallback | `TAVILY_API_KEY` | Secondary search/enrichment path. |
| YouTube research | `YOUTUBE_DATA_API_KEY` | Shorts/topic benchmark discovery. |

## P1 - Useful After The First Loop Works

| Area | Env vars | Why |
| --- | --- | --- |
| Telegram channel | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHANNEL_ID_PUBLIC`, `TELEGRAM_CHANNEL_HANDLE` | Public distribution channel and smoke tests. |
| Resend | `RESEND_API_KEY`, `RESEND_FROM_EMAIL` | Email daily radar and magic links. |
| SEC provider | `SEC_API_KEY` | Optional hosted SEC API path. |
| Media assets | `PEXELS_API_KEY` | Future Shorts/TikTok media asset sourcing. |
| Crawling/rerank | `JINA_API_KEY`, `FIRECRAWL_API_KEY`, `APIFY_API_TOKEN` | Future enrichment/scraping fallbacks. |
| TikTok intelligence | `TIKHUB_API_KEY` | Future TikTok trend adapter. |

## Phase-1 Runtime Switches

Keep publish dry-run until Feishu review, content quality, and attribution are
verified end to end.

```dotenv
MARKETING_DAILY_DRAFT_ENABLED=true
MARKETING_ALWAYS_ON_DRAFT_ENABLED=true
MARKETING_ALWAYS_ON_DRAFT_INTERVAL_MINUTES=180
MARKETING_QUEUE_POLL_ENABLED=true
MARKETING_QUEUE_POLL_INTERVAL_SECONDS=300
MARKETING_DAILY_DIGEST_ENABLED=true

MARKETING_PUBLISH_DRY_RUN=true
X_DRY_RUN=true
```

For X live cutover, flip both after a manual approved row succeeds in dry-run:

```dotenv
MARKETING_PUBLISH_DRY_RUN=false
X_DRY_RUN=false
```

## Preflight

After filling `.env.local`, run:

```powershell
worker/.venv/Scripts/python.exe scripts/marketing_deploy_preflight.py
```

The report prints `present` / `missing` only; it does not print secret values.
