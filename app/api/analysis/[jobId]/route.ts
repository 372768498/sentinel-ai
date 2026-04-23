import { NextResponse } from "next/server";

import { prisma } from "@/lib/prisma";

export async function GET(_: Request, context: { params: { jobId: string } }) {
  const record = await prisma.analysisHistory.findFirst({
    where: {
      workerJobId: context.params.jobId
    },
    select: {
      status: true,
      errorMessage: true,
      resultJson: true,
      completedAt: true
    }
  });

  if (!record) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }

  return NextResponse.json(record);
}
