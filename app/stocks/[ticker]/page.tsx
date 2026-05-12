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
  const [step, setStep] = useState<1 | 2>(1);
  const [seedTickers, setSeedTickers] = useState<[string, string, string]>(["", "", ""]);
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

  function handleStep1(e: React.FormEvent) {
    e.preventDefault();
    if (!email.trim()) return;
    setError("");
    setStep(2);
  }

  async function captureSubmit(rawSeeds: string[]) {
    setLoading(true);
    setError("");

    // Client-side: uppercase + filter on /^[A-Z]{1,5}$/ + dedupe + cap 3.
    // Server re-validates so we don't need to be strict here, but a
    // small clean-up keeps the network payload tidy.
    const cleaned: string[] = [];
    for (const raw of rawSeeds) {
      const upper = raw.trim().toUpperCase();
      if (!/^[A-Z]{1,5}$/.test(upper)) continue;
      if (cleaned.includes(upper)) continue;
      cleaned.push(upper);
      if (cleaned.length >= 3) break;
    }

    try {
      const res = await fetch("/api/leads/capture", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email,
          ticker,
          sourcePath: `/stocks/${ticker}`,
          seedTickers: cleaned,
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

  function handleSkip() {
    captureSubmit([]);
  }

  async function handleStep2Save(e: React.FormEvent) {
    e.preventDefault();
    await captureSubmit(seedTickers);
  }

  function updateSeed(index: 0 | 1 | 2, value: string) {
    // auto-uppercase + strip non A-Z; cap 5 chars
    const clean = value.toUpperCase().replace(/[^A-Z]/g, "").slice(0, 5);
    setSeedTickers((prev) => {
      const next: [string, string, string] = [...prev] as [string, string, string];
      next[index] = clean;
      return next;
    });
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

      {/* Email gate — 2-step: email, then optional seed tickers */}
      {submitted ? (
        <section className="rounded-xl bg-neutral-900 border border-neutral-700 p-6 text-center">
          <p className="text-emerald-400 font-semibold text-lg mb-2">Check your inbox</p>
          <p className="text-neutral-400 text-sm">
            We sent a link to <strong>{email}</strong>. Click it to unlock the full ${ticker} report.
          </p>
        </section>
      ) : step === 1 ? (
        <section className="rounded-xl bg-neutral-900 border border-neutral-700 p-6 mb-6">
          <p className="font-semibold mb-1">Unlock the full 10-dimension report</p>
          <p className="text-neutral-400 text-sm mb-4">
            Get the complete breakdown, risk analysis, and PDF — free.
          </p>
          <form onSubmit={handleStep1} className="flex flex-col sm:flex-row gap-3">
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
              className="rounded-lg bg-emerald-600 hover:bg-emerald-500 px-5 py-2.5 text-sm font-semibold transition-colors"
            >
              Continue →
            </button>
          </form>
          {error && <p className="text-red-400 text-xs mt-2">{error}</p>}
          <p className="text-neutral-500 text-xs mt-3">
            One quick optional step next — nothing else.
          </p>
        </section>
      ) : (
        <section className="rounded-xl bg-neutral-900 border border-neutral-700 p-6 mb-6">
          <p className="font-semibold mb-1">
            What 3 tickers do you check most often?
          </p>
          <p className="text-neutral-400 text-sm mb-1">
            We&apos;ll flag them when they show up in our radar.
          </p>
          <p className="text-neutral-600 text-xs mb-4">
            e.g. AAPL, TSLA, NVDA — skip if you&apos;re not sure yet.
          </p>
          <form onSubmit={handleStep2Save} className="flex flex-col gap-3">
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
              {[0, 1, 2].map((i) => (
                <input
                  key={i}
                  type="text"
                  inputMode="text"
                  autoCapitalize="characters"
                  maxLength={5}
                  placeholder={["AAPL", "TSLA", "NVDA"][i]}
                  value={seedTickers[i]}
                  onChange={(e) => updateSeed(i as 0 | 1 | 2, e.target.value)}
                  className="rounded-lg bg-neutral-800 border border-neutral-700 px-4 py-2.5 text-sm font-mono uppercase tracking-widest text-white placeholder-neutral-600 outline-none focus:border-emerald-500"
                />
              ))}
            </div>
            <div className="flex flex-col sm:flex-row gap-2 mt-1">
              <button
                type="button"
                onClick={handleSkip}
                disabled={loading}
                className="rounded-lg border border-neutral-700 hover:border-neutral-500 px-5 py-2.5 text-sm font-medium text-neutral-300 transition-colors disabled:opacity-60"
              >
                Skip
              </button>
              <button
                type="submit"
                disabled={loading}
                className="flex-1 rounded-lg bg-emerald-600 hover:bg-emerald-500 px-5 py-2.5 text-sm font-semibold transition-colors disabled:opacity-60"
              >
                {loading ? "Saving…" : `Save & email me the $${ticker} report`}
              </button>
            </div>
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
