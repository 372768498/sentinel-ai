# Signal Layer + Content Factory · Week 3 Spec

## Pipeline

```
09:00 ET (Mon-Fri)
   │
   ▼
scan_x_opportunities(DEFAULT_WATCHLIST, min_score=70)
   │   reuses intel.measure_ticker_buzz()
   │   reuses x_client.XClient (X_BEARER_TOKEN required)
   │
   ▼
[Opportunity, …] sorted desc by opportunity_score
   │
   ▼  top N = MARKETING_TOP_OPPORTUNITIES_PER_DAY (default 5)
   │
   ▼
for each Opportunity:
    create_growth_pack_for_opportunity(opp)
       - compose X image/text post          -> MultiPlatformComposer (Anthropic)
       - compose Reddit image/text post     -> MultiPlatformComposer (Anthropic, manual posting)
       - compose YouTube Shorts script      -> MultiPlatformComposer (Anthropic)
       - compose TikTok short-video script  -> MultiPlatformComposer (Anthropic)
    each draft → redline.scan() → ContentDraft
   │
   ▼
submit_draft_to_review(draft)
   │   reuses Week 2 review_queue → bitable_create_record + send_card
   │
   ▼
Feishu Content Queue (Pending)  +  审核群 interactive card
```

## Opportunity score (X buzz)

```
sample_signal = min(sample_count * 2, 60)   # discussion breadth
top_signal    = min(top_like_count // 5, 40)  # peak engagement
opportunity_score = sample_signal + top_signal   # capped at 100
```

- NVDA at sample=30, top_like=200 → score 100
- AAPL at sample=15, top_like=60 → score 42
- WEAK at sample=5, top_like=10 → score 12

`min_score=70` filter keeps the noise out.

## suggested_action thresholds

| score | action |
|-------|--------|
| ≥ 70  | `create_content` |
| 30–69 | `watch` |
| < 30  | `ignore` |

Only `create_content` opportunities reach the Content Factory.

## content_id format

`CT-{YYYYMMDD}-{TICKER}-{platform_suffix}` where suffix is one of `x`, `rd`, `yt`, `tt`.

Example: `CT-20260511-NVDA-x` / `CT-20260511-NVDA-rd` / `CT-20260511-NVDA-yt` / `CT-20260511-NVDA-tt`.

## campaign_id format

`CMP-{YYYYMMDD}-daily` (one campaign per day, covers all opportunities).

## CTA URL

```
{GROWTH_OS_PUBLIC_URL}/stocks/{TICKER}
  ?utm_source={x|reddit|youtube|tiktok}
  &utm_medium={thread|discussion|shorts}
  &utm_campaign={campaign_id}
  &utm_content={content_id}
```

## Redline contract

- Every generated draft passes through `redline.scan(body)`.
- Drafts that fail redline are STILL returned + STILL submitted to review,
  marked `risk_level=High`. Humans see them — they are not silently dropped.
- Mock content NEVER reaches Feishu: if `ANTHROPIC_API_KEY` is missing and no
  composer is injected, `MultiPlatformComposer()` raises `ContentFactoryError`
  and the daily job aborts with `skipped = top_n × 3` in the stats.

## Time zone

All Marketing schedulers use `America/New_York` (US stock market local time).
DST is handled automatically by APScheduler. Host timezone has NO effect.
