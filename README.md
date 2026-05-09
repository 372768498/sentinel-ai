# Sentinel AI

> **Never miss the moment that matters.**
> A watchlist sentinel for self-directed US-equity investors. Quiet until something material crosses your line.

[sentinel.jilo.ai](https://sentinel.jilo.ai) · [@SentinelAI_signals](https://t.me/SentinelAI_signals) (public) · [@SentinelAIProChannelBot](https://t.me/SentinelAIProChannelBot) (Pro)

---

## What Sentinel AI is — and isn't

**Is**
- A *quiet* alerting service: only pings when your tickers cross thresholds you set
- A *contextual* assistant: every alert links to a primary source (SEC EDGAR, Reuters, Fed)
- A *bidirectional* bot: ask "What about TSLA?" and get the current state, not a prediction

**Is not**
- A signal group (no buy/sell calls)
- A 24/7 chat noise machine (silence is a feature)
- A predictive AI (we cite sources, not forecasts)

The brand redline: **never tell users what to buy/sell, never predict prices, always cite primary sources.** Enforced in code via red-line scans on every message template.

---

## Architecture

```
┌─────────────────┐       ┌──────────────────┐       ┌──────────────┐
│   Next.js 14    │◄─────►│  FastAPI Worker  │◄─────►│  PostgreSQL  │
│   (frontend +   │       │   (Python 3.12)  │       │  (Prisma +   │
│    Whop hooks)  │       │                  │       │   asyncpg)   │
└─────────────────┘       └──────────────────┘       └──────────────┘
                                   │
                          ┌────────┼────────┐
                          ▼        ▼        ▼
                     ┌────────┐ ┌────┐ ┌──────┐
                     │Telegram│ │Whop│ │  yf  │
                     │  Bot   │ │API │ │market│
                     └────────┘ └────┘ └──────┘
```

- **Next.js 14 (App Router)** — landing page, Whop checkout, webhooks
- **FastAPI worker** — scanner, scheduler, Telegram bot polling, Whop publisher
- **PostgreSQL** — Prisma-managed user/subscription tables + bot-managed profile/alert tables
- **Telegram bot (PTB v22)** — polling mode, embedded in FastAPI lifespan
- **Whop SDK** — Pro subscription gating, VIP group access, daily forum posts
- **APScheduler** — ET-aware cron in `America/New_York` (handles DST automatically)

---

## Features

### 1. Public channel ([@SentinelAI_signals](https://t.me/SentinelAI_signals))

Daily content for the open community:

| Time (ET, Mon–Fri) | Content |
|---|---|
| 08:30 | Pre-market brief (active or quiet) |
| 16:30 | Post-close digest |

NYSE-aware — skips weekends and US market holidays via `pandas_market_calendars`.

### 2. Whop forum (Pro feed)

One auto-published post per US trading day at 16:45 ET. Five rotating content types:

| Day | Template | Source |
|---|---|---|
| Monday | Week-ahead preview | Static (calendar) |
| Tuesday | Yesterday's catch | `alert_log` (yesterday's window) |
| Wednesday | Behind-the-scenes scanner stats | `alert_log` (today) |
| Thursday | Education (rotating by ISO week) | `whop_education_posts.py` (5 entries) |
| Friday | Week-in-review | `alert_log` (Mon–Fri aggregate) |

### 3. VIP Pro user DMs

After a user joins the VIP Telegram group via Whop, the bot sends a Welcome with a deep-link button, then runs a 3-step DM onboarding:

1. **Tickers** — type freely or tap `Use sample (5 tickers)`
2. **Threshold** — default ±2% or customize 0.5–10%
3. **Quiet hours** — e.g. 22:00–07:00 ET (alerts queued during quiet, drained when window opens)

Personal data persists in `telegram_bot_profile`. Onboarding can be cancelled any time via `/cancel` or the inline ❌ Cancel button.

### 4. Real-time personal alerts

Three times per trading day (09:02 / 12:32 / 16:32 ET) the bot dispatches per-user alerts:

- Per-ticker change checked against each user's threshold
- **30-minute dedup** by `(user, ticker, direction)` to prevent duplicate alerts
- **Quiet-hours queuing** — alerts during muted windows persist in `queued_alerts` and drain every 2 minutes once the window closes
- **Batch aggregation** — if ≥3 tickers cross simultaneously for one user, send one batch message instead of N individual ones

