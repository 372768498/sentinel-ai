"""Signal Layer · turn raw platform buzz into standardized Opportunity objects.

Week 3 scope: X recent-search adapter only. Adapters for FMP / Reddit / YouTube /
OpenClaw will land later behind the same Opportunity interface.

Scoring (X ticker buzz → opportunity_score, 0-100):

  sample_signal = min(sample_count * 2, 60)        # discussion breadth
  top_signal    = min(top_like_count // 5, 40)     # peak engagement
  score         = sample_signal + top_signal       # capped at 100

This favors tickers that are BOTH broadly discussed AND have at least one
high-engagement tweet — pure spam-bot threads with many low-engagement posts
won't break through.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Iterable, Optional

from .intel import TickerBuzz, measure_ticker_buzz
from .opportunities import (
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
        },
    )


async def scan_x_opportunities(
    tickers: Iterable[str] = DEFAULT_WATCHLIST,
    *,
    max_results_per_ticker: int = 30,
    min_score: int = 70,
    client: Optional[XClient] = None,
) -> list[Opportunity]:
    """Scan X buzz for each ticker, return Opportunities sorted by score desc.

    Graceful fallback: if X_BEARER_TOKEN is missing or X_DRY_RUN=true, returns
    an empty list with a warning log instead of raising.
    """
    if not _bearer_available():
        logger.warning(
            "[signal_layer] X_BEARER_TOKEN missing — returning empty opportunity list"
        )
        return []
    if _dry_run():
        logger.warning("[signal_layer] X_DRY_RUN=true — returning empty opportunity list")
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
