import { NextResponse } from "next/server";

import { requireAdminRequest, sendOpsAlert } from "@/lib/admin";
import { appEnv } from "@/lib/env";
import { reclaimStaleAnalyses } from "@/lib/reaper";

export const dynamic = "force-dynamic";

async function handleReap(request: Request) {
  const unauthorized = requireAdminRequest(request);

  if (unauthorized) {
    return unauthorized;
  }

  const summary = await reclaimStaleAnalyses();
  const threshold = appEnv.reapAlertFailureRateThreshold;
  const alertTriggered = summary.totalDailyTasks > 0 && summary.reapRate > threshold;

  if (alertTriggered) {
    try {
      await sendOpsAlert({
        title: "High stale-analysis reap rate detected",
        severity: "high",
        details: {
          threshold,
          reapRate: summary.reapRate,
          totalDailyTasks: summary.totalDailyTasks,
          reapedToday: summary.reapedToday,
          failedToday: summary.failedToday,
          latestReapedTaskIds: summary.reapedTaskIds
        }
      });
    } catch (error) {
      console.error("Failed to deliver ops alert", error);
    }
  }

  return NextResponse.json({
    ok: true,
    threshold,
    alertTriggered,
    summary
  });
}

export async function GET(request: Request) {
  return handleReap(request);
}

export async function POST(request: Request) {
  return handleReap(request);
}
