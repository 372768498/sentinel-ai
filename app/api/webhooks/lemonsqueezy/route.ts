import { NextResponse } from "next/server";

import { syncSubscriptionFromWebhook, verifyLemonSignature } from "@/lib/lemonsqueezy";

export async function POST(request: Request) {
  try {
    const rawBody = await request.text();
    const signature = request.headers.get("x-signature");

    if (!verifyLemonSignature(rawBody, signature)) {
      return NextResponse.json({ error: "Invalid signature" }, { status: 401 });
    }

    const payload = JSON.parse(rawBody);
    const result = await syncSubscriptionFromWebhook(payload);

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
