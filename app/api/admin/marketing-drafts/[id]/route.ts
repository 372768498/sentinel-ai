import { MarketingDraftStatus } from "@prisma/client";
import { NextResponse } from "next/server";
import { z } from "zod";

import { requireAdminRequest } from "@/lib/admin";
import { prisma } from "@/lib/prisma";

export const dynamic = "force-dynamic";

const updateDraftSchema = z.object({
  action: z.enum(["approve", "reject", "mark_posted"]),
  actor: z.string().trim().max(120).optional(),
  reason: z.string().trim().max(1000).optional(),
  externalPostId: z.string().trim().max(200).optional()
});

function updateForAction(input: z.infer<typeof updateDraftSchema>) {
  const now = new Date();

  if (input.action === "approve") {
    return {
      status: MarketingDraftStatus.APPROVED,
      approvedAt: now,
      approvedBy: input.actor,
      rejectedAt: null,
      rejectionReason: null
    };
  }

  if (input.action === "reject") {
    return {
      status: MarketingDraftStatus.REJECTED,
      rejectedAt: now,
      rejectionReason: input.reason ?? "Rejected in dry-run review"
    };
  }

  return {
    status: MarketingDraftStatus.POSTED,
    postedAt: now,
    externalPostId: input.externalPostId
  };
}

export async function PATCH(request: Request, context: { params: Promise<{ id: string }> }) {
  const unauthorized = requireAdminRequest(request);

  if (unauthorized) {
    return unauthorized;
  }

  const parsed = updateDraftSchema.safeParse(await request.json());

  if (!parsed.success) {
    return NextResponse.json({ error: parsed.error.flatten() }, { status: 400 });
  }

  const { id } = await context.params;
  const draft = await prisma.marketingDraft.update({
    where: {
      id
    },
    data: updateForAction(parsed.data)
  });

  return NextResponse.json({ draft });
}
