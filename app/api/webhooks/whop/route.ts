import { NextResponse } from "next/server";

import { syncSubscriptionFromWhop, verifyWhopSignature } from "@/lib/whop";

export async function POST(request: Request) {
  try {
    const rawBody = await request.text();
    const signature =
      request.headers.get("x-whop-signature") ??
      request.headers.get("whop-signature") ??
      request.headers.get("x-signature");

    if (!verifyWhopSignature(rawBody, signature)) {
      return NextResponse.json({ error: "Invalid signature" }, { status: 401 });
    }

    const payload = JSON.parse(rawBody);
    const result = await syncSubscriptionFromWhop(payload);

    return NextResponse.json({ ok: true, ...result });
  } catch (error) {
    return NextResponse.json(
      {
        error: error instanceof Error ? error.message : "Webhook processing failed"
      },
      { status: 400 }
    );
  }
}
