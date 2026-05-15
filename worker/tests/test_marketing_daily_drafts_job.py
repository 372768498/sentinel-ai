"""Tests for the daily review-draft job + scheduler gating."""

from __future__ import annotations

import asyncio

import pytest

from app.marketing.content_factory import MultiPlatformComposer
from app.marketing.jobs import generate_always_on_review_drafts, generate_daily_review_drafts
from app.marketing.opportunities import (
    ACTION_CREATE_CONTENT,
    ACTION_WATCH,
    INTENT_TICKER_BUZZ,
    Opportunity,
)
from app.marketing.review_queue import ReviewQueueError


def _opp(ticker: str, score: int, action: str = ACTION_CREATE_CONTENT) -> Opportunity:
    return Opportunity(
        opportunity_id=f"OP-X-20260511-{ticker}",
        source="x",
        ticker=ticker,
        intent=INTENT_TICKER_BUZZ,
        raw_text=f"${ticker} sample",
        url=None,
        author_id=None,
        opportunity_score=score,
        compliance_risk=0,
        suggested_action=action,
        evidence={"sample_count": 30, "top_like_count": 100},
    )


class FakeComposer:
    def compose(self, *, opportunity, platform, cta_url):
        return (
            f"${opportunity.ticker} score {opportunity.opportunity_score}/100. "
            f"Main risk flag: pending review. {cta_url}\n\nContext, not financial advice."
        )


async def _fake_scanner_three(tickers, *, min_score: int = 70):
    return [
        _opp("NVDA", 100),
        _opp("AAPL", 85),
        _opp("TSLA", 75),
    ]


async def _fake_scanner_empty(tickers, *, min_score: int = 70):
    return []


async def _fake_scanner_mixed(tickers, *, min_score: int = 70):
    return [
        _opp("NVDA", 100, action=ACTION_CREATE_CONTENT),
        _opp("AAPL", 50, action=ACTION_WATCH),  # below threshold, filtered out
    ]


async def _fake_scanner_throws(tickers, *, min_score: int = 70):
    raise RuntimeError("scanner exploded")


