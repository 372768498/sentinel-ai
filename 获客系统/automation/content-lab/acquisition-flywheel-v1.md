# Sentinel AI Acquisition Flywheel v1

> Goal: turn market anxiety into email leads and eventually paid users.
> Scope: phase-1 social acquisition for X, Reddit, YouTube Shorts, TikTok.

## Market Backing

- FINRA's 2025 social-media investing report says 45% of investors receive financial advice from the internet and 24% from social media. Under-30 investors rely on social media more than older investors. Source: <https://www.finra.org/rules-guidance/key-topics/fintech/report/social-media-influenced-investing>
- Pew's 2024 social media report shows YouTube is one of the broadest U.S. adult platforms, while TikTok has grown materially since 2021. Source: <https://www.pewresearch.org/internet/2024/01/31/americans-social-media-use/>
- YouTube says Shorts average more than 70B daily views. Source: <https://blog.youtube/inside-youtube/shorts-revenue-sharing-update/>
- TikTok creative guidance emphasizes fast hooks and clear calls to action. Source: <https://ads.tiktok.com/help/article/creative-best-practices>

## User Psychology

The target user is not looking for another finance creator. They want a fast answer to one of five anxieties:

| Anxiety | What the user thinks | Sentinel content promise |
| --- | --- | --- |
| Missed signal | "What did I miss?" | Show what changed today. |
| Narrative risk | "Everyone says the same thing. Is there a catch?" | Show the second-order risk. |
| Earnings fear | "What can go wrong before earnings?" | Show three checks before the event. |
| Time poverty | "I do not have time to read filings and posts." | Let Sentinel scan the context. |
| Watchlist drift | "My watchlist moved while I was away." | Show what changed overnight. |

The content must never answer "should I buy?" It should answer:

```text
What should I verify before I trust the market narrative?
```

## Core Message

Sentinel AI is not a stock picker. It is a context scanner that:

```text
knows the market -> remembers the user's watchlist -> flags what changed
```

Use this phrasing across content:

- "Run a free context scan."
- "See what Sentinel flags before earnings."
- "Check your watchlist state."
- "Context, not financial advice."

Avoid:

- "buy / sell / hold"
- "price target"
- "AI predicts"
- "this stock will explode"
- "top stocks to buy"

## The Four Flywheels

### Flywheel 1 - Signal To Content

```text
market signal -> anxiety angle -> platform draft -> review -> publish
```

Input sources:

- FMP quote / mover data
- SEC filing / EDGAR context
- X SERP / X API buzz
- YouTube benchmark signals
- Manual ticker seeds from watchlist users

Output per opportunity:

- X post
- Reddit discussion draft
- YouTube Shorts script / video
- TikTok script / video

Decision rule:

```text
Only create content when the opportunity has a clear user anxiety.
No anxiety = no content.
```

### Flywheel 2 - Content To Lead

```text
social post -> UTM CTA -> /stocks/[ticker] -> email capture -> free scan
```

CTA patterns:

- "Run a free $TICKER context scan."
- "Preview what changed in $TICKER."
- "Check the current Sentinel state."
- "See the three risk flags before earnings."

Never use:

- "Learn more"
- "Visit our site"
- "Follow for more"

Optimization metric:

```text
click_to_email_rate = EmailLead / VisitEvent
```

### Flywheel 3 - Lead To Habit

```text
email capture -> seed tickers -> daily radar -> watchlist memory -> repeat visits
```

The first email should not be a newsletter. It should be a useful scan:

- current state
- what changed
- three risk flags
- one next event to watch

Habit trigger:

```text
"Your watchlist changed overnight."
```

This is stronger than:

```text
"Here is today's market news."
```

### Flywheel 4 - KPI To Creative Learning

```text
content_id -> visits -> emails -> signups -> paid -> template weights
```

Every content item must store:

- `content_id`
- platform
- ticker
- state
- angle
- hook
- CTA
- publish time

Evaluate at:

- T+24h: views / clicks / email captures
- T+72h: signups / paid
- Weekly: winning hooks and losing formats

North Star:

```text
qualified_email_leads_per_day
```

Secondary:

