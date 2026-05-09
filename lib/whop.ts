import crypto from "node:crypto";

import { SubscriptionPlan, SubscriptionState } from "@prisma/client";

import { appEnv, assertServerEnv } from "@/lib/env";
import { prisma } from "@/lib/prisma";
import { createVipInviteLink } from "@/lib/telegram";

type WhopWebhookData = {
  id?: string;
  product?: string;
  product_id?: string;
  plan?: string;
  plan_id?: string;
  user?: string | { id?: string; email?: string; username?: string };
  user_id?: string;
  email?: string;
  user_email?: string;
  status?: string;
  valid?: boolean;
  renewal_period_end?: number | string | null;
  expires_at?: number | string | null;
  metadata?: Record<string, unknown>;
};

type WhopWebhookPayload = {
  action?: string;
  event?: string;
  type?: string;
  data?: WhopWebhookData;
};

function asString(value: unknown): string | undefined {
  if (typeof value === "string" && value.trim()) {
    return value.trim();
  }
  if (typeof value === "number" && Number.isFinite(value)) {
    return String(value);
  }
  return undefined;
}

function asEpochDate(value: unknown): Date | null {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  const numeric = typeof value === "number" ? value : Number(value);
  if (Number.isFinite(numeric)) {
    const ms = numeric > 1e12 ? numeric : numeric * 1000;
    return new Date(ms);
  }
  if (typeof value === "string") {
    const parsed = Date.parse(value);
    return Number.isNaN(parsed) ? null : new Date(parsed);
  }
  return null;
}

function extractSignatureHex(header: string | null): string {
  if (!header) return "";
  const trimmed = header.trim();
  const v1Match = trimmed.match(/v1=([a-f0-9]+)/i);
  if (v1Match) return v1Match[1].toLowerCase();
  const sha256Match = trimmed.match(/sha256=([a-f0-9]+)/i);
  if (sha256Match) return sha256Match[1].toLowerCase();
  return trimmed.toLowerCase();
}

export function verifyWhopSignature(rawBody: string, signatureHeader: string | null): boolean {
  const secret = assertServerEnv("WHOP_WEBHOOK_SECRET", appEnv.whopWebhookSecret);
  const provided = extractSignatureHex(signatureHeader);

  if (!provided) return false;

  const digest = crypto.createHmac("sha256", secret).update(rawBody).digest("hex").toLowerCase();
  const digestBuffer = Buffer.from(digest, "utf8");
  const providedBuffer = Buffer.from(provided, "utf8");

  if (digestBuffer.length !== providedBuffer.length) return false;

  return crypto.timingSafeEqual(digestBuffer, providedBuffer);
}

function mapEventToState(action: string | undefined, status: string | undefined, valid: boolean | undefined): SubscriptionState {
  const ev = (action ?? "").toLowerCase();
  const st = (status ?? "").toLowerCase();

  if (ev.includes("went_valid") || valid === true || st === "active" || st === "completed" || st === "trialing") {
    return SubscriptionState.ACTIVE;
  }
  if (ev.includes("went_invalid") || valid === false) {
    if (st.includes("past_due") || st.includes("unpaid")) return SubscriptionState.PAST_DUE;
    if (st.includes("expired")) return SubscriptionState.EXPIRED;
    if (st.includes("cancel")) return SubscriptionState.CANCELED;
    return SubscriptionState.INACTIVE;
  }
  if (ev.includes("payment_failed") || st.includes("past_due") || st.includes("unpaid")) {
    return SubscriptionState.PAST_DUE;
  }
  if (ev.includes("cancelled") || ev.includes("canceled") || st.includes("cancel")) {
    return SubscriptionState.CANCELED;
  }
  if (ev.includes("expired") || st.includes("expired")) {
    return SubscriptionState.EXPIRED;
  }
  return SubscriptionState.INACTIVE;
}

