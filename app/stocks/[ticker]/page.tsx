"use client";

import { useEffect, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { scoreToRating, ratingColor, ratingBg } from "@/lib/rating";
import { parseUtmFromSearch, persistUtm, readUtmCookie, mergeUtm, type UtmParams } from "@/lib/utm";

interface DimensionScore {
  name: string;
  score: number;
  blurb: string;
}

interface StockData {
  ticker: string;
  companyName: string;
  totalScore: number;
  dimensions: DimensionScore[];
  riskFlag: string;
}

function getMockData(ticker: string): StockData {
  const t = ticker.toUpperCase();
  return {
    ticker: t,
    companyName: t === "NVDA" ? "NVIDIA Corporation" : `${t} Inc.`,
    totalScore: 78,
    dimensions: [
      { name: "Revenue Growth", score: 88, blurb: "Accelerating data center demand." },
      { name: "Profitability", score: 82, blurb: "Margins expanded year-over-year." },
      { name: "Balance Sheet", score: 79, blurb: "Low debt, strong cash position." },
      { name: "Analyst Sentiment", score: 74, blurb: "Majority maintain positive outlook." },
      { name: "Insider Activity", score: 71, blurb: "Minimal insider selling noted." },
      { name: "Technical Momentum", score: 76, blurb: "Trading above 200-day moving average." },
      { name: "Valuation", score: 62, blurb: "Premium vs. sector median P/E." },
      { name: "Earnings Quality", score: 80, blurb: "High accrual-to-cash ratio." },
      { name: "Competitive Moat", score: 85, blurb: "AI chip leadership position intact." },
      { name: "Regulatory Risk", score: 66, blurb: "Export restrictions under review." },
    ],
    riskFlag: "Export restriction risk may weigh on guidance — monitor Q3 disclosure.",
  };
}

export default function StockPage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const ticker = (params.ticker as string).toUpperCase();

  const [email, setEmail] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [utm, setUtm] = useState<UtmParams>({});

  const data = getMockData(ticker);
  const rating = scoreToRating(data.totalScore);

  useEffect(() => {
    const fromSearch = parseUtmFromSearch(searchParams.toString());
    const fromCookie = readUtmCookie();
    const merged = mergeUtm(fromSearch, fromCookie);
    persistUtm(merged);
    setUtm(merged);

    fetch("/api/track/visit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: `/stocks/${ticker}`, utm: merged }),
    }).catch(() => {});
  }, [ticker, searchParams]);

  async function handleCapture(e: React.FormEvent) {
    e.preventDefault();
    if (!email) return;
    setLoading(true);
    setError("");

    try {
      const res = await fetch("/api/leads/capture", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email,
          ticker,
          sourcePath: `/stocks/${ticker}`,
          utm,
        }),
      });

      if (!res.ok) throw new Error("capture failed");

      await fetch("/api/auth/magic-link", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });

      setSubmitted(true);
    } catch {
      setError("Something went wrong. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  const telegramUrl = process.env.NEXT_PUBLIC_TELEGRAM_FREE_URL ?? "https://t.me/SentinelAI_signals";

  return (
    <main className="min-h-screen bg-neutral-950 text-neutral-100 px-4 py-10 max-w-2xl mx-auto">
      <header className="mb-8">
        <p className="text-xs text-neutral-500 uppercase tracking-widest mb-1">Sentinel AI · Stock Context</p>
        <h1 className="text-3xl font-bold">${ticker}</h1>
        <p className="text-neutral-400 text-sm mt-1">{data.companyName}</p>
      </header>

      {/* Score card */}
      <section className={`rounded-xl border p-6 mb-6 ${ratingBg(rating)}`}>
        <div className="flex items-center justify-between">
          <div>
            <p className="text-xs uppercase tracking-widest text-neutral-400 mb-1">AI Score</p>
            <p className="text-5xl font-black">{data.totalScore}</p>
            <p className={`text-lg font-semibold mt-1 ${ratingColor(rating)}`}>{rating}</p>
          </div>
          <div className="text-right text-xs text-neutral-500">
            <p>10-dimension analysis</p>
            <p className="mt-1">Updated today</p>
          </div>
        </div>
      </section>

      {/* Dimensions preview (visible) */}
      <section className="mb-6">
        <h2 className="text-sm font-semibold text-neutral-400 uppercase tracking-widest mb-3">Dimension Scores</h2>
        <ul className="space-y-2">
          {data.dimensions.map((d) => (
            <li key={d.name} className="flex items-center gap-3">
              <span className="text-sm text-neutral-300 w-40 shrink-0">{d.name}</span>
              <div className="flex-1 bg-neutral-800 rounded-full h-1.5">
                <div
                  className="bg-emerald-500 h-1.5 rounded-full"
                  style={{ width: `${d.score}%` }}
                />
              </div>
              <span className="text-sm font-mono text-neutral-400 w-6 text-right">{d.score}</span>
            </li>
          ))}
        </ul>
      </section>

      {/* Risk flag (visible) */}
      <section className="rounded-lg bg-orange-950 border border-orange-800 p-4 mb-8 text-sm text-orange-200">
        <p className="font-semibold mb-1">Key Risk Flag</p>
        <p>{data.riskFlag}</p>
      </section>

      {/* Email gate */}
      {submitted ? (
        <section className="rounded-xl bg-neutral-900 border border-neutral-700 p-6 text-center">
          <p className="text-emerald-400 font-semibold text-lg mb-2">Check your inbox</p>
          <p className="text-neutral-400 text-sm">
            We sent a link to <strong>{email}</strong>. Click it to unlock the full ${ticker} report.
          </p>
        </section>
      ) : (
        <section className="rounded-xl bg-neutral-900 border border-neutral-700 p-6 mb-6">
          <p className="font-semibold mb-1">Unlock the full 10-dimension report</p>
          <p className="text-neutral-400 text-sm mb-4">
            Get the complete breakdown, risk analysis, and PDF — free.
          </p>
          <form onSubmit={handleCapture} className="flex flex-col sm:flex-row gap-3">
            <input
              type="email"
              required
              placeholder="you@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="flex-1 rounded-lg bg-neutral-800 border border-neutral-700 px-4 py-2.5 text-sm text-white placeholder-neutral-500 outline-none focus:border-emerald-500"
            />
            <button
              type="submit"
              disabled={loading}
              className="rounded-lg bg-emerald-600 hover:bg-emerald-500 px-5 py-2.5 text-sm font-semibold transition-colors disabled:opacity-60"
            >
              {loading ? "Sending…" : `Email me the full $${ticker} report`}
            </button>
          </form>
          {error && <p className="text-red-400 text-xs mt-2">{error}</p>}
        </section>
      )}

      {/* Telegram secondary CTA */}
      <section className="text-center mb-8">
        <a
          href={telegramUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-2 text-sm text-sky-400 hover:text-sky-300 transition-colors"
        >
          Track ${ticker} on Telegram →
        </a>
      </section>

      <footer className="text-center text-xs text-neutral-600">
        Context, not financial advice. Sentinel AI provides analysis for informational purposes only.
      </footer>
    </main>
  );
}