Every successful delivery logs to `alert_log` for the Whop publisher's recap data.

### 5. Conversational interface

In the Pro DM users can:

| Input | Bot response |
|---|---|
| `/watchlist` | Dashboard with tickers, threshold, status + Add/Remove/Threshold/Quiet inline buttons |
| `/threshold all 1.5` | Update alert threshold |
| `/snooze 2` | Pause alerts for N hours |
| `/help` | Command summary |
| `What about TSLA?` | Live yfinance data + threshold status + catalyst summary |
| `Why no alert on NVDA?` | Same handler — explains if the move stayed under threshold |

Free-text matching uses keyword + standalone-uppercase recognition (e.g. won't trigger on "Hello world"). Implementation in `worker/app/bot/handlers/messages.py`.

### 6. Operator broadcast endpoint

`POST /api/bot/push-alert` (internal-token protected) — used during the public-test period to manually broadcast caught-moment alerts before the auto-pipeline is fully trusted.

```json
{
  "ticker": "TSLA",
  "headline": "8-K filed: material asset write-down",
  "detail": "Tesla disclosed...",
  "source_url": "https://www.sec.gov/...",
  "change_pct": -4.5,
  "target": "watchers"
}
```

`target=all` sends to every active VIP; `target=watchers` only to users with the ticker in their watchlist.

### 7. Alert priority tier

Each alert carries one of three priority levels for future critical-alert routing:

| Priority | Trigger | Behavior |
|---|---|---|
| `normal` | Default threshold cross | Standard DM |
| `urgent` | Move ≥5% or large earnings miss | Standard DM (visual: same; metadata flagged) |
| `critical` | Fed emergency, halt, delisting, VIX spike | Reserved `should_call=True` for future Twilio integration |

Today every priority sends with `disable_notification=False`. The metadata is in place for a future "Pro Plus" tier with phone escalation.

---

## Tech stack

| Layer | Tools |
|---|---|
| **Frontend** | Next.js 14, TypeScript, Tailwind, Prisma client |
| **Backend** | FastAPI, Python 3.12, httpx, Pydantic |
| **Bot** | python-telegram-bot v22 (polling) |
| **Scheduler** | APScheduler (timezone-aware) |
| **Calendar** | pandas_market_calendars (NYSE) |
| **DB** | PostgreSQL 16 (via Docker for local), Prisma + asyncpg |
| **Market data** | yfinance |
| **Subscription** | Whop SDK (Pro tier, VIP group access, forum posts) |
| **Email** | Resend (mock-mode fallback if no API key) |
| **PDF reports** | Playwright headless Chromium |

---

## Local development

### Prerequisites

- Node.js 24+ / npm 11+
- Python 3.12+
- Docker Desktop (for PostgreSQL)

### One-time setup

```powershell
cd D:\code2026\sentinel-ai
copy .env.example .env.local
# Fill in keys: TELEGRAM_BOT_TOKEN, WHOP_API_KEY, DATABASE_URL, etc.

# Start Postgres
docker compose up -d postgres
npm run prisma:migrate -- --name init

# Install Python deps into worker venv
cd worker
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
# (or use uv: uv pip install --python .venv/Scripts/python.exe -r requirements.txt)
```

### Run the stack

In separate terminals:

```powershell
# Terminal 1: Next.js
npm run dev          # → http://localhost:3000

# Terminal 2: Worker (with bot polling enabled)
cd worker
$env:BOT_ENABLED="true"
.\.venv\Scripts\uvicorn.exe app.main:app --port 18000 --reload
```

### Self-test

```powershell
cd D:\code2026\sentinel-ai
python -m worker.app.bot.e2e_test
```

Runs 7 steps covering timezone correctness, red-line template scans (Telegram + Whop), quiet-hours logic, ticker-query regex, priority classification, DB CRUD, and full alert dispatch (with mocked sender). Skips DB-dependent steps gracefully if Postgres isn't running. Current target: **21/21 PASS**.

---

## Repository layout

```
sentinel-ai/
├── app/                              # Next.js 14 App Router
│   ├── api/
│   │   ├── analyze/                  # Stock analysis endpoint
│   │   ├── webhooks/whop/            # Whop subscription events
│   │   └── checkout/                 # Whop checkout init
│   ├── page.tsx                      # Landing
│   └── layout.tsx
├── lib/
│   ├── whop.ts                       # Whop SDK wrapper
│   ├── telegram.ts                   # VIP group invite/kick
│   ├── prisma.ts
│   └── env.ts
├── prisma/
│   ├── schema.prisma                 # Users, subscriptions, analysis history
│   └── migrations/
├── worker/                           # FastAPI Python worker
│   ├── app/
│   │   ├── main.py                   # FastAPI app + lifespan
│   │   ├── scheduler.py              # APScheduler jobs (ET-aware)
│   │   ├── scanner.py                # Movement scanner (yfinance)
│   │   ├── runner.py                 # Analysis job orchestrator
│   │   ├── telegram.py               # Public-channel sender (httpx)
│   │   └── bot/                      # Telegram bot
│   │       ├── bot.py                # Application factory + lifecycle
│   │       ├── db.py                 # asyncpg layer (4 tables)
│   │       ├── alerter.py            # Personal alerts + dedup + queue + batch
│   │       ├── digest.py             # EOD digests (public + per-user)
│   │       ├── whop_publisher.py     # Whop daily forum post
│   │       ├── tz_check.py           # Timezone diagnostics
│   │       ├── market_calendar.py    # NYSE trading day check
│   │       ├── e2e_test.py           # Self-test runner (21/21)
│   │       ├── handlers/
│   │       │   ├── welcome.py        # Group join → welcome + deep link
│   │       │   ├── onboarding.py     # 3-step ConversationHandler
│   │       │   ├── commands.py       # /watchlist /threshold /snooze /help
│   │       │   └── messages.py       # "What about X?" handler
│   │       └── templates/
│   │           ├── telegram_messages.py     # 7 alert + onboarding templates
│   │           ├── whop_post_templates.py   # 4 dynamic forum templates
│   │           ├── whop_education_posts.py  # 5 Thursday education posts
│   │           └── callback_actions.py      # Inline button callback constants
│   ├── HANDOVER_v2.md                # Sprint 1 detailed handover
│   └── requirements.txt
├── skills/
│   └── xiangyu-finance-stock-analyzing/  # Stock analysis Python skill
└── docker-compose.yml
```

---

## Bot DB tables (created automatically by `worker/app/bot/db.py`)

| Table | Purpose |
|---|---|
| `telegram_bot_profile` | One row per Pro user — watchlist, threshold, quiet hours, onboarding state |
| `alert_cooldown` | Per-(user, ticker, direction) 30-min cooldown for dedup |
| `queued_alerts` | Alerts deferred during quiet hours; drained every 2 min |
| `alert_log` | Permanent record of every delivered alert (powers Whop weekly recap) |

These live alongside the Prisma-managed schema; no migration tooling required.

---

## Brand red lines (enforced in code)

1. **Never imply buy/sell.** Templates that contain `"buy"` / `"sell"` / `"price target"` / `"predict"` / `"trading signal"` fail e2e step 2 + step 2b.
2. **Always disclaimer.** Every alert template ends with `Context, not advice.` or `Your call. Not advice.`
3. **Source > prediction.** Source URL required for factual claims; templates without one don't pass review.
4. **Quiet day = post anyway.** Static silence is the differentiator — both Telegram public channel and Whop publisher have `silence_day` / `quiet_day` fallback templates.

---

## Status (2026-05-08)

| Feature | Status |
|---|---|
| Telegram bot (polling, 4 capabilities) | ✅ Live, 21/21 self-test PASS |
| Personal alert dispatch (dedup + quiet + batch) | ✅ Live |
| Public channel scheduled briefs | ✅ Live |
| Whop daily forum publisher | ✅ Code complete, awaiting Whop `forum:post:create` permission approval |
| Manual broadcast endpoint | ✅ Live |
| Production cloud deploy | ⏳ Pending (≥5 paying users) |
| Twilio critical-alert escalation | ⏳ Pending (≥50 paying users) |

See [`worker/HANDOVER_v2.md`](worker/HANDOVER_v2.md) for the detailed Sprint 1 handover.

---

## License

Private — All rights reserved.
