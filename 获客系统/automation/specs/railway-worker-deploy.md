# Railway · Sentinel AI Worker Deploy Spec (Week 6)

> Long-running container that owns the Growth OS scheduler:
> review-queue poller (every 5 min) + daily growth digest (16:30 ET).
>
> Telegram is the only LIVE publisher in this phase. Everything else stays
> dry-run by design.

## 1. Railway service shape

| Setting | Value |
|---------|-------|
| Service type | Worker (not Web) — no HTTP port required for cron |
| Image | `worker/Dockerfile` |
| Start command | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` (keeps `/api/health` available for Railway probe) |
| Region | `us-east` (same coast as the NYSE; minor latency win on the 16:30 ET cron) |
| Always-on | yes |

The same image runs:

- the existing analyze worker (FastAPI app)
- the existing Telegram bot scheduler (if `BOT_ENABLED=true`)
- the new marketing schedulers (if `MARKETING_*` flags set)

There is no need for a separate Railway service.

## 2. Required env (Railway dashboard)

Variables are grouped by what they unlock. Copy into Railway, paste real values
(no quotes). Anything labelled "Yes" must be set before first deploy.

> **Copy-paste shortcut**: `获客系统/automation/specs/railway-env-template.md`
> has every variable pre-grouped with R/D/L/O tier markers, ready to paste
> into Railway dashboard → Variables.

### 2.1 Core infra (already in Week 0)

| Variable | Required | Notes |
|----------|----------|-------|
| `DATABASE_URL` | Yes | Supabase / Railway Postgres. Same DB Prisma migrates against. |
| `WORKER_INTERNAL_TOKEN` | Yes | Shared with Vercel. |
| `WORKER_PUBLIC_URL` | Yes | Railway-issued URL of this worker. |
| `WORKER_CORS_ALLOWED_ORIGINS` | Yes | Production Vercel origin. |
| `INTERNAL_CALLBACK_SECRET` | Yes | Existing — analyze callback auth. |
| `RESEND_API_KEY` + `RESEND_FROM_EMAIL` | Recommended | Magic-link + report email. |

### 2.2 Feishu Review Hub (Week 2)

| Variable | Required | Notes |
|----------|----------|-------|
| `FEISHU_REVIEW_ENABLED` | Recommended | `true` to soft-toggle feature in code (no-op without other Feishu vars). |
| `FEISHU_APP_ID` | Yes | App `sentinelai` — `cli_aa8bfc65417c1bdd`. |
| `FEISHU_APP_SECRET` | Yes | Never log this. |
| `FEISHU_REVIEW_CHAT_ID` | Yes | Production: `oc_7aea4cc3f3441ca7cc04b1b8f1839d13`. |
| `FEISHU_BITABLE_APP_TOKEN` | Yes | `I7X0bjghIaIrYtsfENHceXgfnAb` (already provisioned). |
| `FEISHU_CAMPAIGNS_TABLE_ID` | Yes | `tblwL5rGdEmzqCQA`. |
| `FEISHU_CONTENT_QUEUE_TABLE_ID` | Yes | `tblWeS9rb9UaeK32`. |
| `FEISHU_PERFORMANCE_TABLE_ID` | Yes | `tblpahcZSdQCDCw8`. |

### 2.3 LLM composer (Week 3)

| Variable | Required | Notes |
|----------|----------|-------|
| `ANTHROPIC_API_KEY` | Yes | Refusal-to-mock contract — daily draft job aborts without it. |
| `ANTHROPIC_BASE_URL` | Optional | Set when using a proxy (`https://code.newcli.com/claude/aws`). |
| `MARKETING_COMPOSER_MODEL` | Optional | Override `claude-sonnet-4-6` (e.g. `claude-sonnet-4-5` for proxies that only stock 4.5). |
| `GROWTH_OS_PUBLIC_URL` | Yes | The CTA hostname stamped into UTM links. Set to production Vercel origin. |

### 2.4 Telegram publisher (Week 4)

