# marketing — Sentinel X Acquisition Pipeline

> Pipeline: `scanner.TickerMove` → `signals.score_from_move` → gate → `Composer` (Claude Sonnet 4.6) → `redline.scan` → `XClient.post` → bot deep-link

## Modules

| File | Role |
|---|---|
| `redline.py` | Brand red-line scanner — every post must pass before publish |
| `personas.py` | 3 source-cited personas (SEC Filing Reporter / Risk Watchdog / Market Calendar) |
| `signals.py` | abs(change_pct) → 0-100 score, piecewise-linear curve |
| `tracker.py` | Telegram bot deep-link payload encode/decode (aligned with `bot/handlers/onboarding.py:START_PAYLOAD_RE`) |
| `composer.py` | Claude Sonnet 4.6 wrapper with prompt cache + redline retry + Mock Mode |
| `x_client.py` | `tweepy` wrapper — OAuth 1.0a for posting + Bearer for read; default `dry_run=True` |
| `intel.py` | Read-only X search (uses Bearer Token); surfaces $TICKER buzz + KOL candidates |
| `publisher.py` | Orchestrator — Composer + XClient + Tracker into one `publish_alert()` |
| `jobs.py` | APScheduler entry: `publish_marketing_alerts(session_label)` |

## Env vars

| Var | Used by | Default |
|---|---|---|
| `MARKETING_ENABLED` | scheduler.py — registers the cron job | unset → off |
| `MARKETING_SCORE_THRESHOLD` | jobs.py — gate score | `80` |
| `MARKETING_SOURCE_LABEL` | jobs.py — attribution label | `xtw` |
| `BOT_USERNAME` | jobs.py — deep-link domain | `SentinelAIProChannelBot` |
| `ANTHROPIC_API_KEY` | composer.py — leaves Mock Mode | unset → mock template |
| `X_DRY_RUN` | x_client.py — flip live posting | `true` |
| `X_API_KEY` / `X_API_SECRET` / `X_ACCESS_TOKEN` / `X_ACCESS_TOKEN_SECRET` | OAuth 1.0a — posting | required for live |
| `X_BEARER_TOKEN` | OAuth 2.0 App-only — read/search | optional (intel only) |

## Tests

```bash
cd worker
.venv/Scripts/python.exe -m pytest tests/ -v
# 41/41 PASS expected
```

## Activation checklist (operator)

1. **Set ANTHROPIC_API_KEY** in `.env.local` → Composer leaves Mock Mode.
2. **Set X OAuth 1.0a keys** at [developer.x.com](https://developer.x.com/en/portal/dashboard):
   - App permissions = Read and write
   - Generate / copy: API Key, API Secret, Access Token, Access Token Secret
   - Paste into `.env.local` as `X_API_KEY` / `X_API_SECRET` / `X_ACCESS_TOKEN` / `X_ACCESS_TOKEN_SECRET`
3. **One-shot activation**:
   ```bash
   python scripts/marketing_activate.py
   # validates Claude + 4 OAuth keys, sends 1 test tweet (opt-in)
   ```
4. **Flip live in `.env.local`**:
   ```dotenv
   MARKETING_ENABLED=true
   X_DRY_RUN=false
   MARKETING_SCORE_THRESHOLD=80
   ```
5. **Restart worker**. Scheduler logs `[marketing] X dispatch after Pre-market at 09:03 ET (mon-fri)`.
6. **Verify attribution**: when a deep-link click lands on the bot, `telegram_bot_profile.signup_source/_campaign/_ticker` populate via `bot/handlers/onboarding.py:_parse_start_payload`.

## Deep-link payload format

`{src_}{source}_score{N}_{ticker}_{YYYYMMDD}` — example: `src_xtw_score92_aapl_20260509`

Decoded by bot:
- `signup_source` = "xtw" (X/Twitter)
- `signup_campaign` = "score92"
- `signup_ticker` = "AAPL"
- `signup_payload_raw` = full string

## Brand red lines (enforced in `redline.py`)

- ❌ buy / sell / price target / predict / trading signal / yolo / 100x / pump / dump / "go long"/"go short" etc.
- ✅ Must contain at least one `https://` source URL
- ✅ Must end with: `Context, not advice.` / `Not investment advice.` / `Not financial advice.`

Mirrors README:281 enforcement.

## OG card endpoint

`GET /api/og/{ticker}?variant={x_post|reddit_card|telegram_inline}` — Next.js public route at `app/api/og/[ticker]/route.tsx`. Use for media uploads when X media support is added to `XClient`.

| Variant | Dimensions | Use |
|---|---|---|
| `x_post` (default) | 1200×675 | X feed card (16:9) |
| `reddit_card` | 1200×630 | Reddit thumbnail |
| `telegram_inline` | 800×418 | Telegram link preview |
