import { MarketingChannel, MarketingDraftStatus } from "@prisma/client";
import { NextResponse } from "next/server";
import { z } from "zod";

import { requireAdminRequest } from "@/lib/admin";
import { prisma } from "@/lib/prisma";

export const dynamic = "force-dynamic";

const createDraftSchema = z.object({
  channel: z.nativeEnum(MarketingChannel),
  persona: z.string().trim().min(1).max(80),
  ticker: z.string().trim().max(8).optional(),
  score: z.number().int().min(0).max(100).optional(),
  headline: z.string().trim().min(1).max(180),
  body: z.string().trim().min(1).max(5000),
  sourceUrl: z.string().trim().url().optional(),
  deepLink: z.string().trim().url().optional(),
  redlineOk: z.boolean().default(false),
  redlineNotes: z.string().trim().max(1000).optional(),
  scheduledFor: z.string().datetime().optional()
});

function parseStatus(value: string | null) {
  if (!value) {
    return undefined;
  }

  return Object.values(MarketingDraftStatus).includes(value as MarketingDraftStatus)
    ? (value as MarketingDraftStatus)
    : undefined;
}

export async function GET(request: Request) {
  const unauthorized = requireAdminRequest(request);

  if (unauthorized) {
    return unauthorized;
  }

  const url = new URL(request.url);
  const status = parseStatus(url.searchParams.get("status"));

  const drafts = await prisma.marketingDraft.findMany({
    where: status ? { status } : undefined,
    orderBy: {
      createdAt: "desc"
    },
    take: 100
  });

  return NextResponse.json({
    generatedAt: new Date().toISOString(),
    drafts
  });
}

export async function POST(request: Request) {
  const unauthorized = requireAdminRequest(request);

  if (unauthorized) {
    return unauthorized;
  }

  const parsed = createDraftSchema.safeParse(await request.json());

  if (!parsed.success) {
    return NextResponse.json({ error: parsed.error.flatten() }, { status: 400 });
  }

  const draft = await prisma.marketingDraft.create({
    data: {
      ...parsed.data,
      ticker: parsed.data.ticker?.toUpperCase(),
      scheduledFor: parsed.data.scheduledFor ? new Date(parsed.data.scheduledFor) : undefined
    }
  });

  return NextResponse.json({ draft }, { status: 201 });
}
