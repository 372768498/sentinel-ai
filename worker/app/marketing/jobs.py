"""APScheduler jobs that drive the marketing pipeline."""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

from ..scanner import fetch_watchlist_moves
from .catalysts import Catalyst, fallback_source, latest_catalyst
from .composer import Composer
from .content_factory import (
    ContentFactoryError,
    GROWTH_PACK_PLATFORMS,
    MultiPlatformComposer,
    create_growth_pack_for_opportunity,
)
from .feishu_client import FeishuAPIError, FeishuClient
from .opportunities import ACTION_CREATE_CONTENT, Opportunity
from .publisher import Publisher
from .review_queue import ReviewQueueError, submit_draft_to_review
from .signal_layer import DEFAULT_WATCHLIST, scan_x_opportunities
from .signals import passes_gate, score_from_move
from .x_client import XClient

logger = logging.getLogger(__name__)

DEFAULT_BOT_USERNAME = "SentinelAIProChannelBot"
DEFAULT_THRESHOLD = 80


_publisher_singleton: Optional[Publisher] = None


def _get_publisher() -> Publisher:
    global _publisher_singleton
    if _publisher_singleton is not None:
        return _publisher_singleton
    bot_username = os.environ.get("BOT_USERNAME", DEFAULT_BOT_USERNAME)
    _publisher_singleton = Publisher(
        composer=Composer(),  # auto Mock if no ANTHROPIC_API_KEY
        x_client=XClient(),  # auto dry_run unless X_DRY_RUN=false
        bot_username=bot_username,
        source_label=os.environ.get("MARKETING_SOURCE_LABEL", "xtw"),
    )
    return _publisher_singleton


def _threshold() -> int:
    raw = os.environ.get("MARKETING_SCORE_THRESHOLD", str(DEFAULT_THRESHOLD))
    try:
        return int(raw)
    except ValueError:
        logger.warning("invalid MARKETING_SCORE_THRESHOLD=%r, using %d", raw, DEFAULT_THRESHOLD)
        return DEFAULT_THRESHOLD


async def publish_marketing_alerts(session_label: str) -> dict:
    """Scan watchlist, filter by score threshold, dispatch each via X.

    Safe to call any time: composer + x_client default to dry-run.
    Designed to run ~3 min after each scanner session so prices have settled.
    """
    moves = await fetch_watchlist_moves()
    threshold = _threshold()
    qualified = []
    for move in moves:
        score = score_from_move(move)
        if passes_gate(score, threshold=threshold):
            qualified.append((move, score))

    logger.info(
        "marketing[%s] scanned=%d qualified=%d threshold=%d",
        session_label, len(moves), len(qualified), threshold,
    )

    if not qualified:
        return {
            "session": session_label,
            "scanned": len(moves),
            "qualified": 0,
            "outcomes": [],
        }

    publisher = _get_publisher()

    # Parallel SEC catalyst lookup so the chain isn't serialized on EDGAR latency.
    catalyst_tasks = [latest_catalyst(move.ticker) for move, _ in qualified]
    catalysts: list[Optional[Catalyst]] = await asyncio.gather(*catalyst_tasks)

    outcomes = []
    for (move, score), catalyst in zip(qualified, catalysts):
        sign = "+" if move.change_pct > 0 else ""
        if catalyst is not None:
            headline = (
                f"{catalyst.headline()}; intraday move {sign}{move.change_pct:.2f}%"
            )
            source_url = catalyst.homepage_url
        else:
            headline = f"intraday move of {sign}{move.change_pct:.2f}% on watchlist"
            source_url = fallback_source(move.ticker)

        try:
            outcome = await publisher.publish_alert(
                ticker=move.ticker,
                change_pct=move.change_pct,
                score=score,
                headline=headline,
                source_url=source_url,
            )
            outcomes.append({
                "ticker": move.ticker,
                "score": score,
                "persona": outcome.persona,
                "redline_ok": outcome.redline_ok,
                "posted": outcome.post_result.posted,
                "tweet_id": outcome.post_result.tweet_id,
                "dry_run": outcome.post_result.dry_run,
                "catalyst": catalyst.form if catalyst else None,
            })
        except Exception as exc:
            logger.exception("marketing publish failed for %s", move.ticker)
            outcomes.append({"ticker": move.ticker, "error": str(exc)})

    return {
        "session": session_label,
        "scanned": len(moves),
        "qualified": len(qualified),
        "outcomes": outcomes,
    }


# ---------------------------------------------------------------------------
# Daily review-draft generation (Week 3 · Signal + Content Factory)
# ---------------------------------------------------------------------------


