import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

interface CaptureBody {
  email: string;
  ticker?: string;
  sourcePath?: string;
  utm?: {
    utm_source?: string;
    utm_medium?: string;
    utm_campaign?: string;
    utm_content?: string;
    ref?: string;
  };
}

export async function POST(req: NextRequest) {
  let body: CaptureBody;
  try {
    body = (await req.json()) as CaptureBody;
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const email = body.email?.trim().toLowerCase();
  if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    return NextResponse.json({ error: "Valid email required" }, { status: 400 });
  }

  const utm = body.utm ?? {};

  try {
    const lead = await prisma.emailLead.upsert({
      where: { email_ticker: { email, ticker: body.ticker ?? "" } },
      create: {
        email,
        ticker: body.ticker,
        sourcePath: body.sourcePath,
        utmSource: utm.utm_source,
        utmMedium: utm.utm_medium,
        utmCampaign: utm.utm_campaign,
        utmContent: utm.utm_content,
        ref: utm.ref,
      },
      update: {
        sourcePath: body.sourcePath ?? undefined,
        utmSource: utm.utm_source ?? undefined,
        utmMedium: utm.utm_medium ?? undefined,
        utmCampaign: utm.utm_campaign ?? undefined,
        utmContent: utm.utm_content ?? undefined,
        ref: utm.ref ?? undefined,
        updatedAt: new Date(),
      },
    });

    return NextResponse.json({ ok: true, leadId: lead.id });
  } catch (err) {
    console.error("[leads/capture]", err);
    return NextResponse.json({ error: "Internal error" }, { status: 500 });
  }
}
