"""Tests for content_factory."""

from __future__ import annotations

import pytest

from app.marketing.content_factory import (
    GROWTH_PACK_PLATFORMS,
    PLATFORMS,
    PLATFORM_REDDIT,
    PLATFORM_SHORTS,
    PLATFORM_TELEGRAM,
    PLATFORM_TIKTOK,
    PLATFORM_X,
    ContentFactoryError,
    MultiPlatformComposer,
    build_cta_url,
    campaign_id_for,
    content_id_for,
    create_drafts_for_opportunity,
    create_growth_pack_for_opportunity,
)
from app.marketing.opportunities import (
    ACTION_CREATE_CONTENT,
    INTENT_TICKER_BUZZ,
    Opportunity,
)


def _opp(score: int = 85, ticker: str = "NVDA") -> Opportunity:
    return Opportunity(
        opportunity_id=f"OP-X-20260511-{ticker}",
        source="x",
        ticker=ticker,
        intent=INTENT_TICKER_BUZZ,
        raw_text=f"${ticker} discussion sample",
        url="https://x.com/i/web/status/123",
        author_id="u1",
        opportunity_score=score,
        compliance_risk=0,
        suggested_action=ACTION_CREATE_CONTENT,
        evidence={"sample_count": 30, "top_like_count": 200, "top_tweet_id": "123"},
    )


class FakeComposer:
    """Returns a clean redline-passing body for each platform."""

    def __init__(self, clean: bool = True, fail_platform: str | None = None) -> None:
        self.clean = clean
        self.fail_platform = fail_platform
        self.calls: list[tuple[str, str]] = []

    def compose(self, *, opportunity, platform: str, cta_url: str) -> str:
        self.calls.append((opportunity.ticker, platform))
        if self.fail_platform and platform == self.fail_platform:
            raise RuntimeError("composer fail injected")
        if not self.clean:
            return f"${opportunity.ticker} buy now and price target {cta_url}"
        return (
            f"${opportunity.ticker} Sentinel AI score "
            f"{opportunity.opportunity_score}/100.\n"
            f"Main risk flag: regulatory review pending.\n"
            f"Full breakdown: {cta_url}\n\n"
            f"Context, not financial advice."
        )


def test_content_id_for_format() -> None:
    op = _opp(ticker="aapl")
    assert content_id_for(op, PLATFORM_X, date="20260511") == "CT-20260511-AAPL-x"
    assert content_id_for(op, PLATFORM_REDDIT, date="20260511") == "CT-20260511-AAPL-rd"
    assert content_id_for(op, PLATFORM_TELEGRAM, date="20260511") == "CT-20260511-AAPL-tg"
    assert content_id_for(op, PLATFORM_SHORTS, date="20260511") == "CT-20260511-AAPL-yt"
    assert content_id_for(op, PLATFORM_TIKTOK, date="20260511") == "CT-20260511-AAPL-tt"


def test_campaign_id_for_format() -> None:
    assert campaign_id_for(date="20260511") == "CMP-20260511-daily"


def test_build_cta_url_has_correct_utm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROWTH_OS_PUBLIC_URL", "https://sentinel.example.com")
    op = _opp(ticker="NVDA")
    url = build_cta_url(op, PLATFORM_X, "CMP-20260511-daily", "CT-20260511-NVDA-x")
    assert url == (
        "https://sentinel.example.com/stocks/NVDA"
        "?utm_source=x&utm_medium=thread"
        "&utm_campaign=CMP-20260511-daily&utm_content=CT-20260511-NVDA-x"
    )

    url_tg = build_cta_url(op, PLATFORM_TELEGRAM, "CMP-X", "CT-X")
    assert "utm_source=telegram" in url_tg and "utm_medium=broadcast" in url_tg

    url_yt = build_cta_url(op, PLATFORM_SHORTS, "CMP-X", "CT-X")
    assert "utm_source=youtube" in url_yt and "utm_medium=shorts" in url_yt

    url_rd = build_cta_url(op, PLATFORM_REDDIT, "CMP-X", "CT-X")
    assert "utm_source=reddit" in url_rd and "utm_medium=discussion" in url_rd

    url_tt = build_cta_url(op, PLATFORM_TIKTOK, "CMP-X", "CT-X")
    assert "utm_source=tiktok" in url_tt and "utm_medium=shorts" in url_tt


