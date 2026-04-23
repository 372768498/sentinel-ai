import { NextResponse } from "next/server";
import { z } from "zod";

import { getOrCreateUser, normalizeEmail } from "@/lib/analysis";
import { createLemonCheckout } from "@/lib/lemonsqueezy";

const checkoutSchema = z.object({
  email: z.string().email().optional()
});

export async function POST(request: Request) {
  try {
    const payload = checkoutSchema.parse(await request.json().catch(() => ({})));
    const email = normalizeEmail(payload.email ?? "guest@example.com");
    const user = await getOrCreateUser(email);
    const checkout = await createLemonCheckout({
      email,
      userId: user.id
    });

    return NextResponse.json({
      ...checkout,
      mode: "overlay"
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
