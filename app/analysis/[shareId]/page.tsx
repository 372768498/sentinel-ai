"use client";

import { useEffect, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { scoreToRating, ratingColor, ratingBg } from "@/lib/rating";
import { parseUtmFromSearch, persistUtm, readUtmCookie, mergeUtm } from "@/lib/utm";

interface SharedAnalysis {
  ticker: string;
  companyName: string;
  totalScore: number;
  ratingLabel: string;
  riskFlag: string;
  createdAt: string;
}

function getMockAnalysis(shareId: string): SharedAnalysis {
  return {
    ticker: "NVDA",
    companyName: "NVIDIA Corporation",
    totalScore: 78,
    ratingLabel: "SOLID",
    riskFlag: "Export restriction risk may weigh on guidance — monitor Q3 disclosure.",
    createdAt: new Date().toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" }),
  };
}

export default function AnalysisSharePage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const shareId = params.shareId as string;

  const [email, setEmail] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const data = getMockAnalysis(shareId);
  const rating = scoreToRating(data.totalScore);

  useEffect(() => {
    const fromSearch = parseUtmFromSearch(searchParams.toString());
    const fromCookie = readUtmCookie();
    const merged = mergeUtm(fromSearch, fromCookie);
    persistUtm(merged);

    fetch("/api/track/visit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: `/analysis/${shareId}`, utm: merged }),
    }).catch(() => {});
  }, [shareId, searchParams]);

  async function handleUnlock(e: React.FormEvent) {
    e.preventDefault();
    if (!email) return;
    setLoading(true);
    setError("");

    try {
      const utm = mergeUtm(parseUtmFromSearch(searchParams.toString()), readUtmCookie());

      await fetch("/api/leads/capture", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email,
          ticker: data.ticker,
          sourcePath: `/analysis/${shareId}`,
          utm,
        }),
      });

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
        <p className="text-xs text-neutral-500 uppercase tracking-widest mb-1">
          Sentinel AI · Shared Analysis · {data.createdAt}
        </p>
        <h1 className="text-3xl font-bold">${data.ticker}</h1>
        <p className="text-neutral-400 text-sm mt-1">{data.companyName}</p>
      </header>

      {/* Score summary */}
      <section className={`rounded-xl border p-6 mb-6 ${ratingBg(rating)}`}>
        <div className="flex items-center justify-between">
          <div>
            <p className="text-xs uppercase tracking-widest text-neutral-400 mb-1">AI Score</p>
            <p className="text-5xl font-black">{data.totalScore}</p>
            <p className={`text-lg font-semibold mt-1 ${ratingColor(rating)}`}>{rating}</p>
          </div>
          <p className="text-xs text-neutral-500 text-right">Sentinel AI<br />10-dimension context</p>
        </div>
      </section>

      {/* Risk flag */}
      <section className="rounded-lg bg-orange-950 border border-orange-800 p-4 mb-8 text-sm text-orange-200">
        <p className="font-semibold mb-1">Key Risk Flag</p>
        <p>{data.riskFlag}</p>
      </section>

      {/* Full report gate */}
      {submitted ? (
        <section className="rounded-xl bg-neutral-900 border border-neutral-700 p-6 text-center">
          <p className="text-emerald-400 font-semibold text-lg mb-2">Check your inbox</p>
          <p className="text-neutral-400 text-sm">
            We sent a link to <strong>{email}</strong>. Click it to access the full 10-dimension report.
          </p>
        </section>
      ) : (
        <section className="rounded-xl bg-neutral-900 border border-neutral-700 p-6 mb-6">
          <p className="font-semibold mb-1">Unlock the full 10-dimension report</p>
          <p className="text-neutral-400 text-sm mb-4">
            Complete risk analysis, all dimension breakdowns, and PDF — free.
          </p>
          <form onSubmit={handleUnlock} className="flex flex-col sm:flex-row gap-3">
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
              {loading ? "Sending…" : "Unlock the full report"}
            </button>
          </form>
          {error && <p className="text-red-400 text-xs mt-2">{error}</p>}
        </section>
      )}

      {/* Telegram secondary */}
      <section className="text-center mb-8">
        <a
          href={telegramUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-2 text-sm text-sky-400 hover:text-sky-300 transition-colors"
        >
          Get daily briefings on Telegram →
        </a>
      </section>

      <footer className="text-center text-xs text-neutral-600">
        Context, not financial advice. Sentinel AI provides analysis for informational purposes only.
      </footer>
    </main>
  );
}
