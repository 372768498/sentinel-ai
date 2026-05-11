import { AnalysisStatus, Prisma } from "@prisma/client";
import { NextResponse } from "next/server";

import { prisma } from "@/lib/prisma";

export const dynamic = "force-dynamic";

type TrackRecordRow = {
  id: string;
  issuedAt: string;
  ticker: string;
  score: number | null;
  state: string | null;
  reportTier: string;
  sourceCited: boolean;
  sourceCount: number;
  pdfAvailable: boolean;
  t3Return: null;
  t7Return: null;
};

function asRecord(value: Prisma.JsonValue | null): Record<string, Prisma.JsonValue> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return {};
  }

  return value as Record<string, Prisma.JsonValue>;
}

function stringArray(value: Prisma.JsonValue | undefined): string[] {
  if (!Array.isArray(value)) {
    return [];
  }

  return value.filter((item): item is string => typeof item === "string");
}

function extractSourceCount(resultJson: Prisma.JsonValue | null, markdownReport: string | null) {
  const result = asRecord(resultJson);
  const sources = [
    ...stringArray(result.sources),
    ...stringArray(result.citations),
    ...stringArray(result.source_urls)
  ];

  const uniqueSources = new Set(sources.filter((source) => /^https?:\/\//i.test(source)));
  const markdownUrlCount = markdownReport?.match(/https?:\/\/[^\s)]+/gi)?.length ?? 0;

  return Math.max(uniqueSources.size, markdownUrlCount);
}

export async function GET() {
  const since = new Date();
  since.setUTCDate(since.getUTCDate() - 90);

  const records = await prisma.analysisHistory.findMany({
    where: {
      status: AnalysisStatus.COMPLETED,
      createdAt: {
        gte: since
      }
    },
    orderBy: {
      createdAt: "desc"
    },
    take: 250,
    select: {
      id: true,
      ticker: true,
      requestedMode: true,
      finalScore: true,
      rating: true,
      recommendation: true,
      resultJson: true,
      markdownReport: true,
      pdfUrl: true,
      createdAt: true
    }
  });

  const rows: TrackRecordRow[] = records.map((record) => {
    const sourceCount = extractSourceCount(record.resultJson, record.markdownReport);

    return {
      id: record.id,
      issuedAt: record.createdAt.toISOString(),
      ticker: record.ticker,
      score: record.finalScore,
      state: record.recommendation ?? record.rating,
      reportTier: record.requestedMode,
      sourceCited: sourceCount > 0,
      sourceCount,
      pdfAvailable: Boolean(record.pdfUrl),
      t3Return: null,
      t7Return: null
    };
  });

  return NextResponse.json(
    {
      generatedAt: new Date().toISOString(),
      windowDays: 90,
      note: "T+3/T+7 return columns stay null until historical price snapshots are persisted.",
      rows
    },
    {
      headers: {
        "Cache-Control": "public, max-age=3600, s-maxage=3600"
      }
    }
  );
}
