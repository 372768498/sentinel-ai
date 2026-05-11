# Content Lab · Content Evolution

> Design doc only. No production code in this directory.
>
> Companion source-of-truth for **how** Sentinel content should be scored,
> predicted, and retrofitted into the rubric. Implementation lands in
> `worker/app/marketing/content_lab/` (future) — once the Market Intelligence
> Layer (Week 6) has been running long enough to generate ground-truth data.

## Why a separate Content Lab

The Growth OS has two distinct concerns that were initially conflated:

| Concern | Owned by | Question it answers |
|---------|----------|---------------------|
| **Data Acquisition / Market Intelligence** | `worker/app/marketing/data_sources/` + `intelligence.py` | What is the market saying today, and why this ticker? |
| **Content Evolution / Content Lab** | this directory (design) → future `worker/app/marketing/content_lab/` | How do we tell the story so that attention becomes email and paid? |

Mixing them produced "spray more tickers" instinct. The Lab forces every piece
of content to commit to a hypothesis ("this hook will outperform because…")
before publish and to retrofit results into the rubric after.

## Workflow

```text
Opportunity (TickerIntelligenceProfile)
    │
    ▼
Draft (Content Factory, redline-scanned)
    │
    ▼
Pre-score (7-dim rubric, see rubric.md)
    │
    ▼
Blind prediction
    "I predict this content will land in the top 25% of click→email conversions."
    │
    ▼
Feishu Review (human edit / Approved)
    │
    ▼
Publish (Telegram dry-run / live)
    │
    ▼
T+24h retro (clicks / emails / signups)
    │
    ▼
T+72h retro (free→paid)
    │
    ▼
Rubric update: which dimension's weight should shift?
```

## Why pre-score AND blind prediction

Pre-score: deterministic, weights known up-front, lets the editor see
"this is a 78 — risk_novelty is what's pulling it up; redo CTA to bring it to 85".

Blind prediction: separate from the rubric, captures editor intuition
("I think this will outperform / underperform"). After T+24h, we compare
the prediction confidence against actual performance and update the editor's
calibration log. This is how Sentinel content judgment compounds — humans get
better at predicting, the rubric gets better at scoring.

## North Star (NOT views)

Views are vanity for a B2C SaaS converting attention into paid plans. The
North Star is the conversion funnel:

```
View → Click rate
Click → Email rate          ← Click-to-Email is the rubric optimization target
Email → First analysis rate
Free → Pro rate             ← Free-to-Paid is the ultimate KPI
```

The Daily Growth Digest (Week 5) already surfaces `click_to_email_rate` and
`free_to_paid_rate` per `content_id`. Content Lab feeds those rates back into
the rubric weights every Monday morning.

## Status

| Phase | Status |
|-------|--------|
| Workflow design | ✅ this doc |
| Rubric design | ✅ `rubric.md` |
| Pre-score implementation | ⏸ deferred — implements `score_content(draft) → 0-100` per dimension |
| Blind prediction capture | ⏸ deferred — stores predictions in a 4th Bitable table `Predictions` |
| T+24h / T+72h retro job | ⏸ deferred — extends `kpi_aggregator` to write retro rows |
| Rubric weight update | ⏸ deferred — weekly cron, regression on past 30d of `Predictions ↔ Performance` |

## Out of scope (deliberately)

- **Auto-generation of competitor benchmarks**: the rubric uses Sentinel's own
  past content as the comparison set. We do NOT need to scrape TipRanks /
  Simply Wall St content for this — Market Intelligence Layer already surfaces
  competitor-alternative chatter; the rubric ranks our content against itself.
- **A/B publishing on Telegram**: the channel is single-output. Variant
  testing belongs in Email and Landing, not in the public channel.
