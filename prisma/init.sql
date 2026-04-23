CREATE TYPE "AnalysisStatus" AS ENUM ('QUEUED', 'RUNNING', 'COMPLETED', 'FAILED');
CREATE TYPE "ReportTier" AS ENUM ('BASIC', 'DEEP');
CREATE TYPE "SubscriptionPlan" AS ENUM ('FREE', 'PRO');
CREATE TYPE "SubscriptionState" AS ENUM ('INACTIVE', 'ACTIVE', 'PAST_DUE', 'CANCELED', 'EXPIRED');

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
  "lemonCustomerId" TEXT,
  "lemonOrderId" TEXT,
  "lemonSubscriptionId" TEXT UNIQUE,
  "lemonVariantId" TEXT,
  "renewsAt" TIMESTAMPTZ,
  "endsAt" TIMESTAMPTZ,
  "lastWebhookEvent" TEXT,
  "createdAt" TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  "updatedAt" TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  "userId" TEXT NOT NULL UNIQUE,
  CONSTRAINT "SubscriptionStatus_userId_fkey"
    FOREIGN KEY ("userId") REFERENCES "User"("id")
    ON DELETE CASCADE
    ON UPDATE CASCADE
);

CREATE INDEX "AnalysisHistory_userId_createdAt_idx"
  ON "AnalysisHistory" ("userId", "createdAt");

CREATE INDEX "AnalysisHistory_status_idx"
  ON "AnalysisHistory" ("status");