- click-to-email rate
- email-to-first-analysis rate
- free-to-paid rate
- lead per content item
- lead per platform

## Content Angles

| Angle | User anxiety | Hook formula | CTA |
| --- | --- | --- | --- |
| Earnings Watch | "What can go wrong before earnings?" | `$TICKER before earnings: 3 risk flags to verify.` | `Run the pre-earnings context scan.` |
| Crowded Trade | "Is everyone too optimistic?" | `$TICKER is getting crowded again. Here is what changed.` | `Check the current Sentinel state.` |
| Retail Misread | "Am I only seeing the headline?" | `Retail is watching the headline. Sentinel flags the second-order risk.` | `See the context scan.` |
| Sudden Move | "Why did it move?" | `$TICKER moved. The move is not the story.` | `Preview what changed.` |
| Valuation Pressure | "What breaks the narrative?" | `$TICKER looks calm, but valuation pressure is building.` | `Check the risk flags.` |
| Watchlist Memory | "What changed while I was away?" | `Your watchlist changed overnight. Sentinel caught this.` | `Add your tickers.` |
| Competitor Alternative | "Is there a better stock research workflow?" | `Still using screenshots and tabs for stock research?` | `Try a context scan.` |
| Filing Alert | "What did the filing actually change?" | `$TICKER filed. Here is the part worth verifying.` | `Read the simplified context.` |
| Sentiment Divergence | "Why does price disagree with attention?" | `$TICKER price is calm, but attention is heating up.` | `Check the signal mix.` |
| Risk Stack | "Are multiple risks overlapping?" | `$TICKER has three risk flags stacked today.` | `Run the full scan.` |

## Platform Roles

| Platform | Role | First-phase behavior |
| --- | --- | --- |
| X | Fast signal and daily hooks | Auto-publish after Feishu approval once live credentials are ready. |
| Reddit | Trust-building discussion | Generate drafts; human posts manually in selected communities. |
| YouTube Shorts | High-scale discovery | Render video pack; manual upload until publisher exists. |
| TikTok | Hook testing and younger audience | Render video pack; manual upload until publisher exists. |
| Email | Habit and retention | Deliver useful scans, not broad market news. |

## 7-Day Experiment

Daily output:

- 3 X posts
- 1 Reddit draft
- 2 Shorts/TikTok video packs
- 1 email scan for captured leads

Only test three angles in week 1:

1. Earnings Watch
2. Crowded Trade
3. Watchlist Memory

Daily review:

- top hook by click-to-email
- worst hook by bounce / no capture
- best ticker by lead count
- platform with highest lead efficiency

Stop rule:

```text
If an angle gets 0 email captures after 10 published items, pause it.
```

Double-down rule:

```text
If an angle beats 8% click-to-email rate twice, produce 3 variants next day.
```

## 30-Day Flywheel Milestones

Week 1:

- Prove CTA and capture path.
- Publish manually where needed.
- No AdsPower.

Week 2:

- Add video pack renderer quality gate.
- Start weekly creative retro.
- Keep platform count small.

Week 3:

- Turn winning hooks into templates.
- Add first YouTube/TikTok upload checklist.
- Segment leads by ticker/state.

Week 4:

- Decide whether X live posting stays on.
- Decide whether Shorts/TikTok deserve automation.
- Define AdsPower readiness criteria, but do not activate matrix yet.

## Video Skill Requirements

The future video skill must not be a renderer-only skill. It must produce a full acquisition pack:

```text
creative_brief.md
script.md
shot_plan.json
captions.srt
cover.png
video.mp4
platform_copy.md
qa_report.json
```

Minimum QA:

- 1080x1920
- 15-45 seconds
- ticker and state visible in first 2 seconds
- max 12 words per screen
- captions stay in safe center area
- CTA is action-specific
- disclaimer present
- forbidden investment advice terms absent

## Implementation Implications

Current renderer quality is insufficient. Keep the pipeline concept, but replace the visual system with:

- scene-based motion templates
- safe-area-aware captions
- cover image generation
- SRT export
- per-platform copy
- video QA screenshots

Do not build ten templates first. Build one excellent `Ticker State / Risk Stack` template, then use KPI data to decide the second template.