| Variable | Required | Notes |
|----------|----------|-------|
| `TELEGRAM_BOT_TOKEN` | Yes (existing) | Shared with the bot scheduler. |
| `TELEGRAM_CHANNEL_ID_PUBLIC` | Yes (live) | Numeric chat id `-100…`. Required when `MARKETING_PUBLISH_DRY_RUN=false`. |
| `TELEGRAM_CHANNEL_HANDLE` | Recommended | `@SentinelAI_signals`. Used to build `https://t.me/.../message_id` URLs. |
| `NEXT_PUBLIC_TELEGRAM_FREE_URL` | Recommended | Frontend secondary-CTA target. |

### 2.5 Marketing flags (master switches)

| Variable | Recommended initial | Notes |
|----------|---------------------|-------|
| `MARKETING_ENABLED` | `true` | Existing X-alert path; harmless if other X env unset. |
| `MARKETING_REVIEW_REQUIRED` | `true` | Hard-coded by Week 2 behavior; keep true. |
| `MARKETING_PUBLISH_DRY_RUN` | `true` | **Stays true until smoke OK.** Flip after dry-run validation. |
| `MARKETING_QUEUE_POLL_ENABLED` | `true` | Enables 5-min review-queue poller. |
| `MARKETING_QUEUE_POLL_INTERVAL_SECONDS` | `300` | 30s floor. |
| `MARKETING_DAILY_DRAFT_ENABLED` | `false` | Keep false until X-replacement scanner lands (currently uses suspended X bearer). |
| `MARKETING_DAILY_DIGEST_ENABLED` | `true` | Post-close KPI digest. |
| `MARKETING_DAILY_DIGEST_HOUR_ET` | `16` | 4 PM ET (post-close). |
| `MARKETING_DAILY_DIGEST_MINUTE_ET` | `30` | 30. |

### 2.6 X (read-only, currently SUSPENDED)

`X_BEARER_TOKEN` may stay in env as inactive — code paths short-circuit when
the token is invalid. Leave `MARKETING_DAILY_DRAFT_ENABLED=false` to avoid
attempting suspended-token searches.

## 3. Expected startup log on Railway

After deploy, the worker's first 30 lines of log should include:

```
[scanner] Pre-market at 09:00 ET (mon-fri)       # if SCANNER_ENABLED
[bot] public pre-market brief at 08:30 ET (mon-fri)   # if BOT_ENABLED
[marketing] X dispatch after Pre-market at 09:03 ET   # if MARKETING_ENABLED
[marketing] review-queue poller every 300s — Telegram publisher DRY-RUN (MARKETING_PUBLISH_DRY_RUN=true)
[marketing] daily growth digest at 16:30 ET (mon-fri)
```

The third-to-last line is the **Telegram publisher mode indicator** — confirm
it reads `DRY-RUN` for the first deploy. After validation, flip
`MARKETING_PUBLISH_DRY_RUN=false`, redeploy, and confirm the same log line
now says `LIVE`.

## 4. Preflight before flipping live

Run from a local machine with the same `.env.local` as Railway:

```powershell
worker/.venv/Scripts/python.exe scripts/marketing_deploy_preflight.py
```

All checks should return `PASS`. Then opt-in network sanity:

```powershell
# verify Feishu chat connectivity (sends a single dry-run text)
worker/.venv/Scripts/python.exe scripts/marketing_deploy_preflight.py --send-feishu-test

# verify Telegram bot has channel post permission (sends one dry-run text)
worker/.venv/Scripts/python.exe scripts/marketing_deploy_preflight.py --send-telegram-test
```

The Telegram test ALSO requires `MARKETING_PUBLISH_DRY_RUN=false` AND a
non-empty `TELEGRAM_CHANNEL_ID_PUBLIC` — otherwise it aborts before any
network call.

## 5. Pre-Live 9-Step Readiness Checklist (Week 7)

Run these in order from a developer machine with `.env.local` mirroring
Railway env. **Every step must pass before flipping `MARKETING_PUBLISH_DRY_RUN=false`.**

