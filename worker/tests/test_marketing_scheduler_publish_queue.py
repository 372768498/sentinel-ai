"""Tests for scheduler.build_scheduler — Week 4 queue-poller gating."""

from __future__ import annotations

import pytest


def _clear_all(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in (
        "SCANNER_ENABLED",
        "BOT_ENABLED",
        "MARKETING_ENABLED",
        "MARKETING_DAILY_DRAFT_ENABLED",
        "MARKETING_ALWAYS_ON_DRAFT_ENABLED",
        "MARKETING_ALWAYS_ON_DRAFT_INTERVAL_MINUTES",
        "MARKETING_QUEUE_POLL_ENABLED",
        "MARKETING_PUBLISH_DRY_RUN",
        "MARKETING_QUEUE_POLL_INTERVAL_SECONDS",
    ):
        monkeypatch.delenv(var, raising=False)


def test_scheduler_disabled_when_no_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_all(monkeypatch)
    from app.scheduler import build_scheduler

    assert build_scheduler() is None


def test_scheduler_registers_review_poller_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_all(monkeypatch)
    monkeypatch.setenv("MARKETING_QUEUE_POLL_ENABLED", "true")
    monkeypatch.setenv("MARKETING_QUEUE_POLL_INTERVAL_SECONDS", "300")

    from app.scheduler import build_scheduler

    scheduler = build_scheduler()
    assert scheduler is not None
    job = scheduler.get_job("marketing-review-poller")
    assert job is not None
    # IntervalTrigger interval seconds = 300
    assert int(job.trigger.interval.total_seconds()) == 300


def test_scheduler_respects_custom_interval(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_all(monkeypatch)
    monkeypatch.setenv("MARKETING_QUEUE_POLL_ENABLED", "true")
    monkeypatch.setenv("MARKETING_QUEUE_POLL_INTERVAL_SECONDS", "120")

    from app.scheduler import build_scheduler

    scheduler = build_scheduler()
    job = scheduler.get_job("marketing-review-poller")
    assert int(job.trigger.interval.total_seconds()) == 120


def test_scheduler_clamps_interval_floor(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_all(monkeypatch)
    monkeypatch.setenv("MARKETING_QUEUE_POLL_ENABLED", "true")
    monkeypatch.setenv("MARKETING_QUEUE_POLL_INTERVAL_SECONDS", "5")  # below 30s floor

    from app.scheduler import build_scheduler

    scheduler = build_scheduler()
    job = scheduler.get_job("marketing-review-poller")
    assert int(job.trigger.interval.total_seconds()) == 30


def test_scheduler_no_poller_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_all(monkeypatch)
    monkeypatch.setenv("MARKETING_DAILY_DRAFT_ENABLED", "true")
    # MARKETING_QUEUE_POLL_ENABLED not set

    from app.scheduler import build_scheduler

    scheduler = build_scheduler()
    assert scheduler.get_job("marketing-daily-drafts") is not None
    assert scheduler.get_job("marketing-review-poller") is None


def test_dry_run_default_true(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_all(monkeypatch)
    from app.scheduler import _publish_is_live

    # When MARKETING_PUBLISH_DRY_RUN is unset, default is dry-run (safe)
    assert _publish_is_live() is False


def test_publish_live_when_dry_run_false(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MARKETING_PUBLISH_DRY_RUN", "false")
    from app.scheduler import _publish_is_live

    assert _publish_is_live() is True


def test_scheduler_registers_daily_digest_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_all(monkeypatch)
    monkeypatch.setenv("MARKETING_DAILY_DIGEST_ENABLED", "true")
    monkeypatch.setenv("MARKETING_DAILY_DIGEST_HOUR_ET", "16")
    monkeypatch.setenv("MARKETING_DAILY_DIGEST_MINUTE_ET", "30")

    from app.scheduler import build_scheduler

    scheduler = build_scheduler()
    assert scheduler is not None
    job = scheduler.get_job("marketing-daily-digest")
    assert job is not None
    fields = {f.name: str(f) for f in job.trigger.fields}
    assert fields["hour"] == "16"
    assert fields["minute"] == "30"
    assert fields["day_of_week"] in ("mon-fri", "0-4")
    assert str(job.trigger.timezone) == "America/New_York"


def test_scheduler_digest_respects_custom_time(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_all(monkeypatch)
    monkeypatch.setenv("MARKETING_DAILY_DIGEST_ENABLED", "true")
    monkeypatch.setenv("MARKETING_DAILY_DIGEST_HOUR_ET", "17")
    monkeypatch.setenv("MARKETING_DAILY_DIGEST_MINUTE_ET", "15")

    from app.scheduler import build_scheduler

    scheduler = build_scheduler()
    job = scheduler.get_job("marketing-daily-digest")
    fields = {f.name: str(f) for f in job.trigger.fields}
    assert fields["hour"] == "17"
    assert fields["minute"] == "15"


def _clear_all_full(monkeypatch: pytest.MonkeyPatch) -> None:
    """Newer _clear_all variant that also drops the Week 5 vars."""
    _clear_all(monkeypatch)
    for var in (
        "MARKETING_DAILY_DIGEST_ENABLED",
        "MARKETING_DAILY_DIGEST_HOUR_ET",
        "MARKETING_DAILY_DIGEST_MINUTE_ET",
    ):
        monkeypatch.delenv(var, raising=False)


def test_scheduler_disabled_includes_digest_check(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_all_full(monkeypatch)
    from app.scheduler import build_scheduler

    assert build_scheduler() is None
