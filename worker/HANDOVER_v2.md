# Sentinel AI Bot — Handover v2

**Date:** 2026-05-08  
**Covers:** Timezone fix, personal real-time alerts, end-to-end self-test

---

## 1. Timezone Fix

### Audit scope

| File | Finding | Fix |
|------|---------|-----|
| `worker/app/scheduler.py` | All CronTriggers already used `"America/New_York"` | Confirmed OK; APScheduler handles DST automatically |
| `worker/app/bot/market_calendar.py` | `today_et()` uses `ZoneInfo("America/New_York")` | Confirmed OK |
| `worker/app/bot/digest.py` | Used `today_et()` throughout | Confirmed OK |
| `worker/app/bot/templates/telegram_messages.py` | `datetime.now()` (naive) for timestamps in templates | Fixed: added `_et_now_str()` using `ZoneInfo("America/New_York")` |
| Quiet hours check | Logic existed but no ET-aware time helper | Added `is_quiet_time()` and `now_et()` to `tz_check.py` |
| All DB timestamps | Stored as `TIMESTAMPTZ` (UTC) | Correct — displayed to users via `et_display()` in ET |

### New: `worker/app/bot/tz_check.py`

Key functions:
- `now_et()` — current time in `America/New_York`
- `is_quiet_time(enabled, start_hour, end_hour)` — ET-aware, handles midnight-crossing windows
- `et_display(dt)` — formats datetime as `"21:57 ET May 07"` for user-facing messages
- `verify_timezones(scheduler)` — prints all job next_run_times in ET on startup

### verify_timezones() sample output (run 2026-05-07 21:57 ET)

```
================================================================
TIMEZONE CHECK
  UTC:          2026-05-08 01:57:19 UTC
  ET (NYSE):    2026-05-07 21:57:19 EDT  <- all jobs use this
  Server local: 2026-05-08 09:57:19      (reference only, Beijing GMT+8)
  DST active:   True
  Scheduled jobs:
    [scan-pre-market]           next: 2026-05-08 09:00 EDT
    [scan-mid-day]              next: 2026-05-08 12:30 EDT
    [scan-post-close]           next: 2026-05-08 16:30 EDT
    [brief-premarket-public]    next: 2026-05-08 08:30 EDT
    [digest-postclose-public]   next: 2026-05-08 16:30 EDT
    [alerts-personal-pre-market] next: 2026-05-08 09:02 EDT
    [alerts-personal-mid-day]   next: 2026-05-08 12:32 EDT
    [alerts-personal-post-close] next: 2026-05-08 16:32 EDT
    [digest-postclose-personal] next: 2026-05-08 16:35 EDT
    [queued-alerts-processor]   next: 2026-05-07 21:59 EDT
================================================================
```

---

## 2. Personal Real-Time Alerts

### New file: `worker/app/bot/alerter.py`

**Core function:** `dispatch_personal_alerts(session_label, sender=None)`

Flow:
1. Load all active profiles from `telegram_bot_profile`
2. Collect unique tickers across all users
3. Batch-fetch prices via `scanner.fetch_watchlist_moves()` (one yfinance call for all tickers)
4. For each user: find crossings vs their `alert_threshold`
5. For each crossing: check cooldown (30-min dedup) → check quiet hours → send or queue

**Alert storm prevention (batch aggregation):**  
If a user has ≥ 3 crossings at once → send 1 `threshold_crossed_batch` message instead of N individual messages.

### New DB tables

```sql
-- 30-minute dedup per (user, ticker, direction)
CREATE TABLE alert_cooldown (
    telegram_user_id BIGINT  NOT NULL,
    ticker           TEXT    NOT NULL,
    direction        CHAR(1) NOT NULL,  -- '+' or '-'
    triggered_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (telegram_user_id, ticker, direction)
);

-- Quiet-hours queue
CREATE TABLE queued_alerts (
    id               SERIAL PRIMARY KEY,
    telegram_user_id BIGINT NOT NULL,
    ticker           TEXT   NOT NULL,
    payload_json     JSONB  NOT NULL,
    queued_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    sent_at          TIMESTAMPTZ          -- NULL = unsent
);
```

Tables are created automatically on first `get_pool()` call. No migration needed.

### Scheduler jobs added

| Job ID | Schedule | Purpose |
|--------|----------|---------|
| `alerts-personal-pre-market` | 09:02 ET Mon-Fri | Personal alerts after 9 AM scan |
| `alerts-personal-mid-day` | 12:32 ET Mon-Fri | Personal alerts after 12:30 scan |
| `alerts-personal-post-close` | 16:32 ET Mon-Fri | Personal alerts after 4:30 scan |
| `queued-alerts-processor` | Every 2 min | Drain quiet-hours queue for users now out of quiet |

### Dedup logic

- Key: `(telegram_user_id, ticker, direction)` where direction = `+` or `-`
- Window: 30 minutes (configurable via `COOLDOWN_MINUTES` in `db.py`)
- A reversal (e.g., +2.5% → later -2.5%) bypasses the cooldown (different direction)

