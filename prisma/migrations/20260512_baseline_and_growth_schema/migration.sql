-- Sentinel Growth OS · baseline + Sprint 1 schema
--
-- Two purposes bundled (review section dividers below):
--   1. Baseline (BASELINE block) — creates 4 tables that exist in
--      schema.prisma but were missing from production: EmailLead,
--      ShareLink, VisitEvent, ContentItem. Adds AnalysisHistory.accessToken
--      that earlier migration 20260509000000 was supposed to add but was
--      marked --applied without running.
--   2. Sprint 1 (GROWTH OS block) — User notification preferences +
--      pricing tier; EmailLead seed tickers.
--
-- All ADD COLUMN / CREATE TABLE use IF NOT EXISTS for re-run safety.
-- No DROP TABLE / DROP COLUMN. No data migration.
-- Bot-runtime tables (telegram_bot_profile, alert_log, alert_cooldown,
-- queued_alerts) are managed by worker/app/bot/db.py — Prisma must not
-- touch them (diff would attempt DROP; those statements were stripped).


-- AlterTable
ALTER TABLE "AnalysisHistory" ADD COLUMN IF NOT EXISTS "accessToken" TEXT;

-- AlterTable
ALTER TABLE "User" ADD COLUMN IF NOT EXISTS "notificationMode" TEXT NOT NULL DEFAULT 'morning',
ADD COLUMN IF NOT EXISTS "proTier" TEXT,
ADD COLUMN IF NOT EXISTS "quietHoursEnd" INTEGER,
ADD COLUMN IF NOT EXISTS "quietHoursStart" INTEGER,
ADD COLUMN IF NOT EXISTS "timezone" TEXT NOT NULL DEFAULT 'America/New_York',
ADD COLUMN IF NOT EXISTS "vacationUntil" TIMESTAMP(3),
ADD COLUMN IF NOT EXISTS "watchlistLimit" INTEGER NOT NULL DEFAULT 0;

-- CreateTable
CREATE TABLE IF NOT EXISTS "EmailLead" (
    "id" TEXT NOT NULL,
    "email" TEXT NOT NULL,
    "ticker" TEXT,
    "sourcePath" TEXT,
    "utmSource" TEXT,
    "utmMedium" TEXT,
    "utmCampaign" TEXT,
    "utmContent" TEXT,
    "ref" TEXT,
    "magicToken" TEXT,
    "magicTokenExpiresAt" TIMESTAMP(3),
    "verifiedAt" TIMESTAMP(3),
    "seedTickers" TEXT[] DEFAULT ARRAY[]::TEXT[],
    "seedTickersAddedAt" TIMESTAMP(3),
    "userId" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "EmailLead_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE IF NOT EXISTS "ShareLink" (
    "id" TEXT NOT NULL,
    "shareId" TEXT NOT NULL,
    "analysisId" TEXT NOT NULL,
    "views" INTEGER NOT NULL DEFAULT 0,
    "emailCaptures" INTEGER NOT NULL DEFAULT 0,
    "expiresAt" TIMESTAMP(3),
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "ShareLink_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE IF NOT EXISTS "VisitEvent" (
    "id" TEXT NOT NULL,
    "path" TEXT NOT NULL,
    "utmSource" TEXT,
    "utmMedium" TEXT,
    "utmCampaign" TEXT,
    "utmContent" TEXT,
    "ref" TEXT,
    "sessionId" TEXT,
    "leadId" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "VisitEvent_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE IF NOT EXISTS "ContentItem" (
    "id" TEXT NOT NULL,
    "contentId" TEXT NOT NULL,
    "platform" TEXT NOT NULL,
    "ticker" TEXT,
    "hook" TEXT,
    "body" TEXT NOT NULL,
    "ctaUrl" TEXT,
    "riskLevel" TEXT NOT NULL DEFAULT 'Low',
    "redlineStatus" TEXT NOT NULL DEFAULT 'PENDING',
    "redlineNotes" TEXT,
    "reviewStatus" TEXT NOT NULL DEFAULT 'PENDING',
    "reviewerComment" TEXT,
    "feishuRecordId" TEXT,
    "publishTime" TIMESTAMP(3),
    "publishedUrl" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "ContentItem_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX IF NOT EXISTS "EmailLead_magicToken_key" ON "EmailLead"("magicToken");

-- CreateIndex
CREATE UNIQUE INDEX IF NOT EXISTS "EmailLead_userId_key" ON "EmailLead"("userId");

-- CreateIndex
CREATE INDEX IF NOT EXISTS "EmailLead_email_idx" ON "EmailLead"("email");

-- CreateIndex
CREATE INDEX IF NOT EXISTS "EmailLead_magicToken_idx" ON "EmailLead"("magicToken");

-- CreateIndex
CREATE UNIQUE INDEX IF NOT EXISTS "EmailLead_email_ticker_key" ON "EmailLead"("email", "ticker");

-- CreateIndex
CREATE UNIQUE INDEX IF NOT EXISTS "ShareLink_shareId_key" ON "ShareLink"("shareId");

-- CreateIndex
CREATE INDEX IF NOT EXISTS "ShareLink_shareId_idx" ON "ShareLink"("shareId");

-- CreateIndex
CREATE INDEX IF NOT EXISTS "ShareLink_analysisId_idx" ON "ShareLink"("analysisId");

-- CreateIndex
CREATE INDEX IF NOT EXISTS "VisitEvent_leadId_idx" ON "VisitEvent"("leadId");

-- CreateIndex
CREATE INDEX IF NOT EXISTS "VisitEvent_utmCampaign_idx" ON "VisitEvent"("utmCampaign");

-- CreateIndex
CREATE INDEX IF NOT EXISTS "VisitEvent_createdAt_idx" ON "VisitEvent"("createdAt");

-- CreateIndex
CREATE UNIQUE INDEX IF NOT EXISTS "ContentItem_contentId_key" ON "ContentItem"("contentId");

-- CreateIndex
CREATE INDEX IF NOT EXISTS "ContentItem_reviewStatus_platform_idx" ON "ContentItem"("reviewStatus", "platform");

-- CreateIndex
CREATE INDEX IF NOT EXISTS "ContentItem_ticker_idx" ON "ContentItem"("ticker");

-- CreateIndex
CREATE INDEX IF NOT EXISTS "ContentItem_feishuRecordId_idx" ON "ContentItem"("feishuRecordId");

-- CreateIndex
CREATE UNIQUE INDEX IF NOT EXISTS "AnalysisHistory_accessToken_key" ON "AnalysisHistory"("accessToken");

-- AddForeignKey
ALTER TABLE "EmailLead" ADD CONSTRAINT "EmailLead_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ShareLink" ADD CONSTRAINT "ShareLink_analysisId_fkey" FOREIGN KEY ("analysisId") REFERENCES "AnalysisHistory"("id") ON DELETE CASCADE ON UPDATE CASCADE;

