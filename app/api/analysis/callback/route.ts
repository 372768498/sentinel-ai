import { AnalysisStatus } from "@prisma/client";
import { NextResponse } from "next/server";
import { z } from "zod";

import { appEnv } from "@/lib/env";
import { prisma } from "@/lib/prisma";

const callbackSchema = z.object({
  historyId: z.string(),
  jobId: z.string(),
  status: z.enum(["completed", "failed"]),
  resultJson: z.record(z.any()).optional(),
  markdownReport: z.string().optional(),
  emailDeliveryId: z.string().optional(),
  errorMessage: z.string().optional()
});

export async function POST(request: Request) {
  const token = request.headers.get("x-internal-token");

  if (!token || token !== appEnv.internalCallbackSecret) {
    return NextResponse.json({ error: "Unauthorized callback" }, { status: 401 });
  }

  const payload = callbackSchema.parse(await request.json());

  await prisma.analysisHistory.update({
    where: {
      id: payload.historyId
    },
    data: {
      workerJobId: payload.jobId,
      status: payload.status === "completed" ? AnalysisStatus.COMPLETED : AnalysisStatus.FAILED,
      resultJson: payload.resultJson,
      markdownReport: payload.markdownReport,
      emailDeliveryId: payload.emailDeliveryId,
      errorMessage: payload.errorMessage,
      finalScore:
        typeof payload.resultJson?.score_100 === "number" ? payload.resultJson.score_100 : null,
      rating: typeof payload.resultJson?.rating === "string" ? payload.resultJson.rating : null,
      recommendation:
        typeof payload.resultJson?.recommendation === "string"
          ? payload.resultJson.recommendation
          : null,
      completedAt: new Date()
    }
  });

  return NextResponse.json({ ok: true });
}
