# Sentinel AI Go-Live Smoke Test

## 1. Infra

1. Open `GET /api/admin/stats` with `Authorization: Bearer <ADMIN_API_KEY>` and confirm a JSON response.
2. Open Railway worker `GET /api/health` and confirm `{ "status": "ok" }`.
3. Confirm Prisma can read/write production `DATABASE_URL`.

## 2. Basic Analyze Flow

1. Submit a basic analysis with a new free email.
2. Confirm `/api/analyze` returns `200` with `jobId`, `eventsUrl`, `pollUrl`, and quota usage.
3. Confirm SSE logs stream from the worker.
4. Confirm callback updates `analysisHistory.status` to `COMPLETED`.
5. Confirm email is delivered through Resend and not left in mock mode.

## 3. Pro Upgrade Flow

1. Submit a deep analysis using a free account.
2. Confirm `/api/analyze` returns `403` with `upgradeRequired: true`.
3. Confirm the frontend redirects to the Whop hosted Pro checkout.
4. Complete checkout with the live Pro plan.
5. Confirm Whop webhook arrives at `/api/webhooks/whop`.
6. Confirm `subscriptionStatus.plan=PRO` and `subscriptionStatus.state=ACTIVE`.
7. Confirm a single-use Telegram VIP invite link is stored on the subscription.
8. Re-run deep analysis and confirm it starts successfully.

## 4. Webhook Mode Transition

1. Ensure Vercel production env sets live `WHOP_*` values.
2. Ensure checkout redirects to `NEXT_PUBLIC_WHOP_CHECKOUT_URL_PRO`.
3. Ensure the production webhook in Whop uses the live `WHOP_WEBHOOK_SECRET`.
4. Send a signed Whop webhook fixture and confirm signature verification passes.
5. Confirm the subscription is synced and the Telegram invite is issued on first activation.

## 5. Reaper And Alerting

1. Create or backfill a stale `QUEUED` or `RUNNING` analysis older than `REAP_STALE_MINUTES`.
2. Call `POST /api/admin/reap` with admin auth.
3. Confirm stale tasks are marked `FAILED` with `[STALE_REAP]` prefix.
4. If stale reaps exceed the configured daily threshold, confirm an ops alert is emitted.

## 6. Social Preview

1. Call `GET /api/admin/generate-preview/NVDA`.
2. Confirm a 1200x630 image is returned.
3. Confirm the image shows ticker, score, rating, recommendation, and updated timestamp.

## 7. Growth OS · Conversion Foundation (Week 1)

> **Status (2026-05-13)**: LIVE with real brand sender `Sentinel AI <noreply@mail.jilo.ai>`. Resend domain `mail.jilo.ai` is Verified — magic-link emails can land in any inbox (no sandbox cap). See `docs/RESEND_DNS.md` for the DNS records.

1. Visit `/stocks/NVDA?utm_source=test&utm_campaign=smoke&utm_content=manual`.
2. Confirm score card renders with rating word (STRONG / SOLID / NEUTRAL / CAUTION / WEAK).
3. Submit email through the gate. Confirm `EmailLead` row created with the UTM fields populated.
4. Confirm magic-link email arrives via Resend with `From: Sentinel AI <noreply@mail.jilo.ai>`.
5. Click magic link → confirm redirect to `/stocks/NVDA?verified=1` and `EmailLead.verifiedAt` set.
6. Confirm `VisitEvent` row written for the page visit with matching UTM tags.

## 8. Growth OS · Review Hub (Week 2)

Prereq: `FEISHU_APP_ID` / `FEISHU_APP_SECRET` / `FEISHU_REVIEW_CHAT_ID` /
`FEISHU_BITABLE_APP_TOKEN` / `FEISHU_CONTENT_QUEUE_TABLE_ID` set in `.env.local`.

```powershell
worker/.venv/Scripts/python.exe scripts/feishu/push_test_message.py
```

Expected: `[ok] response: {'code': 0, ...}` and the review chat receives a
plain test message.

## 9. Growth OS · Content Factory (Week 3 + 8.5 fallback)

Prereq: `ANTHROPIC_API_KEY` (+ optional `ANTHROPIC_BASE_URL` /
`MARKETING_COMPOSER_MODEL`).

Optional fallback: set `MARKETING_FALLBACK_API_KEY` (+ `MARKETING_FALLBACK_BASE_URL`
+ `MARKETING_FALLBACK_MODEL`) to wire `FallbackComposer`. The wrapper only
delegates to the OpenAI-compatible fallback when the primary raises a
rate-limit error — fallback output still passes through redline and Feishu
review.

```powershell
worker/.venv/Scripts/python.exe scripts/feishu/manual_brief.py --tickers NVDA
```

Expected:
- Three Feishu review cards appear (`-x`, `-tg`, `-yt`).
- Console reports `opportunities=1 drafts_created=3 submitted_to_review=3`.

## 10. Growth OS · Telegram Publish Loop (Week 4)

After Step 9 (a Telegram draft exists in Bitable):

```powershell
# Mark Telegram draft Approved
worker/.venv/Scripts/python.exe scripts/feishu/set_record_status.py \
    --content-id CT-YYYYMMDD-NVDA-tg --status Approved

# Trigger poller (dry-run by default)
worker/.venv/Scripts/python.exe scripts/feishu/poll_review_status.py
```

Dry-run expected: Bitable row → Published, `published_url=about:dryrun?...`,
review group receives a **grey "Published (dry-run)"** card.

Live (after Telegram channel admin granted + `MARKETING_PUBLISH_DRY_RUN=false`):
- Telegram channel receives the actual post.
- Bitable `published_url=https://t.me/{handle}/{message_id}`.
- Review group receives a **blue "Published"** card.

