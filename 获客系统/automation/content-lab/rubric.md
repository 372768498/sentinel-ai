# Sentinel Content Rubric · 7-Dim

> Design doc. The rubric is implemented later as
> `worker/app/marketing/content_lab/rubric.py::score_content(draft) -> ContentScore`.

## The 7 dimensions

| # | Dimension | Question | Source of truth |
|---|-----------|----------|-----------------|
| 1 | **Ticker Heat** | Is this ticker actually being talked about right now? | `TickerIntelligenceProfile.overall_opportunity` |
| 2 | **Retail Intent** | Does the draft answer a retail-investor question they're already asking? | SocialSignal intent counts from x_serp |
| 3 | **Hook Clarity** | First sentence makes me lean in within 3 seconds? | LLM rubric pass (Sonnet 4.6 grader) |
| 4 | **Risk Novelty** | Risk flag is concrete and non-obvious (not "macro uncertainty")? | LLM rubric pass + redline novelty heuristic |
| 5 | **Evidence Strength** | At least one primary-source URL + at least one numeric data point? | redline.scan + regex over body |
| 6 | **CTA Fit** | CTA URL is `/stocks/{ticker}` and matches the body's claim? | exact string match on draft.cta_url |
| 7 | **Compliance Safety** | Zero redline hits, disclaimer present, no recommendation verbs? | redline.scan result |

## Content Score formula

```
Content Score =
    Ticker Heat        × 0.20
  + Retail Intent      × 0.20
  + Hook Clarity       × 0.15
  + Risk Novelty       × 0.15
  + Evidence Strength  × 0.10
  + CTA Fit            × 0.10
  + Compliance Safety  × 0.10
```

All dimensions return 0-100. Total is 0-100.

## Why these weights (Week 6 baseline)

- **Ticker Heat (0.20)** and **Retail Intent (0.20)** are the two pre-existing
  conditions for any click whatsoever. If the topic is dead, the rest doesn't
  matter.
- **Hook Clarity (0.15)** and **Risk Novelty (0.15)** are the two levers a
  writer actually controls on a per-draft basis. They sum to 0.30, matching
  the structural weight of "is this even the right ticker".
- **Evidence Strength (0.10)** and **CTA Fit (0.10)** are correctness checks —
  necessary but not differentiating once met.
- **Compliance Safety (0.10)** is a multiplier-style floor — any redline hit
  zeros this dimension and brings the total down regardless of how good the
  rest is.

## Score → action

| Score | Action |
|-------|--------|
| ≥ 80 | Publish without edits |
| 65-79 | Editor pass with specific dimension to fix (return rubric breakdown) |
| 50-64 | Send back for hook + evidence rewrite |
| < 50 | Reject — usually means the underlying opportunity isn't strong |

## Updating the rubric

Every Monday 09:00 ET:

1. Pull the last 30 days of `Predictions ↔ Performance` rows.
2. Fit a regression: `(actual_click_to_email_rate) ~ (each dimension score)`.
3. Renormalize weights so high-correlation dimensions get more weight
   (capped at 0.05 movement per week to avoid whiplash).
4. Commit the new weights to `content_lab/rubric_weights.json` with the
   regression report attached.

This is the "rubric evolution" piece — Sentinel content judgment compounds
because the weights track what actually converts, not what the editor
*thinks* converts.

## Predictions table (future Feishu Bitable schema)

| Field | Type | Notes |
|-------|------|-------|
| `prediction_id` | text (primary) | `PR-YYYYMMDD-{content_id}` |
| `content_id` | text | links to Content Queue |
| `editor` | text | who made the prediction |
| `predicted_bucket` | single-select | top_25 / median / bottom_25 |
| `predicted_at` | datetime | |
| `actual_click_to_email_rate` | number | filled at T+24h |
| `actual_free_to_paid_rate` | number | filled at T+72h |
| `prediction_correct` | checkbox | |
| `notes` | text | |