```text
1. Deploy preflight
   worker/.venv/Scripts/python.exe scripts/marketing_deploy_preflight.py
   → all checks PASS or WARN (no FAIL)

2. Browser QA against current deploy
   worker/.venv/Scripts/python.exe scripts/marketing_browser_check.py \
       --url ${GROWTH_OS_PUBLIC_URL}/stocks/NVDA --ticker NVDA
   worker/.venv/Scripts/python.exe scripts/marketing_browser_check.py \
       --url ${GROWTH_OS_PUBLIC_URL}/analysis/demo
   → both PASS (200, title, email gate, disclaimer)

3. Generate one fresh Telegram draft
   worker/.venv/Scripts/python.exe scripts/feishu/manual_brief.py --tickers NVDA
   → Feishu review chat receives green "Review Needed" card for CT-...-tg

4. Approve in Feishu Bitable (point-and-click in Content Queue)
   → review_status = Approved
   OR via CLI:
   worker/.venv/Scripts/python.exe scripts/feishu/set_record_status.py \
       --content-id CT-YYYYMMDD-NVDA-tg --status Approved

5. Run poller in DRY-RUN mode
   worker/.venv/Scripts/python.exe scripts/feishu/poll_review_status.py
   → Bitable row → Published with published_url=about:dryrun?…
   → review chat receives grey "Published (dry-run)" card

6. Browser QA the Feishu CTAs that just shipped
   worker/.venv/Scripts/python.exe scripts/marketing_browser_check.py \
       --from-feishu --limit 5 --notify-feishu
   → all rows PASS; summary card pushed to review chat

7. Flip the kill-switch (Railway dashboard)
   MARKETING_PUBLISH_DRY_RUN=false
   → Redeploy. Startup log line should now read:
   [marketing] review-queue poller every 300s — Telegram publisher LIVE
   (MARKETING_PUBLISH_DRY_RUN=false)

8. Repeat steps 3–5 with one fresh ticker
   → Telegram channel actually receives a post
   → Bitable published_url = https://t.me/{handle}/{message_id}
   → review chat shows blue "Published" card
   → Visit the CTA URL once manually; confirm VisitEvent row appears in Postgres

9. Next-day digest sanity
   worker/.venv/Scripts/python.exe scripts/feishu/push_daily_growth_digest.py
   → indigo "Daily Growth Digest" card appears with the new content_id
   → clicks ≥ 1, emails ≥ 0 (depending on landing-page traffic)
```

Any FAIL between steps 1-6 → fix it before step 7. After step 7, if anything
looks off, immediately flip `MARKETING_PUBLISH_DRY_RUN=true` and redeploy —
the next poller tick goes back to dry-run within 5 minutes.

### One-time Telegram prerequisite (before step 7 the FIRST time)

Add the `sentinelai` bot as **admin** of the public channel
(`@SentinelAI_signals`) with **Post Messages** permission. Verify via:

```powershell
worker/.venv/Scripts/python.exe scripts/marketing_deploy_preflight.py --send-telegram-test
```

→ `[PASS] telegram_test_message` (the channel receives a "preflight smoke"
test post). If FAIL, the bot is either not a member or lacks post permission.

## 6. Rollback

To stop all Growth OS jobs without losing other worker functionality:

```
MARKETING_QUEUE_POLL_ENABLED=false
MARKETING_DAILY_DIGEST_ENABLED=false
```

`SCANNER_ENABLED` and `BOT_ENABLED` keep your other scheduled jobs alive.

## 7. Manual fallback if scheduler ever fails

Every scheduled job has a CLI equivalent that can be run by hand:

| Cron job | Manual CLI |
|----------|-----------|
| `marketing-review-poller` | `scripts/feishu/poll_review_status.py` |
| `marketing-daily-digest` | `scripts/feishu/push_daily_growth_digest.py` |
| `marketing-daily-drafts` | `scripts/feishu/manual_brief.py --tickers …` |

Worker outage does not block growth ops — the chat-driven path stays usable
from any developer machine with `.env.local` synced.
