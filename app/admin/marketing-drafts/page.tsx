"use client";

import { FormEvent, useMemo, useState } from "react";

type MarketingDraft = {
  id: string;
  channel: "X" | "REDDIT" | "TELEGRAM";
  persona: string;
  ticker: string | null;
  score: number | null;
  headline: string;
  body: string;
  sourceUrl: string | null;
  deepLink: string | null;
  status: "DRAFT" | "APPROVED" | "REJECTED" | "POSTED";
  redlineOk: boolean;
  redlineNotes: string | null;
  createdAt: string;
};

type DraftListResponse = {
  drafts: MarketingDraft[];
};

const emptyForm = {
  channel: "X",
  persona: "SEC Filing Reporter",
  ticker: "",
  score: "80",
  headline: "",
  body: "",
  sourceUrl: "",
  deepLink: "",
  redlineOk: false,
  redlineNotes: ""
};

export default function MarketingDraftsPage() {
  const [adminKey, setAdminKey] = useState("");
  const [drafts, setDrafts] = useState<MarketingDraft[]>([]);
  const [message, setMessage] = useState("");
  const [form, setForm] = useState(emptyForm);
  const pendingCount = useMemo(() => drafts.filter((draft) => draft.status === "DRAFT").length, [drafts]);

  const headers = {
    "Content-Type": "application/json",
    "x-admin-key": adminKey
  };

  async function loadDrafts() {
    setMessage("");
    const response = await fetch("/api/admin/marketing-drafts", {
      headers,
      cache: "no-store"
    });
    const payload = (await response.json()) as DraftListResponse & { error?: string };

    if (!response.ok) {
      setMessage(payload.error ?? "Unable to load drafts.");
      return;
    }

    setDrafts(payload.drafts);
  }

  async function createDraft(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage("");

    const response = await fetch("/api/admin/marketing-drafts", {
      method: "POST",
      headers,
      body: JSON.stringify({
        channel: form.channel,
        persona: form.persona,
        ticker: form.ticker || undefined,
        score: form.score ? Number(form.score) : undefined,
        headline: form.headline,
        body: form.body,
        sourceUrl: form.sourceUrl || undefined,
        deepLink: form.deepLink || undefined,
        redlineOk: form.redlineOk,
        redlineNotes: form.redlineNotes || undefined
      })
    });
    const payload = (await response.json()) as { draft?: MarketingDraft; error?: unknown };

    if (!response.ok || !payload.draft) {
      setMessage(typeof payload.error === "string" ? payload.error : "Unable to create draft.");
      return;
    }

    setDrafts((current) => [payload.draft as MarketingDraft, ...current]);
    setForm(emptyForm);
  }

  async function updateDraft(id: string, action: "approve" | "reject" | "mark_posted") {
    const response = await fetch(`/api/admin/marketing-drafts/${id}`, {
      method: "PATCH",
      headers,
      body: JSON.stringify({
        action,
        actor: "admin-dashboard",
        reason: action === "reject" ? "Rejected in dry-run dashboard" : undefined
      })
    });
    const payload = (await response.json()) as { draft?: MarketingDraft; error?: string };

    if (!response.ok || !payload.draft) {
      setMessage(payload.error ?? "Unable to update draft.");
      return;
    }

    setDrafts((current) => current.map((draft) => (draft.id === id ? (payload.draft as MarketingDraft) : draft)));
  }

  return (
    <main className="min-h-screen bg-[#050505] px-5 py-8 text-[#e7f3ec]">
      <div className="mx-auto max-w-7xl">
        <header className="mb-8 flex flex-col gap-4 border-b border-[#153824] pb-5 md:flex-row md:items-end md:justify-between">
          <div>
            <p className="font-mono text-xs uppercase tracking-[0.22em] text-[#00ff88]">Growth Dry-Run</p>
            <h1 className="mt-3 text-4xl font-black tracking-[-0.04em]">Marketing approval queue</h1>
            <p className="mt-3 max-w-2xl text-sm leading-6 text-[#8a9a90]">
              X, Reddit, and Telegram copy should land here first. Approve only source-cited, red-line clean drafts.
            </p>
          </div>
          <div className="border border-[#153824] px-4 py-3 font-mono text-xs uppercase tracking-[0.14em] text-[#00ff88]">
            {pendingCount} pending
          </div>
        </header>

        <section className="mb-8 grid gap-3 md:grid-cols-[1fr_auto]">
          <input
            className="border border-[#153824] bg-black px-4 py-3 text-sm outline-none focus:border-[#00ff88]"
            onChange={(event) => setAdminKey(event.target.value)}
            placeholder="ADMIN_API_KEY"
            type="password"
            value={adminKey}
          />
          <button className="bg-[#00ff88] px-5 py-3 font-mono text-xs font-bold uppercase tracking-[0.16em] text-black" onClick={loadDrafts}>
            Load queue
          </button>
        </section>

        {message ? <p className="mb-5 border border-[#f59e0b] p-3 text-sm text-[#f59e0b]">{message}</p> : null}

        <form className="mb-8 grid gap-3 border border-[#153824] bg-[#0a0a0a] p-5" onSubmit={createDraft}>
          <div className="grid gap-3 md:grid-cols-4">
            <select
              className="border border-[#153824] bg-black px-3 py-3 text-sm"
              onChange={(event) => setForm((current) => ({ ...current, channel: event.target.value }))}
              value={form.channel}
            >
              <option value="X">X</option>
              <option value="REDDIT">Reddit</option>
              <option value="TELEGRAM">Telegram</option>
            </select>
            <input
              className="border border-[#153824] bg-black px-3 py-3 text-sm"
              onChange={(event) => setForm((current) => ({ ...current, persona: event.target.value }))}
              placeholder="Persona"
              value={form.persona}
            />
            <input
              className="border border-[#153824] bg-black px-3 py-3 text-sm"
              onChange={(event) => setForm((current) => ({ ...current, ticker: event.target.value.toUpperCase() }))}
              placeholder="Ticker"
              value={form.ticker}
            />
            <input
              className="border border-[#153824] bg-black px-3 py-3 text-sm"
              max="100"
              min="0"
              onChange={(event) => setForm((current) => ({ ...current, score: event.target.value }))}
              placeholder="Score"
              type="number"
              value={form.score}
            />
          </div>
          <input
            className="border border-[#153824] bg-black px-3 py-3 text-sm"
            onChange={(event) => setForm((current) => ({ ...current, headline: event.target.value }))}
            placeholder="Headline"
            value={form.headline}
          />
          <textarea
            className="min-h-36 border border-[#153824] bg-black px-3 py-3 text-sm"
            onChange={(event) => setForm((current) => ({ ...current, body: event.target.value }))}
            placeholder="Draft body"
            value={form.body}
          />
          <div className="grid gap-3 md:grid-cols-2">
            <input
              className="border border-[#153824] bg-black px-3 py-3 text-sm"
              onChange={(event) => setForm((current) => ({ ...current, sourceUrl: event.target.value }))}
              placeholder="Primary source URL"
              value={form.sourceUrl}
            />
            <input
              className="border border-[#153824] bg-black px-3 py-3 text-sm"
              onChange={(event) => setForm((current) => ({ ...current, deepLink: event.target.value }))}
              placeholder="Telegram deep-link"
              value={form.deepLink}
            />
          </div>
          <label className="flex items-center gap-3 text-sm text-[#8a9a90]">
            <input
              checked={form.redlineOk}
              onChange={(event) => setForm((current) => ({ ...current, redlineOk: event.target.checked }))}
              type="checkbox"
            />
            Red-line scan passed
          </label>
          <button className="w-full bg-[#00ff88] px-5 py-3 font-mono text-xs font-bold uppercase tracking-[0.16em] text-black">
            Create dry-run draft
          </button>
        </form>

        <section className="grid gap-4">
          {drafts.map((draft) => (
            <article className="border border-[#153824] bg-[#0a0a0a] p-5" key={draft.id}>
              <div className="mb-3 flex flex-wrap items-center gap-2 font-mono text-[11px] uppercase tracking-[0.12em] text-[#8a9a90]">
                <span className="text-[#00ff88]">{draft.channel}</span>
                <span>{draft.status}</span>
                <span>{draft.persona}</span>
                {draft.ticker ? <span>${draft.ticker}</span> : null}
                {draft.score !== null ? <span>Score {draft.score}</span> : null}
                <span>{draft.redlineOk ? "Red-line ok" : "Needs scan"}</span>
              </div>
              <h2 className="text-lg font-bold text-white">{draft.headline}</h2>
              <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-[#d8e4dc]">{draft.body}</p>
              <div className="mt-4 flex flex-wrap gap-2">
                <button className="border border-[#00ff88] px-4 py-2 text-xs text-[#00ff88]" onClick={() => updateDraft(draft.id, "approve")}>
                  Approve
                </button>
                <button className="border border-[#f59e0b] px-4 py-2 text-xs text-[#f59e0b]" onClick={() => updateDraft(draft.id, "reject")}>
                  Reject
                </button>
                <button className="border border-[#8a9a90] px-4 py-2 text-xs text-[#8a9a90]" onClick={() => updateDraft(draft.id, "mark_posted")}>
                  Mark posted
                </button>
              </div>
            </article>
          ))}
        </section>
      </div>
    </main>
  );
}
