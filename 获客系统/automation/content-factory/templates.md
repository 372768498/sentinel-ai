# Content Factory · Platform Templates (Week 3)

Each Opportunity fans out into three platform-specific drafts. The composer
sends a `system_prompt` + `user_prompt` to Claude Sonnet 4.6.

## X thread

**System prompt focus**: 4-tweet thread, factual calm tone, no hype.

**Required elements**:
- Ticker as `$TICKER`
- Sentinel AI score (from opportunity, do not invent)
- At least one risk-flag sentence
- CTA URL inline
- Trailing disclaimer

**Forbidden words** (redline auto-rejection):
`buy / sell / hold / price target / predict / guaranteed / moonshot / 100x / pump / dump / go long / go short`

## Telegram post

**System prompt focus**: single broadcast post under 500 chars, scan-friendly.

**Required elements**:
- Ticker `$TICKER`
- "Why now" hook
- Risk flag
- CTA URL
- Trailing disclaimer

Same forbidden-word list. No emojis (Telegram clients render inconsistently).

## YouTube Shorts script

**System prompt focus**: 45-60 second vertical short, time-stamped sections.

**Structure**:
```
0-3s   Hook       — ticker + score teaser
3-10s  Score      — reveal full score and rating
10-40s 3 Reasons  — strongest / weakest / risk flag
40-55s CTA        — link to /stocks/[ticker]
Footer            — Context, not financial advice.
```

Same forbidden-word list.

## Redline gate

After Claude returns the draft, `redline.scan(body)` runs:

| Check | Required |
|-------|----------|
| No forbidden words | yes |
| At least one `https://` source URL | yes |
| Trailing disclaimer phrase | yes |

Blocked drafts are still submitted to the review queue with `risk_level=High`
so humans see the failure mode. They are NOT auto-rewritten in this phase.
