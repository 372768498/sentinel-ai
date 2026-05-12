-- Sentinel Growth OS · ProWaitlist
--
-- Captures email addresses for users who clicked "Join waitlist" on the
-- Coming-Soon Pro Watch / Pro tier cards on sentinel.jilo.ai. Kept
-- separate from EmailLead so the two funnels don't co-mingle —
-- EmailLead is a free-product magic-link user; ProWaitlist is a
-- paid-product future-customer signal.
--
-- All ADD use IF NOT EXISTS for re-run safety.

CREATE TABLE IF NOT EXISTS "ProWaitlist" (
  "id"        TEXT NOT NULL,
  "email"     TEXT NOT NULL,
  "tier"      TEXT NOT NULL,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "source"    TEXT,

  CONSTRAINT "ProWaitlist_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX IF NOT EXISTS "ProWaitlist_email_key"
  ON "ProWaitlist"("email");

CREATE INDEX IF NOT EXISTS "ProWaitlist_tier_idx"
  ON "ProWaitlist"("tier");

CREATE INDEX IF NOT EXISTS "ProWaitlist_createdAt_idx"
  ON "ProWaitlist"("createdAt");
