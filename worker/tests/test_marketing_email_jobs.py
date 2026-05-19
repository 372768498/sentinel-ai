"""Tests for the Free Email Daily Radar wire-up.

Covers:
  - SQL fetch shape (verified-only filter, only_email path)
  - safety guard: bulk live refuses without allow_bulk
  - dry-run never invokes Resend
  - only-email path collapses to exactly one recipient
  - Anomaly vs Nothing branch selection
  - seed_section assembly with mixed states (HEATED + CALM fallback)
  - scheduler registers the email job when MARKETING_EMAIL_DAILY_ENABLED=true
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from app.marketing.email_jobs import (
    VerifiedLead,
    _select_top_profile,
    _seed_for_lead,
    _split_subject_preview,
    _render_for_lead,
    send_via_resend,
    send_email_digest,
)
from app.marketing.intelligence import TickerIntelligenceProfile
from app.marketing.state import SentinelState


# ---------------------------------------------------------------------------
# Profile factories
# ---------------------------------------------------------------------------


def _profile(
    ticker: str,
    *,
    market: int = 0,
    social: int = 0,
    search: int = 0,
    news: int = 0,
    competitor: int = 0,
    why_now: str = "context",
) -> TickerIntelligenceProfile:
    """Build a TickerIntelligenceProfile with the heat dials we want."""
    return TickerIntelligenceProfile(
        ticker=ticker,
        company_name=f"{ticker} Inc.",
        market_heat=market,
        social_heat=social,
        search_heat=search,
        news_heat=news,
        competitor_heat=competitor,
        overall_opportunity=(market + social + search + news + competitor) // 5,
        why_now=why_now,
        market_signals=("Intraday +3.2%", "Volume 12,345,678"),
        social_signals=(),
        catalysts=("8-K · Earnings beat (2026-05-12)",),
        recommended_angles=("Anomaly story",),
        evidence={
            "mover": {
                "price": 150.0,
                "change_pct": 3.2,
                "volume": 12_345_678,
                "market_cap": 2.5e12,
                "relative_volume": 2.1,
                "source_url": f"https://example.com/{ticker}",
            },
            "social_intent_counts": {},
            "youtube_signal_count": 0,
            "catalyst_count": 1,
            "sources_used": 3,
            "generated_at": "2026-05-13T12:00:00+00:00",
        },
        confidence="medium",
    )


def _heated_profile(ticker: str = "NVDA") -> TickerIntelligenceProfile:
    return _profile(
        ticker,
        market=80,
        social=75,
        search=70,
        news=80,
        competitor=10,
        why_now=f"${ticker} multi-signal firing across price, social, and SEC filings.",
    )


def _calm_profile(ticker: str = "MSFT") -> TickerIntelligenceProfile:
    return _profile(
        ticker,
        market=5,
        social=5,
        search=5,
        news=5,
        competitor=5,
        why_now=f"${ticker} quiet today.",
    )


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def test_split_subject_preview_pulls_headers() -> None:
    rendered = (
        "Subject: Heated: $NVDA — multi-signal firing\n"
        "Preview: Setup + reflection question.\n"
        "\n"
        "─────────────────────────\n"
        "BODY START\n"
    )
    subject, preview, body = _split_subject_preview(rendered)
    assert subject == "Heated: $NVDA — multi-signal firing"
    assert preview == "Setup + reflection question."
    assert body.startswith("─" * 5)
    assert "BODY START" in body


def test_select_top_profile_picks_first_non_calm() -> None:
    profiles = [_calm_profile("AAPL"), _heated_profile("NVDA"), _calm_profile("TSLA")]
    top = _select_top_profile(profiles)
    assert top is not None
    assert top.ticker == "NVDA"


def test_select_top_profile_returns_none_when_all_calm() -> None:
    profiles = [_calm_profile("AAPL"), _calm_profile("MSFT")]
    assert _select_top_profile(profiles) is None


def test_seed_for_lead_falls_back_to_calm_when_no_profile() -> None:
    profiles = {p.ticker: p for p in [_heated_profile("NVDA")]}
    section = _seed_for_lead(("NVDA", "ZZZZ"), profiles)
    # NVDA → any non-CALM state (factory has 4 high-heat signals + a filing,
    # so resolve_state actually returns INFLECTION). ZZZZ has no profile → CALM.
    assert "NVDA" in section
    assert any(label in section for label in ("Heated", "Watching", "Inflection"))
    assert "ZZZZ" in section
    assert "Calm" in section


def test_seed_for_lead_empty_returns_empty_string() -> None:
    assert _seed_for_lead((), {}) == ""


# ---------------------------------------------------------------------------
# Orchestrator — safety + branching
# ---------------------------------------------------------------------------


class _SendRecorder:
    """Mirror of send_via_resend that records calls without HTTP."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def __call__(
        self,
        *,
        api_key: str,
        from_email: str,
        to_email: str,
        subject: str,
        text_body: str | None,
        html_body: str | None = None,
        dry_run: bool,
    ) -> str | None:
        self.calls.append(
            {
                "to": to_email,
                "subject": subject,
                "dry_run": dry_run,
                "from": from_email,
                "has_text": bool(text_body),
                "has_html": bool(html_body),
            }
        )
        return None if dry_run else f"msg-{len(self.calls)}"