def test_create_drafts_for_opportunity_generates_three_platforms(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROWTH_OS_PUBLIC_URL", "https://sentinel.example.com")
    fake = FakeComposer(clean=True)
    bundle = create_drafts_for_opportunity(_opp(), composer=fake, date="20260511")
    assert len(bundle.drafts) == 3
    platforms = {d.platform for d in bundle.drafts}
    assert platforms == set(PLATFORMS)

    by_platform = {d.platform: d for d in bundle.drafts}
    assert by_platform[PLATFORM_X].content_id == "CT-20260511-NVDA-x"
    assert by_platform[PLATFORM_TELEGRAM].content_id == "CT-20260511-NVDA-tg"
    assert by_platform[PLATFORM_SHORTS].content_id == "CT-20260511-NVDA-yt"

    for draft in bundle.drafts:
        assert draft.source_opportunity_id == "OP-X-20260511-NVDA"
        assert draft.campaign_id == "CMP-20260511-daily"
        assert draft.ticker == "NVDA"
        assert draft.cta_url.startswith("https://sentinel.example.com/stocks/NVDA")
        assert "utm_campaign=CMP-20260511-daily" in draft.cta_url
        assert f"utm_content={draft.content_id}" in draft.cta_url
        assert bundle.redlines[draft.content_id].ok


def test_create_growth_pack_for_opportunity_generates_agreed_channels(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROWTH_OS_PUBLIC_URL", "https://sentinel.example.com")
    fake = FakeComposer(clean=True)
    bundle = create_growth_pack_for_opportunity(_opp(), composer=fake, date="20260511")
    assert len(bundle.drafts) == 4
    platforms = {d.platform for d in bundle.drafts}
    assert platforms == set(GROWTH_PACK_PLATFORMS)

    by_platform = {d.platform: d for d in bundle.drafts}
    assert by_platform[PLATFORM_X].content_id == "CT-20260511-NVDA-x"
    assert by_platform[PLATFORM_REDDIT].content_id == "CT-20260511-NVDA-rd"
    assert by_platform[PLATFORM_SHORTS].content_id == "CT-20260511-NVDA-yt"
    assert by_platform[PLATFORM_TIKTOK].content_id == "CT-20260511-NVDA-tt"


def test_create_growth_pack_cleans_proxy_encoding_artifacts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROWTH_OS_PUBLIC_URL", "https://sentinel.example.com")

    class DirtyComposer:
        def compose(self, *, opportunity, platform: str, cta_url: str) -> str:
            return (
                f"${opportunity.ticker} is heated \u0431\u043a risk flag is crowded attention. "
                f"Full context: {cta_url}\n\nContext, not financial advice."
            )

    bundle = create_growth_pack_for_opportunity(_opp(), composer=DirtyComposer(), date="20260511")
    assert all("\u0431\u043a" not in draft.body for draft in bundle.drafts)
    assert all(" - " in draft.body for draft in bundle.drafts)


def test_create_growth_pack_does_not_overpromise_cta_destination(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROWTH_OS_PUBLIC_URL", "https://sentinel.example.com")

    class OverpromisingComposer:
        def compose(self, *, opportunity, platform: str, cta_url: str) -> str:
            return (
                f"Full anomaly breakdown: {cta_url}\n\n"
                "Unlock the full anomaly report after preview.\n\n"
                "Risk flag: attention is crowded.\n\n"
                "Context, not financial advice."
            )

    bundle = create_growth_pack_for_opportunity(_opp(), composer=OverpromisingComposer(), date="20260511")
    assert all("Full anomaly breakdown" not in draft.body for draft in bundle.drafts)
    assert all("Stock context preview" in draft.body for draft in bundle.drafts)
    assert all("full anomaly report" not in draft.body.lower() for draft in bundle.drafts)


def test_user_prompt_sets_honest_stock_page_expectation() -> None:
    from app.marketing.content_factory import _format_user_prompt

    prompt = _format_user_prompt(_opp(), PLATFORM_X, "https://app.jilo.ai/stocks/NVDA")
    assert "stock-context preview" in prompt
    assert "Do NOT claim" in prompt
    assert "full breakdown directly" in prompt


def test_create_drafts_redline_blocked_keeps_draft_but_flags_high_risk(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROWTH_OS_PUBLIC_URL", "https://sentinel.example.com")
    fake = FakeComposer(clean=False)
    bundle = create_drafts_for_opportunity(_opp(), composer=fake, date="20260511")
    assert len(bundle.drafts) == 3  # still returned, NOT silently dropped
    for draft in bundle.drafts:
        assert draft.risk_level == "High"
        assert not bundle.redlines[draft.content_id].ok
        violations = bundle.redlines[draft.content_id].violations
        assert "forbidden:buy" in violations
        assert "forbidden:price target" in violations


def test_create_drafts_skips_platform_when_composer_throws(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROWTH_OS_PUBLIC_URL", "https://sentinel.example.com")
    fake = FakeComposer(clean=True, fail_platform=PLATFORM_SHORTS)
    bundle = create_drafts_for_opportunity(_opp(), composer=fake)
    platforms = {d.platform for d in bundle.drafts}
    assert PLATFORM_X in platforms
    assert PLATFORM_TELEGRAM in platforms
    assert PLATFORM_SHORTS not in platforms


def test_composer_raises_when_no_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(ContentFactoryError, match="ANTHROPIC_API_KEY missing"):
        MultiPlatformComposer()


def test_composer_accepts_injected_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    # Should NOT raise — injected client bypasses env requirement
    cmp = MultiPlatformComposer(client=object())
    assert cmp.client is not None
