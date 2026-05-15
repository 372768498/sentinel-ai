from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from app.marketing.acquisition_operator import run_daily_acquisition_operator
from app.marketing.opportunities import ACTION_CREATE_CONTENT, INTENT_TICKER_BUZZ, Opportunity
from app.marketing.review_queue import ReviewQueueError


def _opp(ticker: str = "NVDA", score: int = 90) -> Opportunity:
    return Opportunity(
        opportunity_id=f"OP-X-20260515-{ticker}",
        source="x",
        ticker=ticker,
        intent=INTENT_TICKER_BUZZ,
        raw_text=f"${ticker} attention, margins, and valuation pressure overlap today.",
        url="https://x.com/i/web/status/123",
        author_id="u1",
        opportunity_score=score,
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


class FakeComposer:
    def compose(self, *, opportunity, platform: str, cta_url: str) -> str:
        return (
            f"${opportunity.ticker} has three signals firing right now.\n"
            "Risk flag: expectation crowding.\n"
            "Risk flag: margin sensitivity.\n"
            f"Stock context preview: {cta_url}\n\n"
            "Context, not financial advice."
        )


async def _scanner(tickers, *, min_score: int = 70):
    return [_opp()]


def test_operator_writes_summary_and_video_packs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROWTH_OS_PUBLIC_URL", "https://sentinel.example.com")
    submitted = []

    async def submit_fn(draft, *, client=None, notify_chat=True):
        submitted.append(draft.content_id)

    result = asyncio.run(
        run_daily_acquisition_operator(
            scanner=_scanner,
            composer=FakeComposer(),
            submit_fn=submit_fn,
            output_root=tmp_path,
            content_date="202605151315",
            campaign_id="CMP-202605151315-operator",
        )
    )

    assert result["run_id"] == "202605151315"
    assert result["opportunities_selected"] == 1
    assert result["drafts_created"] == 4
    assert result["submitted_to_review"] == 4
    assert result["video_packs_created"] == 2
    assert result["blocked_count"] == 0
    assert len(submitted) == 4

    out_dir = tmp_path / "202605151315"
    assert (out_dir / "growth_run_summary.json").exists()
    assert (out_dir / "content_queue_summary.md").exists()
    assert (out_dir / "video_pack_index.md").exists()
    assert (out_dir / "blocked_items.md").exists()
    assert (out_dir / "next_actions.md").exists()

    summary = json.loads((out_dir / "growth_run_summary.json").read_text(encoding="utf-8"))
    assert summary["drafts_created"] == 4

    video_packs = list((out_dir / "video_packs").iterdir())
    assert {pack.name[-2:] for pack in video_packs} == {"yt", "tt"}
    for pack in video_packs:
        qa = json.loads((pack / "qa_report.json").read_text(encoding="utf-8"))
        assert qa["ok"]
        assert (pack / "script.md").exists()
        assert (pack / "shot_plan.json").exists()


def test_operator_records_submit_failures(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROWTH_OS_PUBLIC_URL", "https://sentinel.example.com")

    async def submit_fn(draft, *, client=None, notify_chat=True):
        raise ReviewQueueError("review queue down")

    result = asyncio.run(
        run_daily_acquisition_operator(
            scanner=_scanner,
            composer=FakeComposer(),
            submit_fn=submit_fn,
            output_root=tmp_path,
            content_date="202605151400",
        )
    )

    assert result["submitted_to_review"] == 0
    assert result["blocked_count"] == 4
    assert len(result["errors"]) == 4
    blocked = (tmp_path / "202605151400" / "blocked_items.md").read_text(encoding="utf-8")
    assert "review queue down" in blocked


def test_operator_refuses_default_composer_without_api_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    result = asyncio.run(
        run_daily_acquisition_operator(
            scanner=_scanner,
            composer=None,
            output_root=tmp_path,
            content_date="202605151500",
        )
    )

    assert result["drafts_created"] == 0
    assert result["submitted_to_review"] == 0
    assert result["blocked_count"] == 4
    assert "ANTHROPIC_API_KEY missing" in result["errors"][0]
    assert (tmp_path / "202605151500" / "growth_run_summary.json").exists()
