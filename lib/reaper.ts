import { AnalysisStatus } from "@prisma/client";

import { appEnv } from "@/lib/env";
import { prisma } from "@/lib/prisma";

export const STALE_REAP_ERROR_PREFIX = "[STALE_REAP]";

type ReclaimOptions = {
  staleMinutes?: number;
  limit?: number;
};

function getStartOfUtcDay() {
  const start = new Date();
  start.setUTCHours(0, 0, 0, 0);
  return start;
}

export async function reclaimStaleAnalyses(options: ReclaimOptions = {}) {
  const staleMinutes = options.staleMinutes ?? appEnv.reapStaleMinutes;
  const limit = options.limit ?? 100;
  const cutoff = new Date(Date.now() - staleMinutes * 60_000);
  const now = new Date();

  const staleRecords = await prisma.analysisHistory.findMany({
    where: {
      status: {
        in: [AnalysisStatus.QUEUED, AnalysisStatus.RUNNING]
      },
      updatedAt: {
        lt: cutoff
      }
    },
    orderBy: {
      updatedAt: "asc"
    },
    take: limit,
    select: {
      id: true,
      ticker: true,
      workerJobId: true,
      updatedAt: true
    }
  });

  if (staleRecords.length > 0) {
    await prisma.analysisHistory.updateMany({
      where: {
        id: {
          in: staleRecords.map((record) => record.id)
        }
      },
      data: {
        status: AnalysisStatus.FAILED,
        errorMessage: `${STALE_REAP_ERROR_PREFIX} Reaped stale analysis after ${staleMinutes} minutes without callback.`,
        completedAt: now
      }
    });
  }

  const today = getStartOfUtcDay();
  const [totalDailyTasks, failedToday, reapedToday] = await Promise.all([
    prisma.analysisHistory.count({
      where: {
        createdAt: {
          gte: today
        }
      }
    }),
    prisma.analysisHistory.count({
      where: {
        status: AnalysisStatus.FAILED,
        createdAt: {
          gte: today
        }
      }
    }),
    prisma.analysisHistory.count({
      where: {
        status: AnalysisStatus.FAILED,
        errorMessage: {
          startsWith: STALE_REAP_ERROR_PREFIX
        },
        createdAt: {
          gte: today
        }
      }
    })
  ]);

  return {
    staleMinutes,
    cutoffIso: cutoff.toISOString(),
    totalDailyTasks,
    failedToday,
    reapedToday,
    reapedCount: staleRecords.length,
    reapedTaskIds: staleRecords.map((record) => record.id),
    reapedJobs: staleRecords.map((record) => ({
      id: record.id,
      ticker: record.ticker,
      workerJobId: record.workerJobId,
      updatedAt: record.updatedAt.toISOString()
    })),
    reapRate: totalDailyTasks > 0 ? reapedToday / totalDailyTasks : 0
  };
}
