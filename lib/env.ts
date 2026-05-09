const withFallback = (value: string | undefined, fallback: string) => {
  if (!value || !value.trim()) {
    return fallback;
  }

  return value.trim();
};

const toNumber = (value: string | undefined, fallback: number) => {
  if (!value) {
    return fallback;
  }

  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
};

export const appEnv = {
  appUrl: withFallback(process.env.APP_URL ?? process.env.NEXT_PUBLIC_APP_URL, "http://localhost:3000"),
  publicWorkerUrl: withFallback(process.env.NEXT_PUBLIC_WORKER_URL, "http://localhost:8000"),
  workerApiBaseUrl: withFallback(
    process.env.WORKER_API_BASE_URL,
    process.env.NEXT_PUBLIC_WORKER_URL ?? "http://localhost:8000"
  ),
  workerInternalToken: process.env.WORKER_INTERNAL_TOKEN ?? "",
  internalCallbackSecret: process.env.INTERNAL_CALLBACK_SECRET ?? "",

  // Whop
  whopAppId: process.env.WHOP_APP_ID ?? "",
  whopApiKey: process.env.WHOP_API_KEY ?? "",
  whopWebhookSecret: process.env.WHOP_WEBHOOK_SECRET ?? "",
  whopProductIdPro: process.env.WHOP_PRODUCT_ID_PRO ?? "",
  whopPlanIdPro: process.env.WHOP_PLAN_ID_PRO ?? "",
  whopCheckoutUrlPro: process.env.NEXT_PUBLIC_WHOP_CHECKOUT_URL_PRO ?? "",
  proMonthlyPriceUsd: toNumber(process.env.WHOP_PRO_MONTHLY_PRICE_USD, 39),

  // Telegram
  telegramBotToken: process.env.TELEGRAM_BOT_TOKEN ?? "",
  telegramBotUsername: process.env.TELEGRAM_BOT_USERNAME ?? "",
  telegramChannelHandle: process.env.TELEGRAM_CHANNEL_HANDLE ?? "",
  telegramChannelIdPublic: process.env.TELEGRAM_CHANNEL_ID_PUBLIC ?? "",
  telegramFreeUrl: process.env.NEXT_PUBLIC_TELEGRAM_FREE_URL ?? "",
  telegramGroupIdVip: process.env.TELEGRAM_GROUP_ID_VIP ?? "",

  resendFromEmail: process.env.RESEND_FROM_EMAIL ?? "Sentinel AI <briefing@example.com>",
  adminApiKey: process.env.ADMIN_API_KEY ?? process.env.CRON_SECRET ?? "",
  opsAlertWebhookUrl: process.env.OPS_ALERT_WEBHOOK_URL ?? "",
  reapStaleMinutes: toNumber(process.env.REAP_STALE_MINUTES, 45),
  reapAlertFailureRateThreshold: toNumber(process.env.REAP_ALERT_FAILURE_RATE_THRESHOLD, 0.2),

  // Desk (high-end custom service)
  deskPriceUsd: toNumber(process.env.SENTINEL_DESK_PRICE_USD, 24000),
  deskInquiryEmail: process.env.SENTINEL_DESK_INQUIRY_EMAIL ?? ""
};

export function assertServerEnv(name: string, value: string): string {
  if (!value) {
    throw new Error(`Missing required environment variable: ${name}`);
  }

  return value;
}
