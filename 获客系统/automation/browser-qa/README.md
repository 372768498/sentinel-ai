# Browser QA Harness (Week 7)

> Pre-publish landing-page verification + screenshot archive.
>
> NOT a scraper. NOT a reverse-engineering tool. NOT for crawling external
> platforms. Only touches Sentinel's own domains.

## What it does

Before any Telegram message goes out in **live** mode, every CTA URL we
publish must pass a real-browser render check:

| Check | Why it matters |
|-------|----------------|
| HTTP 200 | The page is reachable from the public internet |
| Page title not empty | The page actually rendered, not a Next.js error |
| Sentinel AI branding present | We're hitting our deploy, not a wrong host |
| `<input type="email">` visible | Email gate is wired (Week 1 contract) |
| `Context, not financial advice` text present | Compliance disclaimer rendered |
| (optional) Telegram CTA visible | Secondary CTA still in place |

Implementation: `worker/app/marketing/browser_qa.py` (Playwright + pure
HTML detectors).

## When to run

| Trigger | Command |
|---------|---------|
| Before flipping `MARKETING_PUBLISH_DRY_RUN=false` | `--from-feishu --limit 5` |
| New Vercel deploy | `--url https://sentinel.example.com/stocks/NVDA` |
| Daily sanity (manual) | `--from-feishu --notify-feishu` |
| Verifying a single regression | `--url <suspect URL> --ticker NVDA` |

## CLI

```powershell
# Single URL (host machine)
worker/.venv/Scripts/python.exe scripts/marketing_browser_check.py \
    --url https://sentinel.example.com/stocks/NVDA --ticker NVDA

# Pull recent Content Queue rows + check each cta_url
worker/.venv/Scripts/python.exe scripts/marketing_browser_check.py \
    --from-feishu --limit 10

# Same + post a summary card to the Feishu review chat
worker/.venv/Scripts/python.exe scripts/marketing_browser_check.py \
    --from-feishu --notify-feishu

# Require the Telegram secondary CTA to be present too
worker/.venv/Scripts/python.exe scripts/marketing_browser_check.py \
    --url https://sentinel.example.com/stocks/NVDA --require-telegram-cta

# Skip screenshot capture (faster, no disk I/O)
worker/.venv/Scripts/python.exe scripts/marketing_browser_check.py \
    --url https://sentinel.example.com/stocks/NVDA --no-screenshot
```

## Screenshots

Default output directory:

```
D:/code2026/sentinel-ai/获客系统/automation/browser-qa/screenshots/
```

Filename pattern: `{netloc}_{path-slug}_{UTC-timestamp}.png`

The directory is **gitignored** — the only file checked in is this README.
Screenshots are local-only QA artifacts; do not commit them.

On Railway / CI, prefer ephemeral storage (e.g. `/tmp/sentinel-browser-qa`)
since long-term retention isn't needed.

## Hard limits

- **Only Sentinel domains.** The harness does not visit X / Telegram /
  Reddit / Stocktwits / YouTube / TikTok. If you need to render a third-party
  page, that's a different tool — not this one.
- **No login flows.** The CTA pages are public; the harness never authenticates.
- **No mutation.** Pure GET + page render + screenshot. No form submission.

## Why not just `curl + grep`?

Sentinel pages are Next.js client-rendered. A `curl` returns the empty SSR
shell — `<input type="email">` doesn't appear until React hydrates. We need
a real browser to assert that the gate is actually visible.
