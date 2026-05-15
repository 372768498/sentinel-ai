from __future__ import annotations

import asyncio
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "worker"))

from app.marketing.acquisition_operator import run_daily_acquisition_operator
from app.marketing.opportunities import ACTION_CREATE_CONTENT, INTENT_TICKER_BUZZ, Opportunity


class SmokeComposer:
    def compose(self, *, opportunity, platform: str, cta_url: str) -> str:
        return (
            f"${opportunity.ticker} has three signals firing right now.\n"
            "Risk flag: expectation crowding.\n"
            "Risk flag: margin sensitivity.\n"
            f"Stock context preview: {cta_url}\n\n"
            "Context, not financial advice."
        )


async def smoke_scanner(tickers, *, min_score: int = 70):
    return [
        Opportunity(
            opportunity_id="OP-SMOKE-20260515-NVDA",
            source="smoke",
            ticker="NVDA",
            intent=INTENT_TICKER_BUZZ,
            raw_text="$NVDA attention, margins, and valuation pressure overlap today.",
            url="https://example.com/smoke/nvda",
            author_id="smoke",
            opportunity_score=95,
            compliance_risk=0,
            suggested_action=ACTION_CREATE_CONTENT,
            evidence={
                "risk_flags": [
                    "Expectation crowding",
                    "Margin sensitivity",
                    "Valuation compression",
                ],
                "why_now": "Attention, margins, and valuation pressure overlap today.",
            },
            state="heated",
        )
    ]


async def smoke_submit(draft, *, client=None, notify_chat=True):
    return {"record_id": f"smoke-{draft.content_id}", "review_status": "Pending"}


async def smoke_kpi_fetcher(start, end):
    return {
        "CT-20260515-NVDA-x": {
            "clicks": 100,
            "emails_captured": 10,
            "signups": 6,
            "paid_users": 1,
        },
        "CT-20260515-NVDA-rd": {
            "clicks": 20,
            "emails_captured": 0,
            "signups": 0,
            "paid_users": 0,
        },
    }


def main() -> int:
    result = asyncio.run(
        run_daily_acquisition_operator(
            session_label="local_smoke",
            scanner=smoke_scanner,
            composer=SmokeComposer(),
            submit_fn=smoke_submit,
            kpi_fetcher=smoke_kpi_fetcher,
            output_root=REPO_ROOT / "docs" / "growth-runs",
            content_date="local-smoke",
            campaign_id="CMP-local-smoke",
        )
    )
    print("本地 Operator 冒烟测试完成")
    print(f"run_id={result['run_id']}")
    print(f"output_dir={result['output_dir']}")
    print(f"drafts_created={result['drafts_created']}")
    print(f"submitted_to_review={result['submitted_to_review']}")
    print(f"video_packs_created={result['video_packs_created']}")
    print(f"kpi_items_reviewed={result['kpi_items_reviewed']}")
    print(f"blocked_count={result['blocked_count']}")
    return 0 if not result["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
