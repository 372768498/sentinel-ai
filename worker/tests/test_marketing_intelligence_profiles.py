"""Tests for intelligence.synthesize_profile + build_daily_profiles +
profile_to_opportunity bridge."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from app.marketing.data_sources.fmp import MarketMover
from app.marketing.data_sources.sec_api import CatalystSignal
from app.marketing.data_sources.x_serp import (
    INTENT_COMPETITOR_ALTERNATIVE,
    INTENT_HIGH_INTENT_QUESTION,
    INTENT_TICKER_BUZZ,
    SocialSignal,
)
from app.marketing.data_sources.youtube import YouTubeSignal
from app.marketing.intelligence import (
    TickerIntelligenceProfile,
    build_daily_profiles,
    profile_to_opportunity,
    synthesize_profile,
)
from app.marketing.opportunities import (
    ACTION_CREATE_CONTENT,
    ACTION_WATCH,
    Opportunity,
)


def _run(coro):
    return asyncio.run(coro)


def _mover(
    ticker: str,
    pct: float,
    vol: int = 50_000_000,
    cap: int = 10_000_000_000,
    rel_vol: float | None = None,
) -> MarketMover:
    return MarketMover(
        ticker=ticker,
        price=100.0,
        change_pct=pct,
        volume=vol,
        market_cap=cap,
        company_name=f"{ticker} Corp",
        source_url="https://example/fmp",
        relative_volume=rel_vol,
    )


def _social(ticker: str, intent: str = INTENT_TICKER_BUZZ) -> SocialSignal:
    return SocialSignal(
        source="dataforseo",
        query=f'site:x.com "${ticker}"',
        ticker=ticker,
        title=f"${ticker} sample tweet",
        url=f"https://x.com/u/{ticker}",
        snippet="sample snippet",
        observed_at=datetime.now(timezone.utc),
        estimated_engagement=None,
        intent=intent,
    )


def _catalyst(ticker: str, form: str = "8-K", days: int = 1) -> CatalystSignal:
    return CatalystSignal(
        ticker=ticker,
        form=form,
        headline=f"{ticker} filed a {form}",
        url=f"https://sec.gov/{ticker}",
        observed_at=datetime.now(timezone.utc),
        days_since_observed=days,
        source="edgar_fallback",
    )


# ---- synthesize_profile --------------------------------------------------


def test_synthesize_profile_strong_signal_high_overall() -> None:
    profile = synthesize_profile(
        "NVDA",
        mover=_mover("NVDA", pct=5.2, rel_vol=3.0),
        social_signals=[_social("NVDA", INTENT_HIGH_INTENT_QUESTION) for _ in range(8)],
        catalysts=[
            _catalyst("NVDA", "8-K", days=0),
            _catalyst("NVDA", "10-Q", days=2),
            _catalyst("NVDA", "8-K", days=3),
        ],
        youtube_signals=[],
        sources_used=3,
    )
    assert isinstance(profile, TickerIntelligenceProfile)
    assert profile.ticker == "NVDA"
    assert profile.overall_opportunity >= 55  # strong mix without competitor heat
    assert profile.market_heat >= 60
    assert profile.social_heat >= 30
    assert "intraday" in profile.why_now.lower()
    assert len(profile.recommended_angles) >= 1


def test_synthesize_profile_quiet_day_low_overall() -> None:
    profile = synthesize_profile(
        "MSFT",
        mover=_mover("MSFT", pct=0.1, vol=10_000_000),
        social_signals=[],
        catalysts=[],
        youtube_signals=[],
        sources_used=1,
    )
    assert profile.overall_opportunity < 50
    assert profile.confidence == "low"
    # why_now should not be empty
    assert profile.why_now


def test_synthesize_profile_competitor_signals_drive_competitor_heat() -> None:
    profile = synthesize_profile(
        "TSLA",
        mover=_mover("TSLA", pct=2.0),
        social_signals=[_social("TSLA", INTENT_COMPETITOR_ALTERNATIVE) for _ in range(4)],
        catalysts=[],
        youtube_signals=[],
        sources_used=2,
    )
    assert profile.competitor_heat > 0
    assert any("competitor" in a for a in profile.recommended_angles) or profile.competitor_heat >= 50


# ---- build_daily_profiles ------------------------------------------------


def test_build_daily_profiles_orchestrates_all_fetchers() -> None:
    async def fake_fmp(limit: int):
        return [_mover("NVDA", 4.0), _mover("AAPL", -2.0)]

    async def fake_serp(tickers):
        return [_social("NVDA", INTENT_TICKER_BUZZ) for _ in range(3)] + [_social("AAPL")]

    async def fake_sec(ticker):
        return [_catalyst(ticker, "8-K", days=0)] if ticker == "NVDA" else []

    async def fake_youtube(tickers):
        return [
            YouTubeSignal(
                video_id="abc",
                title="NVDA analysis",
                channel_title="someone",
                published_at=None,
                view_count=1000,
                like_count=50,
                comment_count=5,
                ticker="NVDA",
                url="https://youtube.com/watch?v=abc",
            )
        ]

    profiles = _run(
        build_daily_profiles(
            seed_tickers=["NVDA", "AAPL"],
            limit=5,
            fmp_fetcher=fake_fmp,
            serp_fetcher=fake_serp,
            sec_fetcher=fake_sec,
            youtube_fetcher=fake_youtube,
        )
    )
    assert len(profiles) == 2
    # Sorted desc by overall_opportunity, NVDA should lead (has filing + more signals)
    assert profiles[0].ticker == "NVDA"
    assert profiles[0].overall_opportunity >= profiles[1].overall_opportunity
    assert profiles[0].evidence["sources_used"] == 4  # all four fakes returned data


def test_build_daily_profiles_graceful_when_all_sources_empty() -> None:
    async def empty_fmp(limit: int):
        return []

    async def empty_serp(tickers):
        return []

    async def empty_sec(ticker):
        return []

    async def empty_yt(tickers):
        return []

    profiles = _run(
        build_daily_profiles(
            seed_tickers=["NVDA"],
            fmp_fetcher=empty_fmp,
            serp_fetcher=empty_serp,
            sec_fetcher=empty_sec,
            youtube_fetcher=empty_yt,
        )
    )
    assert len(profiles) == 1
    p = profiles[0]
    assert p.ticker == "NVDA"
    assert p.overall_opportunity == 0 or p.overall_opportunity < 50
    assert p.confidence == "low"
    assert p.evidence["sources_used"] == 0


def test_build_daily_profiles_continues_when_one_fetcher_raises() -> None:
    async def boom_fmp(limit: int):
        raise RuntimeError("fmp down")

    async def ok_serp(tickers):
        return [_social("NVDA")]

    async def ok_sec(ticker):
        return []

    async def ok_yt(tickers):
        return []

    profiles = _run(
        build_daily_profiles(
            seed_tickers=["NVDA"],
            fmp_fetcher=boom_fmp,
            serp_fetcher=ok_serp,
            sec_fetcher=ok_sec,
            youtube_fetcher=ok_yt,
        )
    )
    assert len(profiles) == 1
    # SERP still contributed
    assert profiles[0].evidence["sources_used"] == 1


def test_build_daily_profiles_respects_limit() -> None:
    async def fake_fmp(limit: int):
        return [_mover(t, 3.0) for t in ("A", "B", "C", "D", "E", "F")]

    async def fake_serp(tickers):
        return []

    async def fake_sec(ticker):
        return []

    async def fake_yt(tickers):
        return []

    profiles = _run(
        build_daily_profiles(
            seed_tickers=["A", "B", "C", "D", "E", "F"],
            limit=3,
            fmp_fetcher=fake_fmp,
            serp_fetcher=fake_serp,
            sec_fetcher=fake_sec,
            youtube_fetcher=fake_yt,
        )
    )
    assert len(profiles) == 3


# ---- profile_to_opportunity bridge --------------------------------------


def test_profile_to_opportunity_preserves_score_and_evidence() -> None:
    profile = synthesize_profile(
        "NVDA",
        mover=_mover("NVDA", 4.0),
        social_signals=[_social("NVDA") for _ in range(5)],
        catalysts=[_catalyst("NVDA")],
        youtube_signals=[],
        sources_used=3,
    )
    opp = profile_to_opportunity(profile)
    assert isinstance(opp, Opportunity)
    assert opp.ticker == "NVDA"
    assert opp.opportunity_score == profile.overall_opportunity
    assert opp.source == "intelligence"
    assert opp.intent == "ticker_buzz"
    assert "intelligence_profile" in opp.evidence
    assert opp.evidence["intelligence_profile"]["market_heat"] == profile.market_heat
    # High-score profile → create_content
    if profile.overall_opportunity >= 70:
        assert opp.suggested_action == ACTION_CREATE_CONTENT


def test_profile_to_opportunity_low_score_maps_to_watch() -> None:
    profile = synthesize_profile(
        "DEAD",
        mover=_mover("DEAD", 0.05, vol=1_000),
        social_signals=[],
        catalysts=[],
        youtube_signals=[],
        sources_used=1,
    )
    opp = profile_to_opportunity(profile)
    assert opp.suggested_action == ACTION_WATCH