---

## 3. e2e_test.py Full Output

Run command: `cd D:/code2026/sentinel-ai && python -m worker.app.bot.e2e_test`

```
================================================================
SENTINEL AI BOT - END-TO-END SELF-TEST
================================================================

=== STEP 1: Timezone check ===
  UTC:   2026-05-08 01:57:19 UTC
  ET:    2026-05-07 21:57:19 EDT  (offset -4h)
  DST:   yes (EDT, UTC-4)
  et_display(): 21:57 ET May 07
  [PASS] ET timezone is correct (America/New_York with DST handling)
  [PASS] ET offset -4h is valid (EDT=-4 / EST=-5)

=== STEP 2: Red-line scan on all templates ===
  [PASS] All 18 templates pass red-line check -- no buy/sell/prediction language
  [PASS] All alert templates contain disclaimer (Context/Your call, not advice)

=== STEP 3: Quiet hours logic (ET-aware) ===
  [PASS] Midnight-crossing window (22-7) logic correct
  [PASS] Same-day window (1-6) logic correct
  [PASS] Disabled quiet hours always returns False
  [PASS] All 24 hours correctly classified for 22:00-07:00 window

=== STEP 4: 'What about X?' handler regex ===
  [PASS] All 7 query patterns correctly classified

=== STEP 5: DB -- onboarding write + read ===
  [PASS] Upsert profile wrote to DB
  [PASS] Read back: watchlist=['NVDA', 'AAPL', 'TSLA'], threshold=0.01

=== STEP 6: Alert dispatch + dedup + quiet-hours queuing ===
  [PASS] Immediate send: 1 alert dispatched (msg captured: 1)
  [PASS] Dedup: same ticker+direction within 30 min correctly suppressed
  [PASS] Quiet hours: alert correctly queued, not sent immediately
  [PASS] Queued alert in DB: id=1, ticker=NVDA
  [PASS] Batch aggregation: 4 crossings -> 1 message (not 4 separate alerts)
  [PASS] Test user cleaned up from DB

================================================================
RESULTS: 17/17 passed  |  0 failed  |  0 skipped
ALL TESTS PASSED [OK]
================================================================
```

---

## 4. Real-User Verification (mock alerts sent)

Three mock alert templates sent to VIP group to verify HTML rendering and Telegram delivery:

| Message | msg_id | Content |
|---------|--------|---------|
| Mock threshold_crossed (single) | 16 | NVDA +2.5% alert, HTML bold/links correct |
| Mock threshold_crossed_batch (4 tickers) | 17 | 4-ticker aggregated alert, sorted by abs(pct) |
| Mock silence_day | 18 | Quiet day digest, watchlist listed |

Sent at: `21:57 ET May 07` (confirmed correct ET timestamp)

**Real personal DM test** requires user to:
1. Send `/start` to `@SentinelAIProChannelBot` → complete onboarding
2. Set watchlist with a low threshold (e.g., `/threshold all 0.5`)
3. Wait for a scan run, or run: `curl -X POST http://localhost:8000/api/scan/run?session_label=Test`

---

## 5. Known Remaining Issues

1. **Bot requires Docker running**: `telegram_bot_profile` etc. live in the Dockerized Postgres. If Docker is stopped, the bot degrades gracefully (logs error, FastAPI still works) but won't store profiles.

2. **No per-ticker threshold**: Currently `alert_threshold` is one value applied to all tickers in a user's watchlist. Per-ticker thresholds are not stored (would need schema change + UI for `/threshold TSLA 3`). The command `/threshold TSLA 3` currently sets the global threshold.

3. **yfinance ticker validation is slow**: 3-5s per 5 tickers during onboarding. Acceptable for v1 but noticeable if users add large watchlists.

4. **Live caught moment still manual**: As agreed — not automated. Operator sends via Telegram manually or via a future `/api/bot/push-alert` internal endpoint.

5. **Polling → Webhook migration needed for Railway/Fly.io**: Current polling mode works locally. When deploying to cloud, switch to webhook mode (set `BOT_WEBHOOK_URL` env var and add a FastAPI endpoint to receive updates). The Application object is already wired to support this.

---

## 6. Next Steps (Recommended)

1. **Real user onboarding**: Have at least one VIP user complete the 3-step onboarding to populate `telegram_bot_profile` with real data, then trigger a manual scan to verify personal DMs arrive.

2. **Per-ticker thresholds (v2)**: Store `{ticker: threshold}` JSON in the profile instead of a single float.

3. **Live caught moment API**: Add `POST /api/bot/push-alert` (internal token required) that takes `{ticker, headline, change_pct, source_url, users: "all"|"watchlist"}` and dispatches to relevant users.

4. **Webhook mode**: Before Railway/Fly.io deploy, switch from polling to webhook. PTB v21 supports this cleanly.

5. **Redis context persistence**: Optional v2 upgrade — persist ConversationHandler state to Redis so in-progress onboardings survive worker restarts.
