import { AnalysisStatus, ReportTier, SubscriptionPlan, SubscriptionState } from "@prisma/client";

import { prisma } from "@/lib/prisma";

export function normalizeTicker(value: string): string {
  return value.trim().toUpperCase();
}

export function normalizeEmail(value: string): string {
  return value.trim().toLowerCase();
}

export async function getOrCreateUser(email: string) {
  return prisma.user.upsert({
    where: {
      email
    },
    update: {},
    create: {
      email,
      subscription: {
        create: {
          plan: SubscriptionPlan.FREE,
          state: SubscriptionState.INACTIVE
        }
      }
    },
    include: {
      subscription: true
    }
  });
}

export function isProUser(state?: { plan: SubscriptionPlan; state: SubscriptionState } | null): boolean {
  return state?.plan === SubscriptionPlan.PRO && state.state === SubscriptionState.ACTIVE;
}

export async function countBasicReportsToday(userId: string) {
  const start = new Date();
  start.setUTCHours(0, 0, 0, 0);

  return prisma.analysisHistory.count({
    where: {
      userId,
      requestedMode: ReportTier.BASIC,
      status: {
        in: [AnalysisStatus.QUEUED, AnalysisStatus.RUNNING, AnalysisStatus.COMPLETED]
      },
      createdAt: {
        gte: start
      }
    }
  });
}
