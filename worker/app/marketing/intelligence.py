"""Market Intelligence Layer · per-ticker daily profile.

A `TickerIntelligenceProfile` is the standardized hand-off between data
sources and the Content Factory. It answers:

  - 今天为什么是这只股票？  → why_now
  - 怎么讲？               → recommended_angles
  - 用什么证据？           → evidence + market_signals / catalysts

Adapters in `data_sources/` produce raw signals; this module composes them.
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from .data_sources.fmp import MarketMover, fetch_market_movers
from .data_sources.sec_api import CatalystSignal, fetch_recent_catalysts
from .data_sources.x_serp import SocialSignal, scan_x_serp_signals
from .data_sources.youtube import YouTubeSignal, search_stock_videos
from .opportunity_scoring import (
    derive_confidence,
    recommend_angles,
    score_competitor_heat,
    score_market_heat,
    score_news_heat,
    score_overall_opportunity,
    score_search_heat,
    score_social_heat,
)

logger = logging.getLogger(__name__)

DEFAULT_SEED_TICKERS: tuple[str, ...] = ("AAPL", "NVDA", "TSLA", "MSFT", "GOOGL", "AMD", "META")


@dataclass(frozen=True)
class TickerIntelligenceProfile:
    ticker: str
    company_name: str | None
    market_heat: int
    social_heat: int
    search_heat: int
    news_heat: int
    competitor_heat: int
    overall_opportunity: int
    why_now: str
    market_signals: tuple[str, ...]
    social_signals: tuple[str, ...]
    catalysts: tuple[str, ...]
    recommended_angles: tuple[str, ...]
    evidence: dict[str, Any]
    confidence: str


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def _format_market_signals(mover: Optional[MarketMover]) -> tuple[str, ...]:
    if mover is None:
        return ()
    parts: list[str] = []
    if mover.change_pct is not None:
        sign = "+" if mover.change_pct >= 0 else ""
        parts.append(f"Intraday {sign}{mover.change_pct:.2f}%")
    if mover.volume is not None:
        parts.append(f"Volume {mover.volume:,}")
    if mover.market_cap is not None:
        parts.append(f"Market cap ${mover.market_cap/1e9:.1f}B")
    return tuple(parts)


def _format_social_signals(signals: list[SocialSignal]) -> tuple[str, ...]:
    return tuple(
        f"[{s.intent}] {s.title[:80]} ({s.source})" for s in signals[:5]
    )


def _format_catalysts(catalysts: list[CatalystSignal]) -> tuple[str, ...]:
    return tuple(f"{c.form} · {c.headline[:80]} ({c.observed_at.date()})" for c in catalysts[:3])


def _build_why_now(
    ticker: str,
    mover: Optional[MarketMover],
    social: list[SocialSignal],
    catalysts: list[CatalystSignal],
) -> str:
    bits: list[str] = []
    if mover is not None and mover.change_pct is not None:
        sign = "+" if mover.change_pct >= 0 else ""
        bits.append(f"intraday move {sign}{mover.change_pct:.2f}%")
    if social:
        intents = {s.intent for s in social}
        if "competitor_alternative" in intents:
            bits.append("competitor-alternative chatter on X")
        elif "high_intent_question" in intents:
            bits.append("high-intent retail questions on X")
        else:
            bits.append(f"{len(social)} social mentions surfaced")
    if catalysts:
        bits.append(f"{catalysts[0].form} filing in last 24h")

    if not bits:
        return f"${ticker} on the watchlist — no fresh catalyst surfaced today."
    return f"${ticker} — " + ", ".join(bits) + "."


def _count_intents(signals: Iterable[SocialSignal]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for s in signals:
        counts[s.intent] = counts.get(s.intent, 0) + 1
    return counts


def synthesize_profile(
    ticker: str,
    *,
    mover: Optional[MarketMover],
    social_signals: list[SocialSignal],
    catalysts: list[CatalystSignal],
    youtube_signals: list[YouTubeSignal],
    sources_used: int,
) -> TickerIntelligenceProfile:
    intent_counts = _count_intents(social_signals)
    high_intent = intent_counts.get("high_intent_question", 0) + intent_counts.get(
        "competitor_alternative", 0
    )
    competitor_mentions = intent_counts.get("competitor_alternative", 0)
    risk_mentions = intent_counts.get("risk_discussion", 0)

    has_recent_filing = any(c.days_since_observed <= 1 for c in catalysts)
    has_earnings_signal = any(
        c.form in {"10-Q", "10-K", "8-K"} for c in catalysts
    )

    market_heat = score_market_heat(
        change_pct=mover.change_pct if mover else None,
        relative_volume=getattr(mover, "relative_volume", None) if mover else None,
        news_count=len(catalysts),
        days_since_filing=catalysts[0].days_since_observed if catalysts else None,
        market_cap=mover.market_cap if mover else None,
    )
    social_heat = score_social_heat(
        len(social_signals),
        high_intent_count=high_intent,
        competitor_mentions=competitor_mentions,
    )
    # Search heat re-uses social signal count as a proxy until a dedicated SERP source lands.
    search_heat = score_search_heat(len(social_signals), ranking_spread=min(sources_used, 3))
    news_heat = score_news_heat(
        len(catalysts), high_priority_count=sum(1 for c in catalysts if c.form == "8-K")
    )
    competitor_heat = score_competitor_heat(competitor_mentions)

    overall = score_overall_opportunity(
        market_heat=market_heat,
        social_heat=social_heat,
        search_heat=search_heat,
        news_heat=news_heat,
        competitor_heat=competitor_heat,
    )

    angles = recommend_angles(
        market_heat=market_heat,
        social_heat=social_heat,
        news_heat=news_heat,
        competitor_heat=competitor_heat,
        has_recent_filing=has_recent_filing,
        has_earnings_signal=has_earnings_signal,
        has_valuation_concern=risk_mentions >= 2,
    )

    confidence = derive_confidence(
        sample_size=len(social_signals) + len(catalysts),
        sources_used=sources_used,
        has_filing_evidence=bool(catalysts),
    )

    return TickerIntelligenceProfile(
        ticker=ticker.upper(),
        company_name=mover.company_name if mover else None,
        market_heat=market_heat,
        social_heat=social_heat,
        search_heat=search_heat,
        news_heat=news_heat,
        competitor_heat=competitor_heat,
        overall_opportunity=overall,
        why_now=_build_why_now(ticker.upper(), mover, social_signals, catalysts),
        market_signals=_format_market_signals(mover),
        social_signals=_format_social_signals(social_signals),
        catalysts=_format_catalysts(catalysts),
        recommended_angles=angles,
        evidence={
            "mover": {
                "change_pct": mover.change_pct if mover else None,
                "volume": mover.volume if mover else None,
                "market_cap": mover.market_cap if mover else None,
                "source_url": mover.source_url if mover else None,
            },
            "social_intent_counts": intent_counts,
            "youtube_signal_count": len(youtube_signals),
            "catalyst_count": len(catalysts),
            "sources_used": sources_used,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
        confidence=confidence,
    )


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


async def build_daily_profiles(
    *,
    seed_tickers: Optional[list[str]] = None,
    limit: int = 5,
    fmp_fetcher=fetch_market_movers,
    serp_fetcher=scan_x_serp_signals,
    sec_fetcher=fetch_recent_catalysts,
    youtube_fetcher=search_stock_videos,
) -> list[TickerIntelligenceProfile]:
    """Build per-ticker intelligence profiles, sorted by overall_opportunity desc.

    Every external fetcher is injectable for tests. Each adapter is responsible
    for its own key check + graceful fallback to empty result — this function
    never raises on missing keys; it just records `sources_used` lower.
    """
    tickers = [t.upper() for t in (seed_tickers or DEFAULT_SEED_TICKERS)]

    try:
        movers = await fmp_fetcher(limit=max(limit * 4, 20))
        mover_by_ticker = {m.ticker.upper(): m for m in movers}
        has_fmp = bool(movers)
    except Exception as exc:
        logger.warning("[intelligence] FMP fetcher failed: %s", exc)
        mover_by_ticker = {}
        has_fmp = False

    try:
        social_signals = await serp_fetcher(tickers)
        has_serp = bool(social_signals)
    except Exception as exc:
        logger.warning("[intelligence] SERP fetcher failed: %s", exc)
        social_signals = []
        has_serp = False
    social_by_ticker: dict[str, list[SocialSignal]] = {t: [] for t in tickers}
    for sig in social_signals:
        if sig.ticker and sig.ticker.upper() in social_by_ticker:
            social_by_ticker[sig.ticker.upper()].append(sig)

    catalysts_by_ticker: dict[str, list[CatalystSignal]] = {}
    youtube_by_ticker: dict[str, list[YouTubeSignal]] = {}
    has_sec = False
    has_yt = False

    sec_tasks = [sec_fetcher(t) for t in tickers]
    yt_task = youtube_fetcher(tickers)

    sec_results = await asyncio.gather(*sec_tasks, return_exceptions=True)
    for ticker, result in zip(tickers, sec_results):
        if isinstance(result, Exception):
            logger.warning("[intelligence] SEC fetch failed for %s: %s", ticker, result)
            catalysts_by_ticker[ticker] = []
            continue
        catalysts_by_ticker[ticker] = result
        if result:
            has_sec = True

    try:
        yt_results = await yt_task
        for sig in yt_results:
            if sig.ticker:
                youtube_by_ticker.setdefault(sig.ticker.upper(), []).append(sig)
        has_yt = bool(yt_results)
    except Exception as exc:
        logger.warning("[intelligence] YouTube fetch failed: %s", exc)

    sources_used = sum([has_fmp, has_serp, has_sec, has_yt])

    profiles: list[TickerIntelligenceProfile] = []
    for ticker in tickers:
        profile = synthesize_profile(
            ticker,
            mover=mover_by_ticker.get(ticker),
            social_signals=social_by_ticker.get(ticker, []),
            catalysts=catalysts_by_ticker.get(ticker, []),
            youtube_signals=youtube_by_ticker.get(ticker, []),
            sources_used=sources_used,
        )
        profiles.append(profile)

    profiles.sort(key=lambda p: (-p.overall_opportunity, p.ticker))
    return profiles[:limit]


# ---------------------------------------------------------------------------
# Bridge to existing Content Factory Opportunity contract
# ---------------------------------------------------------------------------


def profile_to_opportunity(profile: TickerIntelligenceProfile):
    """Adapter: TickerIntelligenceProfile → opportunities.Opportunity.

    Keeps the existing Content Factory contract unchanged. Caller can pass the
    returned Opportunity straight into `create_drafts_for_opportunity`.
    """
    from .opportunities import (
        ACTION_CREATE_CONTENT,
        ACTION_WATCH,
        INTENT_TICKER_BUZZ,
        Opportunity,
    )

    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    action = ACTION_CREATE_CONTENT if profile.overall_opportunity >= 70 else ACTION_WATCH
    return Opportunity(
        opportunity_id=f"OP-INTEL-{today}-{profile.ticker}",
        source="intelligence",
        ticker=profile.ticker,
        intent=INTENT_TICKER_BUZZ,
        raw_text=profile.why_now,
        url=profile.evidence.get("mover", {}).get("source_url"),
        author_id=None,
        opportunity_score=profile.overall_opportunity,
        compliance_risk=0,
        suggested_action=action,
        evidence={
            **profile.evidence,
            "intelligence_profile": {
                "market_heat": profile.market_heat,
                "social_heat": profile.social_heat,
                "search_heat": profile.search_heat,
                "news_heat": profile.news_heat,
                "competitor_heat": profile.competitor_heat,
                "confidence": profile.confidence,
                "recommended_angles": list(profile.recommended_angles),
                "market_signals": list(profile.market_signals),
                "social_signals": list(profile.social_signals),
                "catalysts": list(profile.catalysts),
            },
        },
    )
