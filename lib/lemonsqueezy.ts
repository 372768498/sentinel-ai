import crypto from "node:crypto";

import { SubscriptionPlan, SubscriptionState } from "@prisma/client";

import { appEnv, assertServerEnv } from "@/lib/env";
import { prisma } from "@/lib/prisma";

export type LemonCheckoutInput = {
  email: string;
  userId: string;
};

type LemonWebhookPayload = {
  meta?: {
    event_name?: string;
    custom_data?: Record<string, unknown>;
    test_mode?: boolean;
  };
  data?: {
    id?: string;
    attributes?: Record<string, unknown>;
    test_mode?: boolean;
  };
};

function asRecord(value: unknown): Record<string, unknown> | undefined {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return undefined;
  }

  return value as Record<string, unknown>;
}

function pickString(...values: unknown[]): string | undefined {
  for (const value of values) {
    if (typeof value === "string" && value.trim()) {
      return value.trim();
    }

    if (typeof value === "number" && Number.isFinite(value)) {
      return String(value);
    }
  }

  return undefined;
}

function pickBoolean(...values: unknown[]): boolean | null {
  for (const value of values) {
    if (typeof value === "boolean") {
      return value;
    }
  }

  return null;
}

function isExpectedWebhookMode(payload: LemonWebhookPayload) {
  const testMode = pickBoolean(payload.meta?.test_mode, payload.data?.test_mode, payload.data?.attributes?.test_mode);

  if (testMode === null) {
    return true;
  }

  return appEnv.lemonMode === "test" ? testMode : !testMode;
}