## 11. Growth OS · KPI Digest (Week 5)

```powershell
worker/.venv/Scripts/python.exe scripts/feishu/push_daily_growth_digest.py
```

Expected:
- Console: `[digest] rollups=N upserted=N pending_review=N blocked_by_redline=N`.
- Feishu Performance table has one row per `content_id` with `as of YYYY-MM-DD ET` note.
- Review group receives an **indigo "Daily Growth Digest"** card with Top 3 content.

## 12. Growth OS · Deployment Preflight (Week 6)

```powershell
worker/.venv/Scripts/python.exe scripts/marketing_deploy_preflight.py
```

Every check should be `PASS`. With `--send-feishu-test` or
`--send-telegram-test`, the script also fires a single live test message
(requires `MARKETING_PUBLISH_DRY_RUN=false` for Telegram).

## 13. Growth OS · Browser QA Harness (Week 7)

Verifies that CTA landing pages are rendering correctly **before** any
Telegram message goes live.

```powershell
# Single URL
worker/.venv/Scripts/python.exe scripts/marketing_browser_check.py \
    --url ${GROWTH_OS_PUBLIC_URL}/stocks/NVDA --ticker NVDA

# Pull recent Content Queue rows + check each cta_url
worker/.venv/Scripts/python.exe scripts/marketing_browser_check.py --from-feishu --limit 10

# Same + post a QA summary card to the Feishu review chat
worker/.venv/Scripts/python.exe scripts/marketing_browser_check.py --from-feishu --notify-feishu
```

Expected per-page checks: `http_ok` · `has_title` · `ticker_reference` ·
`email_gate` · `disclaimer` · (optional) `telegram_cta`.

Screenshots default to
`获客系统/automation/browser-qa/screenshots/` (gitignored).

## 14. Growth OS · Pre-Live 9-Step Checklist (Week 7)

See `获客系统/automation/specs/railway-worker-deploy.md` §5 for the
authoritative 9-step pre-live checklist. Run in order:

1. `marketing_deploy_preflight.py` — all PASS / WARN
2. `marketing_browser_check.py --url …/stocks/NVDA` — PASS
3. `manual_brief.py --tickers NVDA` — Feishu green card appears
4. Approve in Bitable (point-and-click) or via `set_record_status.py`
5. `poll_review_status.py` (dry-run) — grey "Published (dry-run)" card
6. `marketing_browser_check.py --from-feishu --notify-feishu` — all PASS
7. Flip `MARKETING_PUBLISH_DRY_RUN=false` on Railway
8. Re-run steps 3–5 with a fresh ticker; verify Telegram channel receives the post
9. Next day: `push_daily_growth_digest.py` — digest card shows ≥ 1 click

## 15. Production Go-Live Flags (delivery switches)

> **Why this section exists**: 2026-05-26 incident — Free Telegram channel and
> daily email radar silently stopped after deploy because the Railway env was
> left in "review-only" mode from initial provisioning. `railway_push_env.sh`
> used to hardcode the safety defaults; production go-live now requires an
> explicit second step (this section).

### Flags that gate user-facing delivery

| Flag | Review-only | Live |
|------|-------------|------|
| `BOT_ENABLED` | `false` | `true` |
| `BOT_POLLING_ENABLED` | `false` | `true` |
| `MARKETING_EMAIL_DAILY_ENABLED` | `false` | `true` |
| `MARKETING_EMAIL_DAILY_DRY_RUN` | `true` | `false` |
| `MARKETING_DAILY_DIGEST_ENABLED` | `false` | `true` |
| `MARKETING_DAILY_DRAFT_ENABLED` | `false` | `true` |

If any of these stays in the review-only column after deploy, the scheduler
registers the cron but `digest.publish_*` / `email_daily.run_once` short-circuit
before calling Telegram / Resend. **No alert fires** — the worker logs
look healthy.

### Go-live procedure

1. **Pre-check Railway credit balance.** Hobby plan = $5/mo credit. With both
   `sentinel-ai` worker + Postgres running, ~14 days of runway. If
   `railway status` shows `<$3` remaining, top up or migrate before flipping
   flags — Postgres auto-pauses when credits hit $0 and the worker starts
   throwing `connection reset` errors.
2. **Flip the flags** (idempotent):
   ```bash
   bash scripts/railway_go_live_flags.sh
   ```
3. **Redeploy the worker** so APScheduler re-registers jobs with the new env:
   ```bash
   railway redeploy --service sentinel-ai
   ```
4. **Verify the scheduler picked it up.** Tail logs and confirm these lines
   appear at startup:
   ```
   [bot] enabled — registering digest jobs (premarket / midday / eod)
   [marketing] email daily radar at 08:15 ET (mon-fri) — dry_run=false
   ```
5. **Manual smoke ping** (optional but recommended):
   ```bash
   railway run --service sentinel-ai \
     worker/.venv/Scripts/python.exe -c \
     "import asyncio; from app.bot.digest import public_premarket_brief; asyncio.run(public_premarket_brief())"
   ```
   Expected: a message lands in `@SentinelAI_signals`.

### Rollback to review-only mode

During an incident or before a risky change:

```bash
bash scripts/railway_go_live_flags.sh --off
railway redeploy --service sentinel-ai
```

### What `railway_push_env.sh` does and does NOT touch

`scripts/railway_push_env.sh` provisions secrets + safe defaults only. It will
NOT overwrite the flags in the table above — those are owned exclusively by
`railway_go_live_flags.sh`. Safe to re-run `railway_push_env.sh` against a live
service without flipping delivery off.
