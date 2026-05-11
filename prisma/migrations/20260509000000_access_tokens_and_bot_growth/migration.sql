-- Protect report polling links with an unguessable per-analysis access token.
ALTER TABLE "AnalysisHistory"
  ADD COLUMN IF NOT EXISTS "accessToken" TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS "AnalysisHistory_accessToken_key"
  ON "AnalysisHistory"("accessToken");

-- Bot-owned tables are created by worker/app/bot/db.py in existing installs.
-- These additive columns keep local/prod databases compatible while the bot
-- schema is moved toward first-class migrations.
ALTER TABLE IF EXISTS telegram_bot_profile
  ADD COLUMN IF NOT EXISTS signup_source TEXT,
  ADD COLUMN IF NOT EXISTS signup_campaign TEXT,
  ADD COLUMN IF NOT EXISTS signup_ticker TEXT,
  ADD COLUMN IF NOT EXISTS signup_payload_raw TEXT,
  ADD COLUMN IF NOT EXISTS signup_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS snooze_until TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_tbp_signup_source
  ON telegram_bot_profile (signup_source);

CREATE INDEX IF NOT EXISTS idx_tbp_snooze_until
  ON telegram_bot_profile (snooze_until);
