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

const normalizedLemonMode = (process.env.LEMON_SQUEEZY_MODE ?? "").trim().toLowerCase();

export const appEnv = {
  appUrl: withFallback(process.env.APP_URL ?? process.env.NEXT_PUBLIC_APP_URL, "http://localhost:3000"),
  publicWorkerUrl: withFallback(process.env.NEXT_PUBLIC_WORKER_URL, "http://localhost:8000"),
  workerApiBaseUrl: withFallback(
    process.env.WORKER_API_BASE_URL,
    process.env.NEXT_PUBLIC_WORKER_URL ?? "http://localhost:8000"
  ),
  workerInternalToken: process.env.WORKER_INTERNAL_TOKEN ?? "",
  internalCallbackSecret: process.env.INTERNAL_CALLBACK_SECRET ?? "",
  lemonApiKey: process.env.LEMON_SQUEEZY_API_KEY ?? "",
  lemonStoreId: process.env.LEMON_SQUEEZY_STORE_ID ?? "",
  lemonVariantId: process.env.LEMON_SQUEEZY_PRO_VARIANT_ID ?? "",
  lemonWebhookSecret: process.env.LEMON_SQUEEZY_WEBHOOK_SECRET ?? "",
  lemonMode: normalizedLemonMode === "live" ? "live" : "test",
  fallbackCheckoutUrl: process.env.NEXT_PUBLIC_LEMON_SQUEEZY_CHECKOUT_URL ?? "",
  resendFromEmail: process.env.RESEND_FROM_EMAIL ?? "Sentinel AI <briefing@example.com>",
  adminApiKey: process.env.ADMIN_API_KEY ?? process.env.CRON_SECRET ?? "",
  opsAlertWebhookUrl: process.env.OPS_ALERT_WEBHOOK_URL ?? "",
  reapStaleMinutes: toNumber(process.env.REAP_STALE_MINUTES, 45),
  reapAlertFailureRateThreshold: toNumber(process.env.REAP_ALERT_FAILURE_RATE_THRESHOLD, 0.2),
  proMonthlyPriceUsd: toNumber(process.env.LEMON_SQUEEZY_PRO_MONTHLY_PRICE_USD, 19.9)
};

export function assertServerEnv(name: string, value: string): string {
  if (!value) {
    throw new Error(`Missing required environment variable: ${name}`);
  }

  return value;
}
