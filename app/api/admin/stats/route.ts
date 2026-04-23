import { SubscriptionPlan, SubscriptionState } from "@prisma/client";
import { NextResponse } from "next/server";

import { requireAdminRequest } from "@/lib/admin";
import { appEnv } from "@/lib/env";
import { prisma } from "@/lib/prisma";
import { STALE_REAP_ERROR_PREFIX } from "@/lib/reaper";

export const dynamic = "force-dynamic";

function getStartOfUtcDay() {
  const start = new Date();
  start.setUTCHours(0, 0, 0, 0);
  return start;
}

export async function GET(request: Request) {
  const unauthorized = requireAdminRequest(request);

  if (unauthorized) {
    return unauthorized;
  }

  const today = getStartOfUtcDay();
  const [dailyTotal, dailyCompleted, dailyFailed, dailyReaped, subscriptionGroups] = await Promise.all([
    prisma.analysisHistory.count({
      where: {
        createdAt: {
          gte: today
        }
      }
    }),
    prisma.analysisHistory.count({
      where: {
        status: "COMPLETED",
        createdAt: {
          gte: today
        }
      }
    }),
    prisma.analysisHistory.count({
      where: {
        status: "FAILED",
        createdAt: {
          gte: today
        }
      }
    }),
    prisma.analysisHistory.count({
      where: {
        status: "FAILED",
        errorMessage: {
          startsWith: STALE_REAP_ERROR_PREFIX
        },
        createdAt: {
          gte: today
        }
      }
    }),
    prisma.subscriptionStatus.groupBy({
      by: ["plan", "state"],
      _count: {
        _all: true
      }
    })
  ]);

  const proByState = subscriptionGroups
    .filter((item) => item.plan === SubscriptionPlan.PRO)
    .reduce<Record<SubscriptionState, number>>(
      (accumulator, item) => {
        accumulator[item.state] = item._count._all;
        return accumulator;
      },
      {
        ACTIVE: 0,
        CANCELED: 0,
        EXPIRED: 0,
        INACTIVE: 0,
        PAST_DUE: 0
      }
    );

  const activeProSubscriptions = proByState.ACTIVE ?? 0;
  const mrrEstimateUsd = Number((activeProSubscriptions * appEnv.proMonthlyPriceUsd).toFixed(2));

  return NextResponse.json({
    generatedAt: new Date().toISOString(),
    tasks: {
      today: {
        total: dailyTotal,
        completed: dailyCompleted,
        failed: dailyFailed,
        reaped: dailyReaped,
        successRate: dailyTotal > 0 ? Number((dailyCompleted / dailyTotal).toFixed(4)) : 0,
        failureRate: dailyTotal > 0 ? Number((dailyFailed / dailyTotal).toFixed(4)) : 0
      }
    },
    revenue: {
      activeProSubscriptions,
      pastDueProSubscriptions: proByState.PAST_DUE ?? 0,
      canceledProSubscriptions: proByState.CANCELED ?? 0,
      monthlyPriceUsd: appEnv.proMonthlyPriceUsd,
      mrrEstimateUsd,
      arrEstimateUsd: Number((mrrEstimateUsd * 12).toFixed(2))
    },
    subscriptions: {
      pro: proByState,
      freeUsers: subscriptionGroups
        .filter((item) => item.plan === SubscriptionPlan.FREE)
        .reduce((sum, item) => sum + item._count._all, 0)
    }
  });
}