async def _fake_intel_heated(*, seed_tickers, limit):
    profiles = [_heated_profile("NVDA"), _calm_profile("MSFT")]
    return profiles[:limit]


async def _fake_intel_all_calm(*, seed_tickers, limit):
    profiles = [_calm_profile(t) for t in seed_tickers[: max(1, limit)]]
    return profiles


async def _fake_market_brief() -> str:
    return (
        "MARKET SNAPSHOT / 市场总览\n"
        "- Indexes / 指数: SPY -1.20% · QQQ -1.51%\n\n"
        "SENTINEL WATCH / 今日盯防\n"
        "- Biggest sector spread / 最大板块剪刀差: XLE +2.36% vs XLK -1.81%"
    )


def _fake_market_brief_subject() -> tuple[str, str]:
    return (
        "Sentinel AI 美股市场日报：科技与小盘承压，能源逆势",
        "SPY -1.20% · QQQ -1.51% · IWM -2.41% · VIX 18.43",
    )


def _verified(email: str, seeds: tuple[str, ...] = ()) -> VerifiedLead:
    return VerifiedLead(email=email, seed_tickers=seeds)


def test_send_email_digest_refuses_bulk_live_without_allow_bulk() -> None:
    async def leads_fetcher(*, limit):
        return [_verified("a@example.com"), _verified("b@example.com")]

    stats = asyncio.run(
        send_email_digest(
            live=True,
            allow_bulk=False,
            intel_fetcher=_fake_intel_heated,
            leads_fetcher=leads_fetcher,
            resend_sender=_SendRecorder(),
            market_brief_fetcher=_fake_market_brief,
            market_brief_subject_fetcher=_fake_market_brief_subject,
        )
    )
    assert stats["mode"] == "live"
    assert stats["sent"] == 0
    assert stats["errors"] and "bulk live send refused" in stats["errors"][0]


def test_send_email_digest_dry_run_skips_resend_post() -> None:
    async def leads_fetcher(*, limit):
        return [_verified("a@example.com", ("NVDA",))]

    recorder = _SendRecorder()
    stats = asyncio.run(
        send_email_digest(
            live=False,
            intel_fetcher=_fake_intel_heated,
            leads_fetcher=leads_fetcher,
            resend_sender=recorder,
            market_brief_fetcher=_fake_market_brief,
            market_brief_subject_fetcher=_fake_market_brief_subject,
        )
    )
    assert stats["mode"] == "dry-run"
    assert stats["sent"] == 1
    assert len(recorder.calls) == 1
    assert recorder.calls[0]["dry_run"] is True
    assert recorder.calls[0]["has_text"] is False
    assert recorder.calls[0]["has_html"] is True


def test_render_for_lead_returns_html_email_body() -> None:
    lead = _verified("a@example.com", ("NVDA",))
    subject, preview, text_body, html_body = _render_for_lead(
        lead=lead,
        profiles=[_heated_profile("NVDA")],
        now_et=datetime(2026, 5, 18, 12, 15, tzinfo=timezone.utc),
        public_url="https://sentinelai.com",
        pro_url="https://sentinelai.com/pro",
        methodology_url="https://sentinelai.com/methodology",
        scan_universe_size=2000,
        day_offset=1,
    )

    assert "$NVDA" in subject
    assert preview
    assert "Context, not financial advice" in text_body
    assert "<!doctype html>" in html_body
    assert "Sentinel AI" in html_body
    assert "https://sentinelai.com/stocks/NVDA" in html_body


def test_send_email_digest_only_email_single_recipient() -> None:
    async def single_fetcher(email):
        if email == "vip@example.com":
            return _verified("vip@example.com", ("NVDA",))
        return None

    recorder = _SendRecorder()
    stats = asyncio.run(
        send_email_digest(
            live=True,
            only_email="vip@example.com",
            intel_fetcher=_fake_intel_heated,
            single_lead_fetcher=single_fetcher,
            resend_sender=recorder,
            market_brief_fetcher=_fake_market_brief,
            market_brief_subject_fetcher=_fake_market_brief_subject,
        )
    )
    assert stats["sent"] == 1
    assert len(recorder.calls) == 1
    assert recorder.calls[0]["to"] == "vip@example.com"
    assert recorder.calls[0]["dry_run"] is False


