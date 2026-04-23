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
3. Confirm the frontend opens Lemon Squeezy Overlay, falling back to full-page checkout only if Lemon JS is unavailable.
4. Complete checkout with the live Pro variant.
5. Confirm Lemon webhook arrives at `/api/webhooks/lemonsqueezy`.
6. Confirm `subscriptionStatus.plan=PRO` and `subscriptionStatus.state=ACTIVE`.
7. Re-run deep analysis and confirm it starts successfully.

## 4. Webhook Mode Transition

1. Ensure Vercel production env sets `LEMON_SQUEEZY_MODE=live`.
2. Ensure checkout creation uses the live store and live variant IDs.
3. Ensure the production webhook in Lemon dashboard is the live webhook, with the live signing secret.
4. Send a simulated test-mode webhook to production and confirm the API responds with `ignored: true`.
5. Send a live webhook and confirm the subscription is synced.

## 5. Reaper And Alerting

1. Create or backfill a stale `QUEUED` or `RUNNING` analysis older than `REAP_STALE_MINUTES`.
2. Call `POST /api/admin/reap` with admin auth.
3. Confirm stale tasks are marked `FAILED` with `[STALE_REAP]` prefix.
4. If stale reaps exceed the configured daily threshold, confirm an ops alert is emitted.

## 6. Social Preview

1. Call `GET /api/admin/generate-preview/NVDA`.
2. Confirm a 1200x630 image is returned.
3. Confirm the image shows ticker, score, rating, recommendation, and updated timestamp.
