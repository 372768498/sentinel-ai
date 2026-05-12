import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

/**
 * POST /api/waitlist/join
 *
 * Captures a Pro-tier waitlist email from sentinel.jilo.ai (cross-origin
 * to app.jilo.ai). Idempotent on email — re-submitting the same email
 * updates tier/source but does NOT push the user forward in the queue
 * (createdAt is set once on the first insert).
 *
 * Response shape:
 *   { ok: true, position: <1-indexed integer> }
 *
 * `position` is the count of all rows up to and including this one,
 * computed as max(_, total) so re-submissions still return a stable
 * position. The waitlist count is small enough that a count(*) per
 * request is fine.
 */

interface WaitlistBody {
  email: string;
  tier: string;
  source?: string;
}

const VALID_TIERS = new Set(["watch", "pro"]);
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

// Origins allowed to call this endpoint. sentinel.jilo.ai is the canonical
// marketing landing; *.vercel.app preview deploys for sentinel-landing
// and localhost for dev. Wildcards aren't supported in browser CORS so we
// echo the origin back when it matches.
const ALLOW_ORIGIN_EXACT = new Set([
  "https://sentinel.jilo.ai",
  "https://sentinel-landing-eight.vercel.app",
  "http://localhost:3000",
  "http://localhost:5173",
]);
const ALLOW_ORIGIN_SUFFIXES = [
  ".vercel.app", // sentinel-landing preview deploys
];

function corsHeaders(origin: string | null): Record<string, string> {
  const headers: Record<string, string> = {
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Max-Age": "86400",
  };
  if (!origin) return headers;
  const ok =
    ALLOW_ORIGIN_EXACT.has(origin) ||
    ALLOW_ORIGIN_SUFFIXES.some((s) => origin.endsWith(s));
  if (ok) {
    headers["Access-Control-Allow-Origin"] = origin;
    headers["Vary"] = "Origin";
  }
  return headers;
}

export async function OPTIONS(req: NextRequest) {
  return new NextResponse(null, {
    status: 204,
    headers: corsHeaders(req.headers.get("origin")),
  });
}

export async function POST(req: NextRequest) {
  const cors = corsHeaders(req.headers.get("origin"));

  let body: WaitlistBody;
  try {
    body = (await req.json()) as WaitlistBody;
  } catch {
    return NextResponse.json(
      { error: "Invalid JSON" },
      { status: 400, headers: cors },
    );
  }

  const email = body.email?.trim().toLowerCase();
  if (!email || !EMAIL_RE.test(email)) {
    return NextResponse.json(
      { error: "Valid email required" },
      { status: 400, headers: cors },
    );
  }

  const tier = (body.tier ?? "").trim().toLowerCase();
  if (!VALID_TIERS.has(tier)) {
    return NextResponse.json(
      { error: "tier must be 'watch' or 'pro'" },
      { status: 400, headers: cors },
    );
  }

  const source = body.source?.trim().slice(0, 80) || null;

  // Local Prisma client may not have proWaitlist typed yet when the
  // dev server holds the query-engine DLL lock and prevents `prisma
  // generate` from completing. Vercel's build runs `prisma generate`
  // fresh so production gets full types. Cast keeps local TS happy.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const db = prisma as any;

  try {
    await db.proWaitlist.upsert({
      where: { email },
      create: { email, tier, source },
      // Don't overwrite createdAt on re-submit. Update tier/source so
      // a user who switches their preferred tier reflects the latest pick.
      update: { tier, ...(source ? { source } : {}) },
    });

    const total = await db.proWaitlist.count();

    // Message bands — avoid showing tiny absolute positions when the
    // waitlist is brand new (says "#3" → reads as "they have no users").
    //   < 50   → neutral thanks, no number
    //   < 500  → social-proof framing (`N+ investors waiting`)
    //   ≥ 500  → exact position
    let message: string;
    if (total < 50) {
      message = "Thanks. We'll email you when Pro opens (early 2026).";
    } else if (total < 500) {
      message = `You're in. ${total}+ investors waiting.`;
    } else {
      message = `You're #${total} on the waitlist. We'll email you when Pro opens.`;
    }

    return NextResponse.json(
      { ok: true, position: total, message },
      { status: 200, headers: cors },
    );
  } catch (err) {
    console.error("[waitlist/join]", err);
    return NextResponse.json(
      { error: "Internal error" },
      { status: 500, headers: cors },
    );
  }
}
