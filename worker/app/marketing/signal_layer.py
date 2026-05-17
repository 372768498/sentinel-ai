"""Signal Layer: turn acquisition signals into standardized Opportunities.

The default scanner is deliberately multi-source. Official X search is useful
when available, but the acquisition flywheel must not stop when X credentials
are missing or throttled. ``scan_growth_opportunities()`` therefore falls back
to X SERP search and FMP quote movement, then returns one ranked Opportunity
per ticker so downstream content IDs stay deterministic.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Iterable, Optional

from .data_sources.fmp import MarketMover, fetch_quotes_for_tickers
from .data_sources.x_serp import SocialSignal, scan_x_serp_signals
from .intel import TickerBuzz, measure_ticker_buzz
from .opportunities import (
    INTENT_COMPETITOR_ALTERNATIVE,
    INTENT_HIGH_INTENT_QUESTION,
    INTENT_MARKET_MOVER,
    INTENT_TICKER_BUZZ,
    Opportunity,
    derive_action,
    rank_opportunities,
)
from .x_client import XClient

logger = logging.getLogger(__name__)

DEFAULT_WATCHLIST: tuple[str, ...] = ("AAPL", "NVDA", "TSLA", "MSFT", "GOOGL")


def _bearer_available() -> bool:
    return bool(os.environ.get("X_BEARER_TOKEN", "").strip())


def _dry_run() -> bool:
    return os.environ.get("X_DRY_RUN", "").strip().lower() in {"1", "true", "yes"}


def compute_x_score(buzz: TickerBuzz) -> tuple[int, int]:
    """Return (opportunity_score, top_like_count) for an X TickerBuzz."""
    sample_signal = min(buzz.sample_count * 2, 60)
    top_like = 0
    if buzz.top_engagement:
        top_like = max(
            (t.get("metrics", {}).get("like_count", 0) or 0) for t in buzz.top_engagement
        )
    top_signal = min(top_like // 5, 40)
    score = max(0, min(100, sample_signal + top_signal))
    return score, top_like


def _make_opportunity_from_buzz(buzz: TickerBuzz) -> Opportunity:
    score, top_like = compute_x_score(buzz)
    top = buzz.top_engagement[0] if buzz.top_engagement else None
    raw_text = top["text"] if top else f"${buzz.ticker} buzz: {buzz.sample_count} samples"
    url = f"https://x.com/i/web/status/{top['id']}" if top else None
    author_id = top["author_id"] if top else None
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    return Opportunity(
        opportunity_id=f"OP-X-{today}-{buzz.ticker.upper()}",
        source="x",
        ticker=buzz.ticker.upper(),
        intent=INTENT_TICKER_BUZZ,
        raw_text=raw_text,
        url=url,
        author_id=author_id,
        opportunity_score=score,
        compliance_risk=0,
        suggested_action=derive_action(score),
        evidence={
            "sample_count": buzz.sample_count,
            "top_like_count": top_like,
            "top_tweet_id": top["id"] if top else None,
            "why_now": raw_text[:160],
            "risk_flags": ["Social attention cluster", "Narrative crowding", "Source quality varies"],
        },
        state=_state_from_score(score),
    )


def _state_from_score(score: int) -> str:
    if score >= 88:
        return "heated"
    if score >= 70:
        return "watching"
    return "calm"


def _social_intent(intent: str) -> str:
    if intent == "competitor_alternative":
        return INTENT_COMPETITOR_ALTERNATIVE
    if intent == "high_intent_question":
        return INTENT_HIGH_INTENT_QUESTION
    return INTENT_TICKER_BUZZ


def _risk_flags_from_social(signal: SocialSignal) -> list[str]:
    if signal.intent == "risk_discussion":
        return ["Risk discussion is active", "Narrative may be one-sided", "Source freshness needs review"]
    if signal.intent == "high_intent_question":
        return ["Question-led demand", "Context gap in public discussion", "Answer quality varies by source"]
    return ["Social attention cluster", "Narrative crowding", "Source quality varies"]


def _make_opportunity_from_social_signal(signal: SocialSignal) -> Opportunity | None:
    if not signal.ticker:
        return None
    base_score = {
        "high_intent_question": 86,
        "risk_discussion": 82,
        "competitor_alternative": 78,
        "ticker_buzz": 74,
    }.get(signal.intent, 72)
    engagement = min((signal.estimated_engagement or 0) // 10, 10)
    score = max(0, min(100, base_score + engagement))
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    raw_text = " ".join(part for part in (signal.title, signal.snippet) if part).strip()
    return Opportunity(
        opportunity_id=f"OP-{signal.source.upper()}-{today}-{signal.ticker.upper()}",
        source=signal.source,
        ticker=signal.ticker.upper(),
        intent=_social_intent(signal.intent),
        raw_text=raw_text or f"${signal.ticker.upper()} social signal",
        url=signal.url,
        author_id=None,
        opportunity_score=score,
        compliance_risk=10 if signal.intent == "risk_discussion" else 0,
        suggested_action=derive_action(score),
        evidence={
            "query": signal.query,
            "title": signal.title,
            "snippet": signal.snippet,
            "source": signal.source,
            "why_now": raw_text[:160] if raw_text else "Social search found fresh ticker discussion.",
            "risk_flags": _risk_flags_from_social(signal),
        },
        state=_state_from_score(score),
    )


def _make_opportunity_from_mover(mover: MarketMover) -> Opportunity:
    change = abs(mover.change_pct or 0.0)
    volume_signal = 8 if (mover.volume or 0) >= 10_000_000 else 0
    cap_signal = 7 if (mover.market_cap or 0) >= 50_000_000_000 else 0
    score = max(0, min(100, int(55 + change * 5 + volume_signal + cap_signal)))
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    direction = "up" if (mover.change_pct or 0.0) >= 0 else "down"
    company = f" ({mover.company_name})" if mover.company_name else ""
    raw_text = (
        f"${mover.ticker}{company} is {direction} {mover.change_pct or 0:.2f}% "
        f"with volume {mover.volume or 0:,}."
    )
    return Opportunity(
        opportunity_id=f"OP-FMP-{today}-{mover.ticker.upper()}",
        source="fmp",
        ticker=mover.ticker.upper(),
        intent=INTENT_MARKET_MOVER,
        raw_text=raw_text,
        url=mover.source_url,
        author_id=None,
        opportunity_score=score,
        compliance_risk=0,
        suggested_action=derive_action(score),
        evidence={
            "price": mover.price,
            "change_pct": mover.change_pct,
            "volume": mover.volume,
            "market_cap": mover.market_cap,
            "company_name": mover.company_name,
            "why_now": raw_text,
            "risk_flags": [
                "Price move magnitude",
                "Volume attention",
                "Headline may lag market move",
            ],
        },
        state=_state_from_score(score),
    )


def _dedupe_by_ticker(items: list[Opportunity]) -> list[Opportunity]:
    out: list[Opportunity] = []
    seen: set[str] = set()
    for item in rank_opportunities(items):
        ticker = item.ticker.upper()
        if ticker in seen:
            continue
        seen.add(ticker)
        out.append(item)
    return out


async def scan_x_opportunities(
    tickers: Iterable[str] = DEFAULT_WATCHLIST,
    *,
    max_results_per_ticker: int = 30,
    min_score: int = 70,
    client: Optional[XClient] = None,
) -> list[Opportunity]:
    """Scan official X buzz for each ticker, returning ranked Opportunities."""
    if not _bearer_available():
        logger.warning("[signal_layer] X_BEARER_TOKEN missing; returning empty X opportunity list")
        return []
    if _dry_run():
        logger.warning("[signal_layer] X_DRY_RUN=true; returning empty X opportunity list")
        return []

    fb = client or XClient()
    out: list[Opportunity] = []
    for ticker in tickers:
        try:
            buzz = await measure_ticker_buzz(ticker, client=fb, max_results=max_results_per_ticker)
        except Exception as exc:
            logger.warning("[signal_layer] measure_ticker_buzz failed for %s: %s", ticker, exc)
            continue
        opp = _make_opportunity_from_buzz(buzz)
        if opp.opportunity_score >= min_score:
            out.append(opp)
        else:
            logger.debug(
                "[signal_layer] %s below min_score (%d < %d)",
                ticker,
                opp.opportunity_score,
                min_score,
            )
    return rank_opportunities(out)


async def scan_growth_opportunities(
    tickers: Iterable[str] = DEFAULT_WATCHLIST,
    *,
    max_results_per_ticker: int = 30,
    min_score: int = 70,
    client: Optional[XClient] = None,
) -> list[Opportunity]:
    """Scan all currently available acquisition sources.

    Source order:
      1. Official X recent search, when ``X_BEARER_TOKEN`` is present.
      2. X SERP fallback via DataForSEO or Tavily.
      3. FMP quote movement for the watchlist.

    The return value is one Opportunity per ticker, ranked by internal score.
    """
    cleaned = tuple(t.strip().upper() for t in tickers if t and t.strip())
    if not cleaned:
        return []

    out: list[Opportunity] = []
    out.extend(
        await scan_x_opportunities(
            cleaned,
            max_results_per_ticker=max_results_per_ticker,
            min_score=min_score,
            client=client,
        )
    )

    try:
        social_signals = await scan_x_serp_signals(list(cleaned))
    except Exception as exc:
        logger.warning("[signal_layer] scan_x_serp_signals failed: %s", exc)
        social_signals = []
    for signal in social_signals:
        opp = _make_opportunity_from_social_signal(signal)
        if opp is not None and opp.opportunity_score >= min_score:
            out.append(opp)

    try:
        movers = await fetch_quotes_for_tickers(cleaned)
    except Exception as exc:
        logger.warning("[signal_layer] fetch_quotes_for_tickers failed: %s", exc)
        movers = []
    for mover in movers:
        opp = _make_opportunity_from_mover(mover)
        if opp.opportunity_score >= min_score:
            out.append(opp)

    return _dedupe_by_ticker(out)
