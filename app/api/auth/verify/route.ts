import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

const PUBLIC_URL = process.env.GROWTH_OS_PUBLIC_URL ?? process.env.NEXT_PUBLIC_APP_URL ?? "http://localhost:3000";

export async function GET(req: NextRequest) {
  const token = req.nextUrl.searchParams.get("token");
  if (!token) {
    return NextResponse.redirect(`${PUBLIC_URL}/?auth=missing_token`);
  }

  const lead = await prisma.emailLead.findUnique({ where: { magicToken: token } });

  if (!lead || !lead.magicTokenExpiresAt || lead.magicTokenExpiresAt < new Date()) {
    return NextResponse.redirect(`${PUBLIC_URL}/?auth=invalid_or_expired`);
  }

  await prisma.emailLead.update({
    where: { id: lead.id },
    data: { verifiedAt: new Date(), magicToken: null, magicTokenExpiresAt: null },
  });

  const redirect = lead.ticker
    ? `${PUBLIC_URL}/stocks/${lead.ticker}?verified=1`
    : `${PUBLIC_URL}/?verified=1`;

  return NextResponse.redirect(redirect);
}