function extractEmail(data: WhopWebhookData): string | undefined {
  if (typeof data.user === "object" && data.user) {
    const fromUser = asString(data.user.email);
    if (fromUser) return fromUser.toLowerCase();
  }
  return (
    asString(data.user_email)?.toLowerCase() ??
    asString(data.email)?.toLowerCase()
  );
}

function extractWhopUserId(data: WhopWebhookData): string | undefined {
  if (typeof data.user === "string") return asString(data.user);
  if (typeof data.user === "object" && data.user) {
    const id = asString(data.user.id);
    if (id) return id;
  }
  return asString(data.user_id);
}

async function resolveUser(email: string | undefined) {
  if (!email) return null;

  return prisma.user.upsert({
    where: { email },
    update: {},
    create: {
      email,
      subscription: {
        create: {
          plan: SubscriptionPlan.FREE,
          state: SubscriptionState.INACTIVE
        }
      }
    },
    include: { subscription: true }
  });
}

export async function syncSubscriptionFromWhop(payload: WhopWebhookPayload) {
  const action = payload.action ?? payload.event ?? payload.type;
  const data = payload.data ?? {};
  const email = extractEmail(data);
  const user = await resolveUser(email);

  if (!user) {
    return { ignored: true, reason: "Webhook payload did not contain a recognizable user email." };
  }

  const productId = asString(data.product_id) ?? asString(data.product);
  const planId = asString(data.plan_id) ?? asString(data.plan);
  const membershipId = asString(data.id);
  const whopUserId = extractWhopUserId(data);
  const state = mapEventToState(action, data.status, data.valid);

  const isProProduct =
    productId === appEnv.whopProductIdPro ||
    planId === appEnv.whopPlanIdPro ||
    user.subscription?.plan === SubscriptionPlan.PRO;

  const plan =
    state === SubscriptionState.ACTIVE && isProProduct ? SubscriptionPlan.PRO : isProProduct ? SubscriptionPlan.PRO : SubscriptionPlan.FREE;

  const renewsAt = asEpochDate(data.renewal_period_end);
  const endsAt = asEpochDate(data.expires_at);

  const previousPlan = user.subscription?.plan ?? SubscriptionPlan.FREE;
  const previousState = user.subscription?.state ?? SubscriptionState.INACTIVE;
  const justActivated =
    plan === SubscriptionPlan.PRO &&
    state === SubscriptionState.ACTIVE &&
    !(previousPlan === SubscriptionPlan.PRO && previousState === SubscriptionState.ACTIVE);

  let telegramInviteLink = user.subscription?.telegramInviteLink ?? null;

  if (justActivated && appEnv.telegramBotToken && appEnv.telegramGroupIdVip) {
    try {
      const link = await createVipInviteLink({
        memberLimit: 1,
        name: `pro-${user.id}-${Date.now()}`
      });
      telegramInviteLink = link.inviteLink;
    } catch (error) {
      console.error("[whop] Failed to create Telegram VIP invite link:", error);
    }
  }

  const subscription = await prisma.subscriptionStatus.upsert({
    where: { userId: user.id },
    update: {
      plan,
      state,
      whopUserId: whopUserId ?? undefined,
      whopMembershipId: membershipId ?? user.subscription?.whopMembershipId ?? undefined,
      whopProductId: productId ?? undefined,
      whopPlanId: planId ?? undefined,
      renewsAt,
      endsAt,
      lastWebhookEvent: action ?? undefined,
      telegramInviteLink: telegramInviteLink ?? undefined
    },
    create: {
      userId: user.id,
      plan,
      state,
      whopUserId: whopUserId ?? undefined,
      whopMembershipId: membershipId ?? undefined,
      whopProductId: productId ?? undefined,
      whopPlanId: planId ?? undefined,
      renewsAt,
      endsAt,
      lastWebhookEvent: action ?? undefined,
      telegramInviteLink: telegramInviteLink ?? undefined
    }
  });

  return {
    ok: true,
    action,
    plan: subscription.plan,
    state: subscription.state,
    inviteLinkIssued: justActivated && Boolean(telegramInviteLink)
  };
}
