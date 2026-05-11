# `last30days-skill` Review · 借鉴而不接入

> **Status**: Reference / future-only.
> Not a production scanner. Not on the critical path.

The `last30days-skill` project (multi-source 30-day trend aggregator) has
several techniques worth borrowing **without** adopting the project itself
as a Sentinel AI scanner. This doc captures the borrow points + the
explicit non-goals.

## What it does well (worth borrowing)

| Technique | Why it's interesting for Sentinel |
|-----------|-----------------------------------|
| **Reddit public JSON ingest** | Reddit's `*.json` endpoints (e.g. `/r/wallstreetbets.json`) are free, rate-limited but accessible without OAuth. A great X-bearer replacement for *retail sentiment*. |
| **Cross-source clustering** | Same story surfaced on Reddit + YouTube + Google Trends gets a confidence bump. Sentinel could lift this for `confidence: high` when a ticker shows up in ≥ 3 of `{FMP movers, SEC filings, Reddit posts, YouTube videos, SERP buzz}`. |
| **Entity-aware search** | Pre-resolves a query like "NVDA earnings" to (ticker=NVDA, intent=earnings) before issuing platform-specific queries. Maps cleanly onto our existing `intent` enum in `data_sources/x_serp.py`. |
| **Virality scoring** | Weighted score over (engagement, recency, source diversity). We already compute `social_heat` per ticker — a virality scorer would extend it to per-story granularity. |

## What we explicitly do NOT adopt

- **Not a Sentinel main scanner.** The Market Intelligence Layer
  (`worker/app/marketing/intelligence.py`) stays the authoritative entry
  point. `last30days-skill` would only feed adapters.
- **No multi-account / proxy bypass.** Sentinel's contract — no
  reverse-engineering, no anti-detection. Reddit's public JSON is fine;
  scraping rate-limited endpoints with rotating IPs is not.
- **No background scraping of TikTok / Instagram / private feeds.** Those
  belong to dedicated paid providers (Apify / TikHub — already in env
  matrix as reserved).
- **No batch comment harvesting.** We capture *signal* (topic + intent +
  engagement summary), not raw post bodies.

## Recommended future integration shape

When Sentinel needs a free retail-sentiment source to replace the suspended
X Bearer Token:

```text
worker/app/marketing/data_sources/last30days.py
    ├── @dataclass RedditSignal
    ├── async fetch_reddit_signals(tickers, *, subreddits=[
    │       "wallstreetbets", "stocks", "investing", "stockmarket"
    │   ]) -> list[RedditSignal]
    │   • hits each `{subreddit}/.json?t=day`
    │   • filters posts mentioning $TICKER
    │   • returns title / url / score / num_comments / author / created_utc
    │   • respects Reddit's documented rate limit (~ 60 req/min unauth)
    │
    └── (optional) async cluster_signals(reddit, x_serp, youtube) -> dict
        • combines per-ticker signals across sources
        • emits confidence_modifier ∈ {-10, 0, +10, +20}
        • feeds into TickerIntelligenceProfile.confidence
```

Hookup point: extend `intelligence.build_daily_profiles` to call
`fetch_reddit_signals` alongside the existing `serp_fetcher`. Reddit becomes
the **primary** retail-sentiment source; X SERP becomes a secondary
enrichment when DataForSEO/Tavily creds are present.

## Implementation cost estimate

| Item | Effort |
|------|--------|
| Reddit adapter (`last30days.py`) | 1 day |
| Cross-source clustering integration | 0.5 day |
| Confidence modifier in `synthesize_profile` | 0.5 day |
| Tests + smoke | 0.5 day |
| **Total** | **~2.5 days** |

## When to revisit

When at least **two** of the following are true:
- X official API path stays SUSPENDED beyond 30 days
- DataForSEO/Tavily quota burn is uncomfortable
- Daily Growth Digest shows `social_heat ≤ 20` for most rows (signal-starved)
- Editor judgment says retail sentiment is missing from the angle picks

Until then, the existing 5 adapters (FMP / SEC / DataForSEO / Tavily /
YouTube) are sufficient.

## References

- `worker/app/marketing/data_sources/__init__.py` — current adapter index
- `worker/app/marketing/intelligence.py::build_daily_profiles` — where a new adapter would plug in
- Codex blueprint §4.1 (OpenClaw) — same "borrow concept, don't adopt project" principle applied earlier
