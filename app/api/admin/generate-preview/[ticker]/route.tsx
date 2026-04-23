import { ImageResponse } from "next/og";

import { prisma } from "@/lib/prisma";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function normalizeTicker(value: string) {
  return value.trim().toUpperCase();
}

export async function GET(_: Request, context: { params: { ticker: string } }) {
  const ticker = normalizeTicker(context.params.ticker);
  const latest = await prisma.analysisHistory.findFirst({
    where: {
      ticker,
      status: "COMPLETED"
    },
    orderBy: {
      completedAt: "desc"
    },
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
          padding: "54px 62px",
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
            padding: "36px 40px"
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div style={{ display: "flex", flexDirection: "column" }}>
              <div style={{ fontSize: 18, letterSpacing: 5, color: "#7ce6ab" }}>SENTINEL AI</div>
              <div style={{ fontSize: 60, fontWeight: 700, marginTop: 18 }}>{ticker}</div>
            </div>
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                alignItems: "flex-end",
                border: "1px solid rgba(99, 255, 176, 0.22)",
                padding: "18px 24px",
                minWidth: 240
              }}
            >
              <div style={{ fontSize: 14, letterSpacing: 3, color: "#7ce6ab" }}>SENTINEL SCORE</div>
              <div style={{ fontSize: 68, fontWeight: 700, lineHeight: 1.1, marginTop: 12 }}>
                {score ?? "--"}
                <span style={{ fontSize: 28 }}>/100</span>
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
              <div style={{ fontSize: 13, letterSpacing: 3, color: "#79dfa7" }}>RATING</div>
              <div style={{ fontSize: 34, marginTop: 10 }}>{rating}</div>
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
              <div style={{ fontSize: 13, letterSpacing: 3, color: "#f2d27d" }}>RECOMMENDATION</div>
              <div style={{ fontSize: 28, marginTop: 10 }}>{recommendation}</div>
            </div>
          </div>

          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              marginTop: "auto",
              fontSize: 18,
              color: "rgba(236,255,245,0.78)"
            }}
          >
            <div>Mode: {mode}</div>
            <div>Updated: {updatedAt}</div>
            <div>sentinel scorecard / social preview</div>
          </div>
        </div>
      </div>
    ),
    {
      width: 1200,
      height: 630
    }
  );
}
