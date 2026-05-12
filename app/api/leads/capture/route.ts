import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

interface CaptureBody {
  email: string;
  ticker?: string;
  sourcePath?: string;
  /** Up to 3 user-chosen seed tickers from the registration step 2.
   * Each must match /^[A-Z]{1,5}$/ — anything that doesn't is silently
   * dropped server-side so the form's optimistic uppercase + slice can
   * be naive on the client. */
  seedTickers?: string[];
  utm?: {
    utm_source?: string;
    utm_medium?: string;
    utm_campaign?: string;
    utm_content?: string;
    ref?: string;
  };
}

const SEED_TICKER_RE = /^[A-Z]{1,5}$/;
const MAX_SEED_TICKERS = 3;

function sanitiseSeedTickers(input: unknown): string[] {
  if (!Array.isArray(input)) return [];
  const cleaned: string[] = [];
  for (const raw of input) {
    if (typeof raw !== "string") continue;
    const upper = raw.trim().toUpperCase();
    if (!SEED_TICKER_RE.test(upper)) continue;
    if (cleaned.includes(upper)) continue; // dedupe
    cleaned.push(upper);
    if (cleaned.length >= MAX_SEED_TICKERS) break;
  }
  return cleaned;
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
  const seedTickers = sanitiseSeedTickers(body.seedTickers);
  const seedTickersAddedAt = seedTickers.length > 0 ? new Date() : undefined;

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
        seedTickers,
        seedTickersAddedAt,
      },
      update: {
        sourcePath: body.sourcePath ?? undefined,
        utmSource: utm.utm_source ?? undefined,
        utmMedium: utm.utm_medium ?? undefined,
        utmCampaign: utm.utm_campaign ?? undefined,
        utmContent: utm.utm_content ?? undefined,
        ref: utm.ref ?? undefined,
        // Only overwrite seedTickers when the new payload supplied any;
        // an empty array from "Skip" preserves the user's earlier picks.
        ...(seedTickers.length > 0
          ? { seedTickers, seedTickersAddedAt }
          : {}),
        updatedAt: new Date(),
      },
    });

    return NextResponse.json({
      ok: true,
      leadId: lead.id,
      seedTickersSaved: seedTickers.length,
    });
  } catch (err) {
    console.error("[leads/capture]", err);
    return NextResponse.json({ error: "Internal error" }, { status: 500 });
  }
}
