import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Privacy Policy · Sentinel AI",
  description: "How Sentinel AI handles user data — read-only by design."
};

export default function PrivacyPage() {
  return (
    <main className="mx-auto max-w-3xl px-6 py-16 text-sentinel-glow">
      <h1 className="text-3xl font-semibold text-white">Privacy Policy</h1>
      <p className="mt-2 text-xs uppercase tracking-[0.2em] text-sentinel-glow/55">
        Effective 2026-05-09 · Sentinel AI
      </p>

      <section className="mt-10 space-y-6 text-sm leading-relaxed text-sentinel-glow/85">
        <h2 className="text-lg font-semibold text-white">1. What we collect</h2>
        <ul className="list-disc space-y-2 pl-6">
          <li>
            <strong>Email</strong> — used to deliver analysis reports and account
            communications.
          </li>
          <li>
            <strong>Watchlist tickers + alert preferences</strong> — used solely to
            tailor your alerts. Never shared.
          </li>
          <li>
            <strong>Telegram user ID</strong> (Pro subscribers) — used to deliver
            personal alerts to your Telegram DM.
          </li>
          <li>
            <strong>Subscription state</strong> — synced from Whop to gate Pro
            features.
          </li>
          <li>
            <strong>Acquisition source</strong> — anonymous campaign tag (e.g.
            &ldquo;xtw&rdquo;) recorded once at signup, used to compute funnel
            metrics in aggregate.
          </li>
        </ul>

        <h2 className="text-lg font-semibold text-white">2. What we do not collect</h2>
        <ul className="list-disc space-y-2 pl-6">
          <li>Brokerage credentials. We are read-only and never connect to your broker.</li>
          <li>Portfolio holdings or positions.</li>
          <li>Behavioral tracking across third-party sites.</li>
        </ul>

        <h2 className="text-lg font-semibold text-white">3. How we use data</h2>
        <p>
          Only to deliver the Service: send your alerts, gate paid features, respond
          to support, comply with law. We never sell your data.
        </p>

        <h2 className="text-lg font-semibold text-white">4. Subprocessors</h2>
        <p>
          Whop (billing), Resend (transactional email), Telegram (messaging),
          Vercel/Railway (hosting), Anthropic (LLM inference for analysis content,
          stateless calls).
        </p>

        <h2 className="text-lg font-semibold text-white">5. Retention</h2>
        <p>
          Account data is retained while your account is active. Delete-account
          requests purge all personally identifying data within 30 days.
        </p>

        <h2 className="text-lg font-semibold text-white">6. Your rights</h2>
        <p>
          Access, correction, deletion, export — email{" "}
          <a className="underline" href="mailto:privacy@sentinel.jilo.ai">
            privacy@sentinel.jilo.ai
          </a>
          .
        </p>

        <h2 className="text-lg font-semibold text-white">7. Contact</h2>
        <p>
          Privacy questions:{" "}
          <a className="underline" href="mailto:privacy@sentinel.jilo.ai">
            privacy@sentinel.jilo.ai
          </a>
        </p>
      </section>
    </main>
  );
}
