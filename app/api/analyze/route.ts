import { AnalysisStatus, ReportTier } from "@prisma/client";
import { NextResponse } from "next/server";
import { z } from "zod";

import { countBasicReportsToday, getOrCreateUser, isProUser, normalizeEmail, normalizeTicker } from "@/lib/analysis";
import { appEnv } from "@/lib/env";
import { prisma } from "@/lib/prisma";
import { reclaimStaleAnalyses } from "@/lib/reaper";
import { createWorkerJob } from "@/lib/worker";

const analyzeSchema = z.object({
  ticker: z.string().min(1),
  email: z.string().email(),
  requestedMode: z.enum(["basic", "deep"]),
  deepMode: z.string().optional()
});

export async function POST(request: Request) {
  try {
    const payload = analyzeSchema.parse(await request.json());
    await reclaimStaleAnalyses({ limit: 25 });

    const email = normalizeEmail(payload.email);
    const ticker = normalizeTicker(payload.ticker);
    const user = await getOrCreateUser(email);
    const pro = isProUser(user.subscription);

    if (payload.requestedMode === "deep" && !pro) {
      return NextResponse.json(
        {
          error: "Deep Mode requires an active Pro subscription.",
          upgradeRequired: true
        },
        { status: 403 }
      );
    }

    const todayUsage = pro ? 0 : await countBasicReportsToday(user.id);

    if (!pro && todayUsage >= 1) {
      return NextResponse.json(
        {
          error: "Free users can only run one basic report per day.",
          quotaExceeded: true
        },
        { status: 429 }
      );
    }

    const history = await prisma.analysisHistory.create({
      data: {
        userId: user.id,
        ticker,
        requestedMode: payload.requestedMode === "deep" ? ReportTier.DEEP : ReportTier.BASIC,
        deepMode: payload.requestedMode === "deep" ? payload.deepMode ?? "valuation" : null,
        status: AnalysisStatus.QUEUED
      }
    });

    try {
      const workerJob = await createWorkerJob({
        historyId: history.id,
        ticker,
        email,
        requestedMode: payload.requestedMode,
        deepMode: payload.requestedMode === "deep" ? payload.deepMode ?? "valuation" : undefined,
        callbackUrl: `${appEnv.appUrl}/api/analysis/callback`,
        callbackSecret: appEnv.internalCallbackSecret
      });

      await prisma.analysisHistory.update({
        where: {
          id: history.id
        },
        data: {
          workerJobId: workerJob.jobId,
          status: AnalysisStatus.RUNNING
        }
      });

      return NextResponse.json({
        historyId: history.id,
        jobId: workerJob.jobId,
        eventsUrl: workerJob.eventsUrl,
        pollUrl: workerJob.pollUrl,
        isPro: pro,
        quota: {
          limit: pro ? 0 : 1,
          used: pro ? 0 : todayUsage + 1,
          unlimited: pro
        }
      });
    } catch (error) {
      await prisma.analysisHistory.update({
        where: {
          id: history.id
        },
        data: {
          status: AnalysisStatus.FAILED,
          errorMessage: error instanceof Error ? error.message : "Worker unavailable"
        }
      });

      throw error;
    }
  } catch (error) {
    if (error instanceof z.ZodError) {
      return NextResponse.json({ error: error.issues[0]?.message ?? "Invalid request" }, { status: 400 });
    }

    const message = error instanceof Error ? error.message : "Analyze route failed";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
