import { NextResponse } from "next/server";

import { prisma } from "@/lib/prisma";

export async function GET(request: Request, context: { params: Promise<{ jobId: string }> }) {
  const token = new URL(request.url).searchParams.get("token");

  if (!token) {
    return NextResponse.json({ error: "Missing access token" }, { status: 401 });
  }

  const { jobId } = await context.params;
  const record = await prisma.analysisHistory.findFirst({
    where: {
      workerJobId: jobId,
      accessToken: token
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