async function resolveWebhookUser(userId: string | undefined, email: string | undefined) {
  if (userId) {
    const user = await prisma.user.findUnique({
      where: {
        id: userId
      },
      include: {
        subscription: true
      }
    });

    if (user) {
      return user;
    }
  }

  if (!email) {
    return null;
  }

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

export async function createLemonCheckout(input: LemonCheckoutInput) {
  if (!appEnv.lemonApiKey || !appEnv.lemonStoreId || !appEnv.lemonVariantId) {
    if (appEnv.fallbackCheckoutUrl) {
      return { url: appEnv.fallbackCheckoutUrl };
    }

    throw new Error("Lemon Squeezy is not configured.");
  }

  const response = await fetch("https://api.lemonsqueezy.com/v1/checkouts", {
    method: "POST",
    headers: {
      Accept: "application/vnd.api+json",
      "Content-Type": "application/vnd.api+json",
      Authorization: `Bearer ${assertServerEnv("LEMON_SQUEEZY_API_KEY", appEnv.lemonApiKey)}`
    },
    body: JSON.stringify({
      data: {
        type: "checkouts",
        attributes: {
          checkout_options: {
            embed: false,
            media: false,
            logo: false,
            dark: true
          },
          checkout_data: {
            email: input.email,
            custom: {
              user_id: input.userId,
              user_email: input.email
            }
          },
          product_options: {
            redirect_url: `${appEnv.appUrl}?upgraded=1`
          }
        },
        relationships: {
          store: {
            data: {
              type: "stores",
              id: appEnv.lemonStoreId
            }
          },
          variant: {
            data: {
              type: "variants",
              id: appEnv.lemonVariantId
            }
          }
        }
      }
    })
  });

  if (!response.ok) {
    throw new Error(`Failed to create Lemon Squeezy checkout: ${response.status} ${await response.text()}`);
  }

  const payload = await response.json();
  const url = payload?.data?.attributes?.url as string | undefined;

  if (!url) {
    throw new Error("Checkout URL missing from Lemon Squeezy response.");
  }

  return { url };
}

export function verifyLemonSignature(rawBody: string, signature: string | null) {
  const secret = assertServerEnv("LEMON_SQUEEZY_WEBHOOK_SECRET", appEnv.lemonWebhookSecret);
  const digest = crypto.createHmac("sha256", secret).update(rawBody).digest("hex").toLowerCase();
  const digestBuffer = Buffer.from(digest, "utf8");
  const signatureBuffer = Buffer.from((signature ?? "").trim().toLowerCase(), "utf8");

  if (digestBuffer.length !== signatureBuffer.length) {
    return false;
  }

  return crypto.timingSafeEqual(digestBuffer, signatureBuffer);
}

function mapSubscriptionState(status?: string | null, eventName?: string | null): SubscriptionState {
  const normalized = (status ?? "").toLowerCase();
  const normalizedEvent = (eventName ?? "").toLowerCase();

  if (normalizedEvent === "subscription_payment_failed") {
    return SubscriptionState.PAST_DUE;
  }

  if (normalizedEvent === "subscription_cancelled") {
    return SubscriptionState.CANCELED;
  }

  if (normalizedEvent === "subscription_expired") {
    return SubscriptionState.EXPIRED;
  }

  if (normalized.includes("active") || normalized.includes("trial") || normalized === "on_trial") {
    return SubscriptionState.ACTIVE;
  }

  if (normalized.includes("past_due") || normalized.includes("unpaid")) {
    return SubscriptionState.PAST_DUE;
  }

  if (normalized.includes("cancel")) {
    return SubscriptionState.CANCELED;
  }

  if (normalized.includes("expired")) {
    return SubscriptionState.EXPIRED;
  }

  return SubscriptionState.INACTIVE;
}

export async function syncSubscriptionFromWebhook(payload: LemonWebhookPayload) {
  if (!isExpectedWebhookMode(payload)) {
    return {
      ignored: true,
      reason: `Webhook mode does not match configured app mode (${appEnv.lemonMode}).`
    };
  }

  const eventName = payload.meta?.event_name ?? null;
  const attrs = asRecord(payload.data?.attributes) ?? {};
  const customData = asRecord(payload.meta?.custom_data) ?? {};
  const firstSubscriptionItem = asRecord(attrs.first_subscription_item) ?? {};
  const userId = pickString(customData.user_id, customData.userId);
  const email = pickString(
    attrs.user_email,
    attrs.customer_email,
    customData.user_email,
    customData.userEmail
  );

  const user = await resolveWebhookUser(userId, email);

  if (!user) {
    return {
      ignored: true,
      reason: "Webhook payload did not contain a known user reference."
    };
  }

  const state = mapSubscriptionState(attrs.status as string | undefined, eventName);
  const subscriptionId = pickString(payload.data?.id);
  const variantId = pickString(attrs.variant_id, firstSubscriptionItem.variant_id) ?? "";
  const keepsExistingProSubscription =
    Boolean(subscriptionId) &&
    subscriptionId === user.subscription?.lemonSubscriptionId &&
    user.subscription?.plan === SubscriptionPlan.PRO;
  const plan =
    variantId === appEnv.lemonVariantId || keepsExistingProSubscription
      ? SubscriptionPlan.PRO
      : SubscriptionPlan.FREE;

  return prisma.subscriptionStatus.upsert({
    where: {
      userId: user.id
    },
    update: {
      plan,
      state,
      lemonCustomerId: attrs.customer_id ? String(attrs.customer_id) : undefined,
      lemonOrderId: attrs.order_id ? String(attrs.order_id) : undefined,
      lemonSubscriptionId: subscriptionId ?? user.subscription?.lemonSubscriptionId,
      lemonVariantId: variantId || undefined,
      renewsAt: attrs.renews_at ? new Date(String(attrs.renews_at)) : null,
      endsAt: attrs.ends_at ? new Date(String(attrs.ends_at)) : null,
      lastWebhookEvent: eventName ?? undefined
    },
    create: {
      userId: user.id,
      plan,
      state,
      lemonCustomerId: attrs.customer_id ? String(attrs.customer_id) : undefined,
      lemonOrderId: attrs.order_id ? String(attrs.order_id) : undefined,
      lemonSubscriptionId: subscriptionId,
      lemonVariantId: variantId || undefined,
      renewsAt: attrs.renews_at ? new Date(String(attrs.renews_at)) : null,
      endsAt: attrs.ends_at ? new Date(String(attrs.ends_at)) : null,
      lastWebhookEvent: eventName ?? undefined
    }
  });
}
