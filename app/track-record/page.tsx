import Link from "next/link";

import { prisma } from "@/lib/prisma";

export const dynamic = "force-dynamic";

function formatDate(value: Date) {
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "America/New_York",
    timeZoneName: "short"
  }).format(value);
}

function stateLabel(value: string | null) {
  if (!value) {
    return "Recorded";
  }

  return value.replace(/_/g, " ");
}

export default async function TrackRecordPage() {
  const since = new Date();
  since.setUTCDate(since.getUTCDate() - 90);

  const records = await prisma.analysisHistory.findMany({
    where: {
      status: "COMPLETED",
      createdAt: {
        gte: since
      }
    },
    orderBy: {
      createdAt: "desc"
    },
    take: 120,
    select: {
      id: true,
      ticker: true,
      requestedMode: true,
      finalScore: true,
      rating: true,
      recommendation: true,
      pdfUrl: true,
      createdAt: true
    }
  });

  const completed = records.length;
  const cited = records.filter((record) => Boolean(record.pdfUrl)).length;

  return (
    <main className="min-h-screen bg-[#f4f1ea] px-5 py-8 text-[#0b0d0c]">
      <div className="mx-auto max-w-6xl">
        <header className="mb-10 flex flex-col gap-4 border-b border-[#0b0d0c] pb-6 md:flex-row md:items-end md:justify-between">
          <div>
            <p className="font-mono text-xs uppercase tracking-[0.22em] text-[#0a9454]">Public Track Record</p>
            <h1 className="mt-3 max-w-3xl text-4xl font-black tracking-[-0.04em] md:text-6xl">
              Every completed Sentinel alert, visible in one place.
            </h1>
            <p className="mt-4 max-w-2xl text-sm leading-6 text-[#3a3f3c]">
              This page shows the actual completed analysis history available in the product database. It does not show
              simulated outcomes or backfilled returns.
            </p>
          </div>
          <Link className="border border-[#0b0d0c] px-4 py-3 font-mono text-xs uppercase tracking-[0.16em]" href="/">
            Back to app
          </Link>
        </header>

        <section className="mb-8 grid gap-3 md:grid-cols-3">
          <div className="border border-[#0b0d0c] bg-[#ebe7dd] p-5">
            <p className="font-mono text-xs uppercase tracking-[0.16em] text-[#3a3f3c]">Window</p>
            <p className="mt-2 text-3xl font-black">90 days</p>
          </div>
          <div className="border border-[#0b0d0c] bg-[#ebe7dd] p-5">
            <p className="font-mono text-xs uppercase tracking-[0.16em] text-[#3a3f3c]">Completed</p>
            <p className="mt-2 text-3xl font-black">{completed}</p>
          </div>
          <div className="border border-[#0b0d0c] bg-[#ebe7dd] p-5">
            <p className="font-mono text-xs uppercase tracking-[0.16em] text-[#3a3f3c]">PDF Available</p>
            <p className="mt-2 text-3xl font-black">{cited}</p>
          </div>
        </section>

        <section className="overflow-hidden border border-[#0b0d0c] bg-[#f8f5ee]">
          <div className="grid grid-cols-[1.1fr_0.8fr_0.8fr_0.9fr_0.7fr_0.7fr] gap-3 border-b border-[#0b0d0c] bg-[#0b0d0c] px-4 py-3 font-mono text-[11px] uppercase tracking-[0.14em] text-[#f4f1ea]">
            <span>Issued</span>
            <span>Ticker</span>
            <span>Score</span>
            <span>State</span>
            <span>T+3</span>
            <span>T+7</span>
          </div>
          {records.length > 0 ? (
            records.map((record) => (
              <div
                className="grid grid-cols-[1.1fr_0.8fr_0.8fr_0.9fr_0.7fr_0.7fr] gap-3 border-b border-[#d6d1c3] px-4 py-4 text-sm last:border-b-0"
                key={record.id}
              >
                <span className="font-mono text-xs text-[#3a3f3c]">{formatDate(record.createdAt)}</span>
                <span className="font-bold">{record.ticker}</span>
                <span>{record.finalScore ?? "N/A"}</span>
                <span>{stateLabel(record.recommendation ?? record.rating)}</span>
                <span className="text-[#8a8b85]">pending</span>
                <span className="text-[#8a8b85]">pending</span>
              </div>
            ))
          ) : (
            <div className="px-4 py-10 text-sm text-[#3a3f3c]">
              No completed public records yet. The table will populate automatically from completed analyses.
            </div>
          )}
        </section>

        <p className="mt-5 max-w-3xl text-xs leading-5 text-[#3a3f3c]">
          T+3 and T+7 are intentionally marked pending until Sentinel stores point-in-time market snapshots. This is the
          correct public posture: show what is real today, then expand the record as the data model matures.
        </p>
      </div>
    </main>
  );
}
