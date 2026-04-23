-- CreateEnum
CREATE TYPE "AnalysisStatus" AS ENUM ('QUEUED', 'RUNNING', 'COMPLETED', 'FAILED');

-- CreateEnum
CREATE TYPE "ReportTier" AS ENUM ('BASIC', 'DEEP');

-- CreateEnum
CREATE TYPE "SubscriptionPlan" AS ENUM ('FREE', 'PRO');

-- CreateEnum
CREATE TYPE "SubscriptionState" AS ENUM ('INACTIVE', 'ACTIVE', 'PAST_DUE', 'CANCELED', 'EXPIRED');

-- CreateTable
CREATE TABLE "User" (
    "id" TEXT NOT NULL,
    "email" TEXT NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "User_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "AnalysisHistory" (
    "id" TEXT NOT NULL,
    "ticker" TEXT NOT NULL,
    "requestedMode" "ReportTier" NOT NULL,
    "deepMode" TEXT,
    "status" "AnalysisStatus" NOT NULL DEFAULT 'QUEUED',
    "workerJobId" TEXT,
    "finalScore" INTEGER,
    "rating" TEXT,
    "recommendation" TEXT,
    "emailDeliveryId" TEXT,
    "errorMessage" TEXT,
    "resultJson" JSONB,
    "markdownReport" TEXT,
    "pdfUrl" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,
    "completedAt" TIMESTAMP(3),
    "userId" TEXT NOT NULL,

    CONSTRAINT "AnalysisHistory_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "SubscriptionStatus" (
    "id" TEXT NOT NULL,
    "plan" "SubscriptionPlan" NOT NULL DEFAULT 'FREE',
    "state" "SubscriptionState" NOT NULL DEFAULT 'INACTIVE',
    "lemonCustomerId" TEXT,
    "lemonOrderId" TEXT,
    "lemonSubscriptionId" TEXT,
    "lemonVariantId" TEXT,
    "renewsAt" TIMESTAMP(3),
    "endsAt" TIMESTAMP(3),
    "lastWebhookEvent" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,
    "userId" TEXT NOT NULL,

    CONSTRAINT "SubscriptionStatus_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "User_email_key" ON "User"("email");

-- CreateIndex
CREATE UNIQUE INDEX "AnalysisHistory_workerJobId_key" ON "AnalysisHistory"("workerJobId");

-- CreateIndex
CREATE INDEX "AnalysisHistory_userId_createdAt_idx" ON "AnalysisHistory"("userId", "createdAt");

-- CreateIndex
CREATE INDEX "AnalysisHistory_status_idx" ON "AnalysisHistory"("status");

-- CreateIndex
CREATE UNIQUE INDEX "SubscriptionStatus_lemonSubscriptionId_key" ON "SubscriptionStatus"("lemonSubscriptionId");

-- CreateIndex
CREATE UNIQUE INDEX "SubscriptionStatus_userId_key" ON "SubscriptionStatus"("userId");

-- AddForeignKey
ALTER TABLE "AnalysisHistory" ADD CONSTRAINT "AnalysisHistory_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "SubscriptionStatus" ADD CONSTRAINT "SubscriptionStatus_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User"("id") ON DELETE CASCADE ON UPDATE CASCADE;
