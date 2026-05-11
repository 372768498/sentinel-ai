import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Terms of Service · Sentinel AI",
  description: "Sentinel AI terms of service for self-directed US-equity investors."
};

export default function TermsPage() {
  return (
    <main className="mx-auto max-w-3xl px-6 py-16 text-sentinel-glow">
      <h1 className="text-3xl font-semibold text-white">Terms of Service</h1>
      <p className="mt-2 text-xs uppercase tracking-[0.2em] text-sentinel-glow/55">
        Effective 2026-05-09 · Sentinel AI
      </p>

      <section className="mt-10 space-y-6 text-sm leading-relaxed text-sentinel-glow/85">
        <p>
          Sentinel AI (&ldquo;the Service&rdquo;) is a contextual alerting tool for
          self-directed US-equity investors. By using the Service, you agree to the
          terms below.
        </p>

        <h2 className="text-lg font-semibold text-white">1. What Sentinel AI is</h2>
        <p>
          Sentinel AI surfaces watchlist movements and primary-source filings (SEC
          EDGAR, issuer IR, Fed, NYSE). It does <strong>not</strong> issue buy/sell
          calls, set price targets, or predict outcomes. Every alert cites a primary
          source.
        </p>

        <h2 className="text-lg font-semibold text-white">2. Not investment advice</h2>
        <p>
          Nothing produced by the Service constitutes investment, financial, legal,
          or tax advice. The Service provides context, not advice. You are solely
          responsible for your trading and investing decisions.
        </p>

        <h2 className="text-lg font-semibold text-white">3. Subscriptions and billing</h2>
        <p>
          Paid tiers are billed through Whop. Cancel any time from your Whop
          dashboard; access continues through the end of the paid period.
        </p>

        <h2 className="text-lg font-semibold text-white">4. Acceptable use</h2>
        <p>
          Do not redistribute, scrape, or resell alerts or content. Do not use the
          Service to harass, deceive, or violate applicable law.
        </p>

        <h2 className="text-lg font-semibold text-white">5. Disclaimers and limits</h2>
        <p>
          The Service is provided &ldquo;as is&rdquo; without warranty. We make no
          guarantee of accuracy, timeliness, or fitness for any purpose. Liability
          is limited to fees paid in the prior twelve months.
        </p>

        <h2 className="text-lg font-semibold text-white">6. Contact</h2>
        <p>
          Questions: <a className="underline" href="mailto:hello@sentinel.jilo.ai">hello@sentinel.jilo.ai</a>
        </p>
      </section>
    </main>
  );
}
