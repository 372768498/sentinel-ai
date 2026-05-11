"""Manual brief CLI — generate review drafts for a hand-picked ticker list.

Use when:
  - X bearer token unavailable / app suspended / API tier won't allow recent search
  - You want a one-off "today, scan THESE tickers" run outside the scheduler
  - Testing the Content Factory + Feishu pipeline with no external scrapers

For each ticker, the script fabricates a single high-score Opportunity (no
X buzz data), runs Content Factory to compose three platform drafts (X /
Telegram / YouTube Shorts), and submits each to the Feishu Review Queue.

Usage:
    # Dry-run (no Feishu submit, just see what Anthropic produces)
    worker/.venv/Scripts/python.exe scripts/feishu/manual_brief.py \\
        --tickers NVDA TSLA --no-feishu

    # Live — drafts land in Feishu Content Queue + bot pushes review cards
    worker/.venv/Scripts/python.exe scripts/feishu/manual_brief.py --tickers NVDA

    # Override score / risk
    worker/.venv/Scripts/python.exe scripts/feishu/manual_brief.py \\
        --tickers AAPL --score 78 --compliance-risk 15
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKER_DIR = REPO_ROOT / "worker"


def _load_env_local(path: Path) -> None:
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def main() -> int:
    parser = argparse.ArgumentParser(description="Manual ticker brief → Content Factory → Feishu")
    parser.add_argument("--tickers", nargs="+", required=True, help="Ticker symbols, space-separated")
    parser.add_argument("--score", type=int, default=85, help="opportunity_score per ticker (0-100)")
    parser.add_argument("--compliance-risk", type=int, default=10, help="compliance_risk per ticker")
    parser.add_argument("--no-feishu", action="store_true", help="Skip Feishu submit, print drafts only")
    parser.add_argument("--source", default="manual", help="Opportunity.source label")
    args = parser.parse_args()

    if not 0 <= args.score <= 100:
        print("[error] --score must be 0-100", file=sys.stderr)
        return 2
    if not 0 <= args.compliance_risk <= 100:
        print("[error] --compliance-risk must be 0-100", file=sys.stderr)
        return 2

    _load_env_local(REPO_ROOT / ".env.local")
    sys.path.insert(0, str(WORKER_DIR))

    from app.marketing.jobs import generate_daily_review_drafts
    from app.marketing.opportunities import (
        ACTION_CREATE_CONTENT,
        INTENT_TICKER_BUZZ,
        Opportunity,
    )
    from app.marketing.review_queue import submit_draft_to_review

    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    tickers = [t.strip().upper() for t in args.tickers if t.strip()]

    def _build_opportunity(ticker: str) -> Opportunity:
        return Opportunity(
            opportunity_id=f"OP-MAN-{today}-{ticker}",
            source=args.source,
            ticker=ticker,
            intent=INTENT_TICKER_BUZZ,
            raw_text=f"Manual brief for ${ticker} — operator-selected ticker for today.",
            url=None,
            author_id=None,
            opportunity_score=args.score,
            compliance_risk=args.compliance_risk,
            suggested_action=ACTION_CREATE_CONTENT,
            evidence={"manual_brief": True, "selected_at": today},
        )

    async def manual_scanner(_unused_tickers, *, min_score: int = 70):
        return [_build_opportunity(t) for t in tickers if args.score >= min_score]

    submitted: list = []

    async def fake_submit(draft, *, client=None, notify_chat=True):
        submitted.append(draft)
        print(f"  [dry-run] {draft.content_id} ({draft.platform})")
        return None

    submit_fn = fake_submit if args.no_feishu else submit_draft_to_review

    session = f"manual_brief_{today}"
    mode = "DRY-RUN (composer only)" if args.no_feishu else "LIVE (writing to Feishu)"
    print(f"[manual-brief] session={session} tickers={tickers} mode={mode}")
    print(f"[manual-brief] score={args.score} compliance_risk={args.compliance_risk}")

    try:
        result = asyncio.run(
            generate_daily_review_drafts(
                session_label=session,
                scanner=manual_scanner,
                submit_fn=submit_fn,
            )
        )
    except Exception as exc:
        print(f"[error] pipeline failed: {exc}", file=sys.stderr)
        return 1

    print()
    print("─" * 60)
    print(f"opportunities       : {result['opportunities']}")
    print(f"drafts_created      : {result['drafts_created']}")
    print(f"submitted_to_review : {result['submitted_to_review']}")
    print(f"skipped             : {result['skipped']}")
    if result["errors"]:
        print("errors:")
        for e in result["errors"]:
            print(f"  - {e}")
    print("─" * 60)
    return 0 if not result["errors"] else 1


if __name__ == "__main__":
    sys.exit(main())
