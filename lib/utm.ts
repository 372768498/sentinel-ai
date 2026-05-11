export interface UtmParams {
  utm_source?: string;
  utm_medium?: string;
  utm_campaign?: string;
  utm_content?: string;
  ref?: string;
}

const COOKIE_NAME = "s_utm";
const COOKIE_TTL_DAYS = 30;

export function parseUtmFromSearch(search: string): UtmParams {
  const params = new URLSearchParams(search);
  const result: UtmParams = {};
  const src = params.get("utm_source");
  const med = params.get("utm_medium");
  const cmp = params.get("utm_campaign");
  const cnt = params.get("utm_content");
  const ref = params.get("ref");
  if (src) result.utm_source = src;
  if (med) result.utm_medium = med;
  if (cmp) result.utm_campaign = cmp;
  if (cnt) result.utm_content = cnt;
  if (ref) result.ref = ref;
  return result;
}

export function persistUtm(utm: UtmParams): void {
  if (typeof document === "undefined") return;
  if (!Object.values(utm).some(Boolean)) return;
  const expires = new Date();
  expires.setDate(expires.getDate() + COOKIE_TTL_DAYS);
  document.cookie = `${COOKIE_NAME}=${encodeURIComponent(JSON.stringify(utm))}; expires=${expires.toUTCString()}; path=/; SameSite=Lax`;
}

export function readUtmCookie(): UtmParams {
  if (typeof document === "undefined") return {};
  const match = document.cookie.match(new RegExp(`(?:^|; )${COOKIE_NAME}=([^;]*)`));
  if (!match) return {};
  try {
    return JSON.parse(decodeURIComponent(match[1])) as UtmParams;
  } catch {
    return {};
  }
}

export function mergeUtm(fromSearch: UtmParams, fromCookie: UtmParams): UtmParams {
  return { ...fromCookie, ...fromSearch };
}
