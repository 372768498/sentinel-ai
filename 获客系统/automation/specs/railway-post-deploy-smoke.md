# Railway Post-Deploy Smoke (Week 8)

> Verify the worker is alive, the scheduler is registered, and the
> Approved → Published pipeline works end-to-end **in dry-run mode**.
>
> No live Telegram traffic in this phase. Live cutover is a separate
> step (`railway-worker-deploy.md` §5 step 7).

Companion docs:
- Variable groupings: `railway-env-template.md`
- Pre-deploy checklist: `railway-worker-deploy.md` §5 (steps 1-6)
- Local smoke flows: `docs/SMOKETEST.md` §13-14

---

## Step 1 · Confirm scheduler registration in Railway logs

Open Railway → service → **Logs** tab. Within ~60s of deploy:

```text
[scanner] Pre-market at 09:00 ET (mon-fri)            # (1) if SCANNER_ENABLED=true
[bot] public pre-market brief at 08:30 ET (mon-fri)   # (2) if BOT_ENABLED=true
[marketing] X dispatch after Pre-market at 09:03 ET   # (3) if MARKETING_ENABLED=true
[marketing] review-queue poller every 300s — Telegram publisher DRY-RUN (MARKETING_PUBLISH_DRY_RUN=true)
[marketing] daily growth digest at 16:30 ET (mon-fri)
```

**Required lines for Week 8**: (4) review-queue poller and (5) daily growth
digest. The other three are pre-existing schedulers and only appear if their
gating env is true.

If line (4) does NOT contain `DRY-RUN`, your `MARKETING_PUBLISH_DRY_RUN` is
not `true` — fix before any draft enters the queue. Live cutover is
intentional, not accidental.

## Step 2 · Generate a fresh draft

From a local machine (or Railway SSH if you've set one up):

```powershell
worker/.venv/Scripts/python.exe scripts/feishu/manual_brief.py --tickers NVDA
```

Expected:
- Console: `opportunities=1 drafts_created=3 submitted_to_review=3 skipped=0`
- Feishu review chat receives **three green "Review Needed" cards**
  (`-x`, `-tg`, `-yt` content_ids).

## Step 3 · Approve the Telegram draft

Two options — both work, pick one:

**A. In the Bitable UI**: open Content Queue → find row
`CT-YYYYMMDD-NVDA-tg` → click `review_status` cell → select `Approved` →
auto-save.

**B. Via CLI** (faster for smoke):

```powershell
worker/.venv/Scripts/python.exe scripts/feishu/set_record_status.py `
    --content-id CT-YYYYMMDD-NVDA-tg --status Approved
```

Console: `[ok] recXXXXXX review_status = Approved`.

## Step 4 · Trigger the poller

The Railway worker polls automatically every 5 min, but for smoke you can
force-trigger now:

```powershell
worker/.venv/Scripts/python.exe scripts/feishu/poll_review_status.py
```

Expected:
- Console: `[scan] Approved-not-published: 1 → [dry-run] CT-…-tg (Telegram, $NVDA) → about:dryrun?…`
- Bitable Content Queue row → `review_status=Published`, `published_url=about:dryrun?platform=Telegram&content_id=…`
- Feishu review chat receives a **grey "Sentinel AI · Published (dry-run)" card**.

Wait ≥ 5 min and check Railway logs for the next scheduled poller tick:

```text
[review_poller] tick start — publishers=Telegram dry_run=True notify_chat=True
[review_poller] tick done — scanned=0 processed=0 failed=0 errors=0
```

The 0 / 0 / 0 / 0 confirms idempotency (the same record is not re-published).

## Step 5 · Browser QA the freshly-published CTA

```powershell
worker/.venv/Scripts/python.exe scripts/marketing_browser_check.py `
    --from-feishu --limit 5 --notify-feishu
```

Expected:
- Each CTA URL passes `http_ok` / `has_title` / `ticker_reference` /
  `email_gate` / `disclaimer`.
- Feishu review chat receives a **green "Sentinel AI · Browser QA" card**
  with `Passed: N · Failed: 0`.

If any CTA fails the check, the most likely cause is `GROWTH_OS_PUBLIC_URL`
being misconfigured (Railway env) — the URL won't resolve.

## Step 6 · Run the daily digest manually

The scheduled run is 16:30 ET. To verify the pipeline now without waiting:

```powershell
worker/.venv/Scripts/python.exe scripts/feishu/push_daily_growth_digest.py
```

Expected:
- Console: `[digest] date=YYYY-MM-DD rollups=N upserted=N pending_review=N blocked_by_redline=N failed_publish=N notified=True`
- Bitable Performance table has one upserted row per `content_id` with
  `as of YYYY-MM-DD ET` in notes.
- Feishu review chat receives an **indigo "Sentinel AI · Daily Growth Digest" card**.

Railway logs equivalent (next scheduled run):

```text
[kpi_aggregator] run start — date=YYYY-MM-DD window=…→… notify_chat=True
[kpi_aggregator] run done — date=YYYY-MM-DD rollups=N upserted=N pending=N blocked=N failed_publish=N notified=True
```

---

## Smoke success criteria

After all 6 steps:

| Check | Where |
|-------|-------|
| Bitable Content Queue · 1 Published row with `about:dryrun?…` URL | Bitable |
| Feishu review chat · grey "Published (dry-run)" card | Feishu |
| Feishu review chat · green "Browser QA · Passed N" card | Feishu |
| Feishu review chat · indigo "Daily Growth Digest" card | Feishu |
| Railway logs · `[review_poller] tick done — scanned=0` after second run | Railway logs |

If all five PASS, the dry-run pipeline is healthy on Railway.

## When to flip live

**Only after**:
1. This smoke runs clean 2+ times on consecutive days.
2. Bot is added as **admin** of the public Telegram channel with **Post Messages**.
3. `marketing_deploy_preflight.py --send-telegram-test` returns PASS.
4. You've manually inspected the body of at least one
   `CT-…-tg` Bitable row and confirmed the post copy is publishable.

Then on Railway dashboard:

```dotenv
MARKETING_PUBLISH_DRY_RUN=false
```

Redeploy. Next poller log line should read:

```text
[review_poller] tick start — publishers=Telegram dry_run=False notify_chat=True
```

Approve one fresh `-tg` draft and confirm the Telegram channel receives the
real post + the Bitable URL writes to `https://t.me/SentinelAI_signals/{message_id}`.

If anything looks off, flip back to `MARKETING_PUBLISH_DRY_RUN=true` and
redeploy — the next poller tick resumes dry-run within 5 minutes.

## Rollback (no live posts went out yet)

To stop all Growth OS jobs without disturbing analyze / bot / Whop:

```dotenv
MARKETING_QUEUE_POLL_ENABLED=false
MARKETING_DAILY_DIGEST_ENABLED=false
```

Redeploy. The two scheduled jobs un-register on next startup. The rest of
the worker keeps running.
