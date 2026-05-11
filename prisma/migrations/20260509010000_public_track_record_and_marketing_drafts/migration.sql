-- Public trust asset and growth approval queue.

CREATE TYPE "MarketingChannel" AS ENUM ('X', 'REDDIT', 'TELEGRAM');
CREATE TYPE "MarketingDraftStatus" AS ENUM ('DRAFT', 'APPROVED', 'REJECTED', 'POSTED');

CREATE TABLE "MarketingDraft" (
  "id" TEXT NOT NULL,
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
  "scheduledFor" TIMESTAMP(3),
  "approvedAt" TIMESTAMP(3),
  "approvedBy" TEXT,
  "rejectedAt" TIMESTAMP(3),
  "rejectionReason" TEXT,
  "postedAt" TIMESTAMP(3),
  "externalPostId" TEXT,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updatedAt" TIMESTAMP(3) NOT NULL,

  CONSTRAINT "MarketingDraft_pkey" PRIMARY KEY ("id")
);

CREATE INDEX "MarketingDraft_status_channel_createdAt_idx"
  ON "MarketingDraft"("status", "channel", "createdAt");

CREATE INDEX "MarketingDraft_ticker_idx"
  ON "MarketingDraft"("ticker");
