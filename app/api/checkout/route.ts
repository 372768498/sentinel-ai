import { NextResponse } from "next/server";
import { z } from "zod";

import { getOrCreateUser, normalizeEmail } from "@/lib/analysis";
import { appEnv } from "@/lib/env";

const checkoutSchema = z.object({
  email: z.string().email().optional()
});

function buildCheckoutUrl(baseUrl: string, params: Record<string, string>) {
  try {
    const url = new URL(baseUrl);
    for (const [key, value] of Object.entries(params)) {
      if (value) url.searchParams.set(key, value);
    }
    return url.toString();
  } catch {
    return baseUrl;
  }
}

export async function POST(request: Request) {
  try {
    if (!appEnv.whopCheckoutUrlPro) {
      return NextResponse.json(
        { error: "Whop checkout URL is not configured." },
        { status: 500 }
      );
    }

    const payload = checkoutSchema.parse(await request.json().catch(() => ({})));
    const email = normalizeEmail(payload.email ?? "guest@example.com");
    const user = await getOrCreateUser(email);

    const url = buildCheckoutUrl(appEnv.whopCheckoutUrlPro, {
      email,
      metadata_user_id: user.id,
      metadata_user_email: email
    });

    return NextResponse.json({
      url,
      mode: "redirect"
    });
  } catch (error) {
    return NextResponse.json(
      {
        error: error instanceof Error ? error.message : "Checkout creation failed"
      },
      { status: 500 }
    );
  }
}