def _top_opportunities_count() -> int:
    raw = os.environ.get("MARKETING_TOP_OPPORTUNITIES_PER_DAY", "5")
    try:
        return max(0, int(raw))
    except ValueError:
        logger.warning("invalid MARKETING_TOP_OPPORTUNITIES_PER_DAY=%r, using 5", raw)
        return 5


def _min_opportunity_score() -> int:
    raw = os.environ.get("MARKETING_MIN_OPPORTUNITY_SCORE", "70")
    try:
        return max(0, min(100, int(raw)))
    except ValueError:
        return 70


async def generate_daily_review_drafts(
    session_label: str = "daily_0900_et",
    *,
    tickers=DEFAULT_WATCHLIST,
    scanner=scan_x_opportunities,
    composer: Optional[MultiPlatformComposer] = None,
    feishu_client: Optional[FeishuClient] = None,
    submit_fn=submit_draft_to_review,
    content_date: Optional[str] = None,
    campaign_id: Optional[str] = None,
) -> dict:
    """Scan opportunities → generate 3 drafts each → submit to Feishu Review Hub.

    Designed to run once per trading day, 09:00 America/New_York (pre-market).
    All side-effect collaborators (`scanner`, `composer`, `feishu_client`,
    `submit_fn`) are injectable so tests can fake them end-to-end.

    Returns a stats dict:
        {
            "session": ...,
            "opportunities": int,
            "drafts_created": int,
            "submitted_to_review": int,
            "skipped": int,
            "errors": [...],
        }
    """
    min_score = _min_opportunity_score()
    top_n = _top_opportunities_count()

    try:
        opportunities = await scanner(tickers, min_score=min_score)
    except Exception as exc:
        logger.exception("[daily_drafts] scanner failed")
        return {
            "session": session_label,
            "opportunities": 0,
            "drafts_created": 0,
            "submitted_to_review": 0,
            "skipped": 0,
            "errors": [f"scanner: {exc}"],
        }

    eligible = [o for o in opportunities if o.suggested_action == ACTION_CREATE_CONTENT]
    top = eligible[:top_n]

    logger.info(
        "[daily_drafts] %s scanned=%d eligible=%d top_n=%d",
        session_label,
        len(opportunities),
        len(eligible),
        len(top),
    )

    if not top:
        return {
            "session": session_label,
            "opportunities": len(opportunities),
            "drafts_created": 0,
            "submitted_to_review": 0,
            "skipped": 0,
            "errors": [],
        }

    # Build composer once. If ANTHROPIC_API_KEY missing, refuse the entire run
    # rather than silently emit mock content.
    try:
        cmp = composer or MultiPlatformComposer()
    except ContentFactoryError as exc:
        logger.error("[daily_drafts] %s", exc)
        return {
            "session": session_label,
            "opportunities": len(opportunities),
            "drafts_created": 0,
            "submitted_to_review": 0,
            "skipped": len(top) * len(GROWTH_PACK_PLATFORMS),
            "errors": [str(exc)],
        }

    drafts_created = 0
    submitted = 0
    skipped = 0
    errors: list[str] = []

    for opp in top:
        bundle = create_growth_pack_for_opportunity(
            opp,
            composer=cmp,
            date=content_date,
            campaign_id=campaign_id,
        )
        drafts_created += len(bundle.drafts)
        for draft in bundle.drafts:
            try:
                await submit_fn(draft, client=feishu_client)
                submitted += 1
            except (ReviewQueueError, FeishuAPIError) as exc:
                logger.warning(
                    "[daily_drafts] submit_to_review failed for %s: %s",
                    draft.content_id,
                    exc,
                )
                errors.append(f"{draft.content_id}: {exc}")
                skipped += 1

    return {
        "session": session_label,
        "opportunities": len(opportunities),
        "drafts_created": drafts_created,
        "submitted_to_review": submitted,
        "skipped": skipped,
        "errors": errors,
    }


async def generate_always_on_review_drafts(
    session_label: str = "always_on",
    **kwargs,
) -> dict:
    """Generate review drafts for recurring 24h acquisition scans.

    The daily job uses one `CT-YYYYMMDD-TICKER-platform` id per day. A recurring
    job needs hour-level ids so a second scan can create fresh rows instead of
    overwriting the morning Bitable records.
    """
    from datetime import datetime, timezone

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M")
    return await generate_daily_review_drafts(
        session_label=session_label,
        content_date=stamp,
        campaign_id=f"CMP-{stamp}-always-on",
        **kwargs,
    )
