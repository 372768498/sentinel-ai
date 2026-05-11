"""End-to-end smoke for the daily review-draft pipeline.

Loads .env.local, runs `generate_daily_review_drafts()` once, prints stats.

Usage:
    worker/.venv/Scripts/python.exe scripts/marketing_daily_smoke.py

Optional flags:
    --tickers NVDA AAPL    Override default watchlist
    --no-feishu            Skip Feishu submission (dry-run composer only)
    --probe-only           Just call Anthropic with one trivial prompt to test the proxy
    --mock-opps            Use a single fake NVDA opportunity (bypass X scanner)
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
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
    parser = argparse.ArgumentParser()
    parser.add_argument("--tickers", nargs="*", default=None)
    parser.add_argument("--no-feishu", action="store_true")
    parser.add_argument("--probe-only", action="store_true")
    parser.add_argument("--mock-opps", action="store_true")
    args = parser.parse_args()

    _load_env_local(REPO_ROOT / ".env.local")
    sys.path.insert(0, str(WORKER_DIR))

    if args.probe_only:
        from app.marketing.content_factory import MultiPlatformComposer
        from app.marketing.opportunities import (
            ACTION_CREATE_CONTENT,
            INTENT_TICKER_BUZZ,
            Opportunity,
        )

        cmp = MultiPlatformComposer()
        probe_opp = Opportunity(
            opportunity_id="OP-PROBE-NVDA",
            source="x",
            ticker="NVDA",
            intent=INTENT_TICKER_BUZZ,
            raw_text="Test buzz sample",
            url=None,
            author_id=None,
            opportunity_score=85,
            compliance_risk=0,
            suggested_action=ACTION_CREATE_CONTENT,
            evidence={"sample_count": 30, "top_like_count": 100},
        )
        cta = "http://localhost:3000/stocks/NVDA?utm_source=probe"
        print(f"[probe] model={cmp.model}, base_url={os.environ.get('ANTHROPIC_BASE_URL') or '(default)'}")
        try:
            text = cmp.compose(opportunity=probe_opp, platform="X", cta_url=cta)
        except Exception as exc:
            print(f"[probe] FAILED: {exc}", file=sys.stderr)
            return 1
        print("[probe] OK — output below:")
        print("─" * 60)
        print(text)
        print("─" * 60)
        return 0

    from app.marketing.jobs import generate_daily_review_drafts
    from app.marketing.review_queue import submit_draft_to_review

    submitted: list = []

    async def fake_submit(draft, *, client=None, notify_chat=True):
        submitted.append(draft)
        print(f"  [fake-submit] {draft.content_id} ({draft.platform})")
        return None

    submit_fn = fake_submit if args.no_feishu else submit_draft_to_review
    kwargs: dict = {"submit_fn": submit_fn}
    if args.tickers:
        kwargs["tickers"] = args.tickers

    if args.mock_opps:
        from app.marketing.opportunities import (
            ACTION_CREATE_CONTENT,
            INTENT_TICKER_BUZZ,
            Opportunity,
        )

        async def mock_scanner(_tickers, *, min_score: int = 70):
            return [
                Opportunity(
                    opportunity_id="OP-MOCK-20260511-NVDA",
                    source="x",
                    ticker="NVDA",
                    intent=INTENT_TICKER_BUZZ,
                    raw_text="$NVDA seeing elevated discussion around Q3 export-restriction risk and AI margin expansion.",
                    url="https://x.com/i/web/status/000",
                    author_id="u_mock",
                    opportunity_score=85,
                    compliance_risk=10,
                    suggested_action=ACTION_CREATE_CONTENT,
                    evidence={"sample_count": 28, "top_like_count": 142, "top_tweet_id": "000"},
                )
            ]

        kwargs["scanner"] = mock_scanner
        print("[daily-smoke] using mock NVDA opportunity (skipping X scanner)")

    print("[daily-smoke] starting generate_daily_review_drafts...")
    result = asyncio.run(generate_daily_review_drafts(**kwargs))
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
