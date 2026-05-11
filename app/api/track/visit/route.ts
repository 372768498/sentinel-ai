import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

interface VisitBody {
  path: string;
  sessionId?: string;
  leadId?: string;
  utm?: {
    utm_source?: string;
    utm_medium?: string;
    utm_campaign?: string;
    utm_content?: string;
    ref?: string;
  };
}

export async function POST(req: NextRequest) {
  let body: VisitBody;
  try {
    body = (await req.json()) as VisitBody;
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  if (!body.path) {
    return NextResponse.json({ error: "path required" }, { status: 400 });
  }

  const utm = body.utm ?? {};

  await prisma.visitEvent.create({
    data: {
      path: body.path,
      sessionId: body.sessionId,
      leadId: body.leadId,
      utmSource: utm.utm_source,
      utmMedium: utm.utm_medium,
      utmCampaign: utm.utm_campaign,
      utmContent: utm.utm_content,
      ref: utm.ref,
    },
  });

  return NextResponse.json({ ok: true });
}
