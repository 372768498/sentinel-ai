import { NextRequest, NextResponse } from "next/server";
import { randomBytes } from "crypto";
import { prisma } from "@/lib/prisma";

const TOKEN_TTL_HOURS = 24;
const FROM = process.env.RESEND_FROM_EMAIL ?? "Sentinel AI <noreply@example.com>";
const PUBLIC_URL = process.env.GROWTH_OS_PUBLIC_URL ?? process.env.NEXT_PUBLIC_APP_URL ?? "http://localhost:3000";

async function sendMagicLinkEmail(to: string, link: string): Promise<void> {
  const apiKey = process.env.RESEND_API_KEY;
  if (!apiKey) {
    console.warn("[magic-link] RESEND_API_KEY not set — skipping email send");
    return;
  }

  const res = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      from: FROM,
      to,
      subject: "Your Sentinel AI report link",
      html: `
        <p>Hi,</p>
        <p>Here is your link to access your Sentinel AI stock report:</p>
        <p><a href="${link}">${link}</a></p>
        <p>This link expires in ${TOKEN_TTL_HOURS} hours.</p>
        <p style="color:#888;font-size:12px">Context, not financial advice.</p>
      `,
    }),
  });

  if (!res.ok) {
    const text = await res.text();
    console.error("[magic-link] Resend error:", text);
  }
}

export async function POST(req: NextRequest) {
  let body: { email?: string };
  try {
    body = (await req.json()) as { email?: string };
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const email = body.email?.trim().toLowerCase();
  if (!email) {
    return NextResponse.json({ error: "Email required" }, { status: 400 });
  }

  const token = randomBytes(32).toString("hex");
  const expires = new Date(Date.now() + TOKEN_TTL_HOURS * 60 * 60 * 1000);

  await prisma.emailLead.upsert({
    where: { email_ticker: { email, ticker: "" } },
    create: { email, ticker: "", magicToken: token, magicTokenExpiresAt: expires },
    update: { magicToken: token, magicTokenExpiresAt: expires, updatedAt: new Date() },
  });

  const verifyUrl = `${PUBLIC_URL}/api/auth/verify?token=${token}`;
  await sendMagicLinkEmail(email, verifyUrl);

  return NextResponse.json({ ok: true });
}
