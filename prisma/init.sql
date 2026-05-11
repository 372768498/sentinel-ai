CREATE TYPE "AnalysisStatus" AS ENUM ('QUEUED', 'RUNNING', 'COMPLETED', 'FAILED');
CREATE TYPE "ReportTier" AS ENUM ('BASIC', 'DEEP');
CREATE TYPE "SubscriptionPlan" AS ENUM ('FREE', 'PRO');
CREATE TYPE "SubscriptionState" AS ENUM ('INACTIVE', 'ACTIVE', 'PAST_DUE', 'CANCELED', 'EXPIRED');
CREATE TYPE "MarketingChannel" AS ENUM ('X', 'REDDIT', 'TELEGRAM');
CREATE TYPE "MarketingDraftStatus" AS ENUM ('DRAFT', 'APPROVED', 'REJECTED', 'POSTED');

CREATE TABLE "User" (
  "id" TEXT PRIMARY KEY,
  "email" TEXT NOT NULL UNIQUE,
  "createdAt" TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  "updatedAt" TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE "AnalysisHistory" (
  "id" TEXT PRIMARY KEY,
  "ticker" TEXT NOT NULL,
  "requestedMode" "ReportTier" NOT NULL,
  "deepMode" TEXT,
  "status" "AnalysisStatus" NOT NULL DEFAULT 'QUEUED',
  "workerJobId" TEXT UNIQUE,
  "accessToken" TEXT UNIQUE,
  "finalScore" INTEGER,
  "rating" TEXT,
  "recommendation" TEXT,
  "emailDeliveryId" TEXT,
  "errorMessage" TEXT,
  "resultJson" JSONB,
  "markdownReport" TEXT,
  "pdfUrl" TEXT,
  "createdAt" TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  "updatedAt" TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  "completedAt" TIMESTAMPTZ,
  "userId" TEXT NOT NULL,
  CONSTRAINT "AnalysisHistory_userId_fkey"
    FOREIGN KEY ("userId") REFERENCES "User"("id")
    ON DELETE CASCADE
    ON UPDATE CASCADE
);

CREATE TABLE "SubscriptionStatus" (
  "id" TEXT PRIMARY KEY,
  "plan" "SubscriptionPlan" NOT NULL DEFAULT 'FREE',
  "state" "SubscriptionState" NOT NULL DEFAULT 'INACTIVE',
  "whopUserId" TEXT,
  "whopMembershipId" TEXT UNIQUE,
  "whopProductId" TEXT,
  "whopPlanId" TEXT,
  "renewsAt" TIMESTAMPTZ,
  "endsAt" TIMESTAMPTZ,
  "lastWebhookEvent" TEXT,
  "telegramUserId" TEXT,
  "telegramInviteLink" TEXT,
  "telegramJoinedAt" TIMESTAMPTZ,
  "createdAt" TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  "updatedAt" TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  "userId" TEXT NOT NULL UNIQUE,
  CONSTRAINT "SubscriptionStatus_userId_fkey"
    FOREIGN KEY ("userId") REFERENCES "User"("id")
    ON DELETE CASCADE
    ON UPDATE CASCADE
);

CREATE TABLE "MarketingDraft" (
  "id" TEXT PRIMARY KEY,
  "channel" "MarketingChannel" NOT NULL,
  "persona" TEXT NOT NULL,
  "ticker" TEXT,
  "score" INTEGER,
  "headline" TEXT NOT NULL,
  "body" TEXT NOT NULL,
  "sourceUrl" TEXT,
  "deepLink" TEXT,
  "status" "MarketingDraftStatus" NOT NULL DEFAULT 'DRAFT',
  "redlineOk" BOOLEAN NOT NULL DEFAULT false,
  "redlineNotes" TEXT,
  "scheduledFor" TIMESTAMPTZ,
  "approvedAt" TIMESTAMPTZ,
  "approvedBy" TEXT,
  "rejectedAt" TIMESTAMPTZ,
  "rejectionReason" TEXT,
  "postedAt" TIMESTAMPTZ,
  "externalPostId" TEXT,
  "createdAt" TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  "updatedAt" TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX "AnalysisHistory_userId_createdAt_idx"
  ON "AnalysisHistory" ("userId", "createdAt");

CREATE INDEX "AnalysisHistory_status_idx"
  ON "AnalysisHistory" ("status");

CREATE INDEX "MarketingDraft_status_channel_createdAt_idx"
  ON "MarketingDraft" ("status", "channel", "createdAt");

CREATE INDEX "MarketingDraft_ticker_idx"
  ON "MarketingDraft" ("ticker");
