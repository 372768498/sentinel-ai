import { ImageResponse } from "next/og";

import { prisma } from "@/lib/prisma";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const VARIANTS = {
  x_post: { width: 1200, height: 675, label: "x feed card" },
  reddit_card: { width: 1200, height: 630, label: "reddit thumbnail" },
  telegram_inline: { width: 800, height: 418, label: "telegram link preview" }
} as const;

type VariantKey = keyof typeof VARIANTS;

const TICKER_PATTERN = /^[A-Z][A-Z0-9.\-]{0,9}$/;

function normalizeTicker(value: string) {
  return value.trim().toUpperCase();
}

function pickVariant(value: string | null): VariantKey {
  if (value && value in VARIANTS) {
    return value as VariantKey;
  }
  return "x_post";
}

export async function GET(request: Request, context: { params: Promise<{ ticker: string }> }) {
  const { ticker: tickerParam } = await context.params;
  const ticker = normalizeTicker(tickerParam);
  if (!TICKER_PATTERN.test(ticker)) {
    return new Response("invalid ticker", { status: 400 });
  }

  const url = new URL(request.url);
  const variantKey = pickVariant(url.searchParams.get("variant"));
  const { width, height, label } = VARIANTS[variantKey];

  const latest = await prisma.analysisHistory.findFirst({
    where: { ticker, status: "COMPLETED" },
    orderBy: { completedAt: "desc" },
    select: {
      finalScore: true,
      rating: true,
      recommendation: true,
      requestedMode: true,
      completedAt: true,
      resultJson: true
    }
  });

  const score =
    latest?.finalScore ??
    (typeof latest?.resultJson === "object" &&
    latest.resultJson &&
    "score_100" in latest.resultJson &&
    typeof latest.resultJson.score_100 === "number"
      ? latest.resultJson.score_100
      : null);
  const rating = latest?.rating ?? "Pending";
  const recommendation = latest?.recommendation ?? "Awaiting completed analysis";
  const mode = latest?.requestedMode ?? "BASIC";
  const updatedAt = latest?.completedAt
    ? new Intl.DateTimeFormat("en-US", {
        year: "numeric",
        month: "short",
        day: "2-digit"
      }).format(latest.completedAt)
    : "No completed run yet";

  const tickerSize = Math.round(width * 0.05);
  const scoreSize = Math.round(width * 0.057);
  const ratingSize = Math.round(width * 0.028);
  const recoSize = Math.round(width * 0.023);
  const padding = Math.round(width * 0.045);

  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          background:
            "radial-gradient(circle at top left, rgba(33,209,126,0.2), transparent 32%), linear-gradient(135deg, #07120d 0%, #091814 45%, #03100c 100%)",
          color: "#ecfff5",
          padding,
          fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace"
        }}
      >
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            width: "100%",
            border: "1px solid rgba(99, 255, 176, 0.18)",
            background: "rgba(5, 12, 9, 0.86)",
            padding: `${Math.round(padding * 0.7)}px ${Math.round(padding * 0.8)}px`
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div style={{ display: "flex", flexDirection: "column" }}>
              <div style={{ fontSize: Math.round(width * 0.015), letterSpacing: 5, color: "#7ce6ab" }}>
                SENTINEL AI · {label.toUpperCase()}
              </div>
              <div style={{ fontSize: tickerSize, fontWeight: 700, marginTop: 18 }}>{ticker}</div>
            </div>
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                alignItems: "flex-end",
                border: "1px solid rgba(99, 255, 176, 0.22)",
                padding: "18px 24px",
                minWidth: Math.round(width * 0.2)
              }}
            >
              <div style={{ fontSize: Math.round(width * 0.012), letterSpacing: 3, color: "#7ce6ab" }}>
                SENTINEL SCORE
              </div>
              <div style={{ fontSize: scoreSize, fontWeight: 700, lineHeight: 1.1, marginTop: 12 }}>
                {score ?? "--"}
                <span style={{ fontSize: Math.round(scoreSize * 0.41) }}>/100</span>
              </div>
            </div>
          </div>

          <div style={{ display: "flex", gap: 24, marginTop: 34 }}>
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                flex: 1,
                border: "1px solid rgba(99, 255, 176, 0.18)",
                padding: "20px 22px",
                background: "rgba(5, 10, 8, 0.7)"
              }}
            >
              <div style={{ fontSize: Math.round(width * 0.011), letterSpacing: 3, color: "#79dfa7" }}>
                RATING
              </div>
              <div style={{ fontSize: ratingSize, marginTop: 10 }}>{rating}</div>
            </div>
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                flex: 1.4,
                border: "1px solid rgba(255, 205, 84, 0.2)",
                padding: "20px 22px",
                background: "rgba(18, 14, 6, 0.55)"
              }}
            >
              <div style={{ fontSize: Math.round(width * 0.011), letterSpacing: 3, color: "#f2d27d" }}>
                SENTINEL STATE
              </div>
              <div style={{ fontSize: recoSize, marginTop: 10 }}>{recommendation}</div>
            </div>
          </div>

          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              marginTop: "auto",
              fontSize: Math.round(width * 0.015),
              color: "rgba(236,255,245,0.78)"
            }}
          >
            <div>Mode: {mode}</div>
            <div>Updated: {updatedAt}</div>
            <div>Context, not advice.</div>
          </div>
        </div>
      </div>
    ),
    {
      width,
      height
    }
  );
}