def test_daily_job_no_opportunities(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MARKETING_TOP_OPPORTUNITIES_PER_DAY", "5")
    monkeypatch.setenv("MARKETING_MIN_OPPORTUNITY_SCORE", "70")

    submitted: list = []

    async def fake_submit(draft, *, client=None, notify_chat=True):
        submitted.append(draft)
        return None

    stats = asyncio.run(
        generate_daily_review_drafts(
            scanner=_fake_scanner_empty,
            composer=FakeComposer(),
            submit_fn=fake_submit,
        )
    )
    assert stats == {
        "session": "daily_0900_et",
        "opportunities": 0,
        "drafts_created": 0,
        "submitted_to_review": 0,
        "skipped": 0,
        "errors": [],
    }
    assert submitted == []


def test_daily_job_happy_path_three_opportunities(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MARKETING_TOP_OPPORTUNITIES_PER_DAY", "5")
    monkeypatch.setenv("GROWTH_OS_PUBLIC_URL", "https://sentinel.example.com")

    submitted: list = []

    async def fake_submit(draft, *, client=None, notify_chat=True):
        submitted.append(draft)
        return None

    stats = asyncio.run(
        generate_daily_review_drafts(
            scanner=_fake_scanner_three,
            composer=FakeComposer(),
            submit_fn=fake_submit,
        )
    )
    # 3 opportunities x 4 Growth Content Pack platforms = 12 drafts
    assert stats["opportunities"] == 3
    assert stats["drafts_created"] == 12
    assert stats["submitted_to_review"] == 12
    assert stats["skipped"] == 0
    assert stats["errors"] == []
    assert len(submitted) == 12
    # Each draft carries source_opportunity_id back to its opportunity
    assert all(d.source_opportunity_id.startswith("OP-X-20260511-") for d in submitted)


def test_daily_job_accepts_hour_level_content_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROWTH_OS_PUBLIC_URL", "https://sentinel.example.com")
    submitted: list = []

    async def fake_submit(draft, *, client=None, notify_chat=True):
        submitted.append(draft)

    stats = asyncio.run(
        generate_daily_review_drafts(
            scanner=_fake_scanner_mixed,
            composer=FakeComposer(),
            submit_fn=fake_submit,
            content_date="202605151300",
            campaign_id="CMP-202605151300-always-on",
        )
    )

    assert stats["drafts_created"] == 4
    assert all(d.content_id.startswith("CT-202605151300-NVDA-") for d in submitted)
    assert all(d.campaign_id == "CMP-202605151300-always-on" for d in submitted)


def test_always_on_job_uses_non_daily_campaign(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROWTH_OS_PUBLIC_URL", "https://sentinel.example.com")
    submitted: list = []

    async def fake_submit(draft, *, client=None, notify_chat=True):
        submitted.append(draft)

    stats = asyncio.run(
        generate_always_on_review_drafts(
            scanner=_fake_scanner_mixed,
            composer=FakeComposer(),
            submit_fn=fake_submit,
        )
    )

    assert stats["session"] == "always_on"
    assert stats["drafts_created"] == 4
    assert all("-always-on" in d.campaign_id for d in submitted)


def test_daily_job_caps_at_top_n(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MARKETING_TOP_OPPORTUNITIES_PER_DAY", "1")
    submitted: list = []

    async def fake_submit(draft, *, client=None, notify_chat=True):
        submitted.append(draft)

    stats = asyncio.run(
        generate_daily_review_drafts(
            scanner=_fake_scanner_three,
            composer=FakeComposer(),
            submit_fn=fake_submit,
        )
    )
    # Top 1 x 4 Growth Content Pack platforms
    assert stats["opportunities"] == 3
    assert stats["drafts_created"] == 4
    assert stats["submitted_to_review"] == 4


def test_daily_job_skips_non_create_actions(monkeypatch: pytest.MonkeyPatch) -> None:
    submitted: list = []

    async def fake_submit(draft, *, client=None, notify_chat=True):
        submitted.append(draft)

    stats = asyncio.run(
        generate_daily_review_drafts(
            scanner=_fake_scanner_mixed,
            composer=FakeComposer(),
            submit_fn=fake_submit,
        )
    )
    # Only NVDA (create_content) reaches the Growth Content Pack.
    assert stats["opportunities"] == 2
    assert stats["drafts_created"] == 4
    tickers = {d.ticker for d in submitted}
    assert tickers == {"NVDA"}


def test_daily_job_submit_failure_counted_as_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    call_count = {"n": 0}

    async def flaky_submit(draft, *, client=None, notify_chat=True):
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise ReviewQueueError("feishu down")

    stats = asyncio.run(
        generate_daily_review_drafts(
            scanner=_fake_scanner_three,
            composer=FakeComposer(),
            submit_fn=flaky_submit,
        )
    )
    assert stats["drafts_created"] == 12
    assert stats["submitted_to_review"] == 11
    assert stats["skipped"] == 1
    assert len(stats["errors"]) == 1


def test_daily_job_refuses_without_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    submitted: list = []

    async def fake_submit(draft, *, client=None, notify_chat=True):
        submitted.append(draft)

    # Pass composer=None so default MultiPlatformComposer() construction happens,
    # which should raise, so the job returns error stats with no submissions.
    stats = asyncio.run(
        generate_daily_review_drafts(
            scanner=_fake_scanner_three,
            composer=None,
            submit_fn=fake_submit,
        )
    )
    assert stats["drafts_created"] == 0
    assert stats["submitted_to_review"] == 0
    assert stats["skipped"] == 12
    assert len(stats["errors"]) == 1
    assert "ANTHROPIC_API_KEY missing" in stats["errors"][0]
    assert submitted == []


def test_daily_job_scanner_exception_captured(monkeypatch: pytest.MonkeyPatch) -> None:
    submitted: list = []

    async def fake_submit(draft, *, client=None, notify_chat=True):
        submitted.append(draft)

    stats = asyncio.run(
        generate_daily_review_drafts(
            scanner=_fake_scanner_throws,
            composer=FakeComposer(),
            submit_fn=fake_submit,
        )
    )
    assert stats["opportunities"] == 0
    assert stats["drafts_created"] == 0
    assert len(stats["errors"]) == 1
    assert "scanner" in stats["errors"][0]


# -----------------------------------------------------------------------------
# Scheduler gating
# -----------------------------------------------------------------------------


def test_scheduler_skipped_when_all_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in (
        "SCANNER_ENABLED",
        "BOT_ENABLED",
        "MARKETING_ENABLED",
        "MARKETING_DAILY_DRAFT_ENABLED",
        "MARKETING_ALWAYS_ON_DRAFT_ENABLED",
        "MARKETING_ACQUISITION_OPERATOR_ENABLED",
    ):
        monkeypatch.delenv(var, raising=False)
    from app.scheduler import build_scheduler

    assert build_scheduler() is None


def test_scheduler_registers_daily_draft_job_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("SCANNER_ENABLED", "BOT_ENABLED", "MARKETING_ENABLED"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("MARKETING_DAILY_DRAFT_ENABLED", "true")
    monkeypatch.setenv("MARKETING_DAILY_DRAFT_HOUR_ET", "9")

    from app.scheduler import build_scheduler

    scheduler = build_scheduler()
    assert scheduler is not None
    jobs = {job.id: job for job in scheduler.get_jobs()}
    assert "marketing-daily-drafts" in jobs
    job = jobs["marketing-daily-drafts"]
    assert str(job.trigger.timezone) == "America/New_York"
    # Verify hour=9 in the cron trigger fields
    fields = {f.name: str(f) for f in job.trigger.fields}
    assert fields["hour"] == "9"
    assert fields["minute"] == "0"
    assert fields["day_of_week"] in ("mon-fri", "0-4")
    # not started, so no shutdown needed


def test_scheduler_respects_custom_hour(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("SCANNER_ENABLED", "BOT_ENABLED", "MARKETING_ENABLED"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("MARKETING_DAILY_DRAFT_ENABLED", "true")
    monkeypatch.setenv("MARKETING_DAILY_DRAFT_HOUR_ET", "8")

    from app.scheduler import build_scheduler

    scheduler = build_scheduler()
    assert scheduler is not None
    job = scheduler.get_job("marketing-daily-drafts")
    fields = {f.name: str(f) for f in job.trigger.fields}
    assert fields["hour"] == "8"
    # not started, so no shutdown needed


def test_scheduler_registers_always_on_draft_job(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in (
        "SCANNER_ENABLED",
        "BOT_ENABLED",
        "MARKETING_ENABLED",
        "MARKETING_DAILY_DRAFT_ENABLED",
        "MARKETING_ACQUISITION_OPERATOR_ENABLED",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("MARKETING_ALWAYS_ON_DRAFT_ENABLED", "true")
    monkeypatch.setenv("MARKETING_ALWAYS_ON_DRAFT_INTERVAL_MINUTES", "120")

    from app.scheduler import build_scheduler

    scheduler = build_scheduler()
    assert scheduler is not None
    job = scheduler.get_job("marketing-always-on-drafts")
    assert job is not None
    assert int(job.trigger.interval.total_seconds()) == 120 * 60


def test_scheduler_registers_acquisition_operator(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in (
        "SCANNER_ENABLED",
        "BOT_ENABLED",
        "MARKETING_ENABLED",
        "MARKETING_DAILY_DRAFT_ENABLED",
        "MARKETING_ALWAYS_ON_DRAFT_ENABLED",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("MARKETING_ACQUISITION_OPERATOR_ENABLED", "true")
    monkeypatch.setenv("MARKETING_ACQUISITION_OPERATOR_HOUR_ET", "10")

    from app.scheduler import build_scheduler

    scheduler = build_scheduler()
    assert scheduler is not None
    job = scheduler.get_job("marketing-acquisition-operator")
    assert job is not None
    fields = {f.name: str(f) for f in job.trigger.fields}
    assert fields["hour"] == "10"
    assert fields["minute"] == "15"
    assert fields["day_of_week"] in ("mon-fri", "0-4")