def test_send_email_digest_only_email_unknown_skipped() -> None:
    async def single_fetcher(email):
        return None

    recorder = _SendRecorder()
    stats = asyncio.run(
        send_email_digest(
            live=True,
            only_email="nobody@example.com",
            intel_fetcher=_fake_intel_heated,
            single_lead_fetcher=single_fetcher,
            resend_sender=recorder,
            market_brief_fetcher=_fake_market_brief,
            market_brief_subject_fetcher=_fake_market_brief_subject,
        )
    )
    assert stats["sent"] == 0
    assert stats["skipped_unverified"] == 1
    assert recorder.calls == []


def test_send_email_digest_anomaly_branch_renders_subject_with_state() -> None:
    async def leads_fetcher(*, limit):
        return [_verified("a@example.com", ("NVDA",))]

    recorder = _SendRecorder()
    stats = asyncio.run(
        send_email_digest(
            live=False,
            intel_fetcher=_fake_intel_heated,
            leads_fetcher=leads_fetcher,
            resend_sender=recorder,
            market_brief_fetcher=_fake_market_brief,
            market_brief_subject_fetcher=_fake_market_brief_subject,
        )
    )
    assert stats["renders"][0]["branch"] == "anomaly"
    subject = stats["renders"][0]["subject"]
    assert "$NVDA" in subject
    # The label must be a public Sentinel state word
    assert any(label in subject for label in ("Heated", "Watching", "Inflection"))


def test_send_email_digest_nothing_branch_when_all_calm() -> None:
    async def leads_fetcher(*, limit):
        return [_verified("a@example.com", ("MSFT",))]

    recorder = _SendRecorder()
    stats = asyncio.run(
        send_email_digest(
            live=False,
            intel_fetcher=_fake_intel_all_calm,
            leads_fetcher=leads_fetcher,
            resend_sender=recorder,
            market_brief_fetcher=_fake_market_brief,
            market_brief_subject_fetcher=_fake_market_brief_subject,
        )
    )
    assert stats["renders"][0]["branch"] == "nothing"
    assert "美股市场日报" in stats["renders"][0]["subject"]


def test_send_via_resend_includes_html_payload() -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"id": "email_123"}

    class FakeClient:
        def __init__(self) -> None:
            self.payload = None

        async def post(self, url, *, json, headers):
            self.payload = json
            return FakeResponse()

    client = FakeClient()
    result = asyncio.run(
        send_via_resend(
            api_key="key",
            from_email="Sentinel <noreply@example.com>",
            to_email="a@example.com",
            subject="Subject",
            text_body="plain",
            html_body="<p>html</p>",
            dry_run=False,
            client=client,
        )
    )

    assert result == "email_123"
    assert client.payload["text"] == "plain"
    assert client.payload["html"] == "<p>html</p>"


def test_send_via_resend_can_send_html_without_text_payload() -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"id": "email_456"}

    class FakeClient:
        def __init__(self) -> None:
            self.payload = None

        async def post(self, url, *, json, headers):
            self.payload = json
            return FakeResponse()

    client = FakeClient()
    result = asyncio.run(
        send_via_resend(
            api_key="key",
            from_email="Sentinel <noreply@example.com>",
            to_email="a@example.com",
            subject="Subject",
            text_body=None,
            html_body="<p>html</p>",
            dry_run=False,
            client=client,
        )
    )

    assert result == "email_456"
    assert "text" not in client.payload
    assert client.payload["html"] == "<p>html</p>"


# ---------------------------------------------------------------------------
# Scheduler gating
# ---------------------------------------------------------------------------


def test_scheduler_registers_email_daily_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for var in (
        "SCANNER_ENABLED",
        "BOT_ENABLED",
        "MARKETING_ENABLED",
        "MARKETING_DAILY_DRAFT_ENABLED",
        "MARKETING_QUEUE_POLL_ENABLED",
        "MARKETING_DAILY_DIGEST_ENABLED",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("MARKETING_EMAIL_DAILY_ENABLED", "true")
    monkeypatch.setenv("MARKETING_EMAIL_DAILY_HOUR_ET", "7")
    monkeypatch.setenv("MARKETING_EMAIL_DAILY_MINUTE_ET", "0")

    from app.scheduler import build_scheduler

    scheduler = build_scheduler()
    assert scheduler is not None
    job = scheduler.get_job("marketing-email-daily")
    assert job is not None
    fields = {f.name: str(f) for f in job.trigger.fields}
    assert fields["hour"] == "7"
    assert fields["minute"] == "0"
    assert fields["day_of_week"] in ("mon-fri", "0-4")


def test_scheduler_email_daily_disabled_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for var in (
        "SCANNER_ENABLED",
        "BOT_ENABLED",
        "MARKETING_ENABLED",
        "MARKETING_DAILY_DRAFT_ENABLED",
        "MARKETING_QUEUE_POLL_ENABLED",
        "MARKETING_DAILY_DIGEST_ENABLED",
        "MARKETING_EMAIL_DAILY_ENABLED",
    ):
        monkeypatch.delenv(var, raising=False)

    from app.scheduler import build_scheduler

    # With every switch off, build_scheduler short-circuits to None.
    assert build_scheduler() is None
