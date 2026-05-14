"""
Scheduled digest functions called by APScheduler.
- public_premarket_brief(): 8:30 AM ET → @SentinelAI_signals
- public_midday_brief():    12:30 PM ET → @SentinelAI_signals
- public_eod_digest():      4:30 PM ET → @SentinelAI_signals
- personal_eod_digests():   4:35 PM ET → each VIP user's DM

Each public job carries a process-local idempotency guard keyed on
{job_id}:{ET-date}. Combined with Railway pinning the worker to a single
replica, this is double-safety against the duplicate-push bug that surfaced
on 5/12-5/14 (two replicas each fired the cron once).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date

from ..scanner import TickerMove, fetch_watchlist_moves
from ..scoring import (
    Narrative,
    ScoreRow,
    ScoreSnapshot,
    generate_narrative,
    get_latest_scores,
    get_score_delta,
    score_watchlist,
    store_score,
)
from ..scoring.highlights import (
    component_highlight,
    component_label,
    extract_peer_tickers,
    rank_components,
)
from ..telegram import send_channel_message
from ..watchlist import DEFAULT_WATCHLIST, MOVE_THRESHOLD_PCT
from . import db
from .market_calendar import is_trading_day, today_et
from .templates.telegram_messages import (
    alert_eod_digest,
    alert_silence_day,
    pro_daily_brief_card,
    pro_daily_brief_quiet,
    public_midday_brief_active,
    public_midday_brief_quiet,
    public_postclose_digest,
    public_premarket_brief_active,
    public_premarket_brief_quiet,
)

logger = logging.getLogger(__name__)

# Process-local idempotency set: {f"{job_id}:{YYYY-MM-DD ET}"}.
# Cleared on restart, which is fine — the goal is to dedupe within a single
# trading day. Cross-replica dedupe requires Railway to pin to 1 worker.
_SENT_TODAY: set[str] = set()


def _idem_key(job_id: str) -> str:
    return f"{job_id}:{today_et().isoformat()}"


def _claim(job_id: str) -> bool:
    """Return True if this fire-of-the-day has not been claimed yet."""
    key = _idem_key(job_id)
    if key in _SENT_TODAY:
        logger.warning("idempotency: skipping duplicate fire of %s", key)
        return False
    _SENT_TODAY.add(key)
    return True


async def _fetch_score_overlay(tickers: list[str]) -> dict[str, dict]:
    """
    Best-effort enrichment of mover dicts with Sentinel score / rating /
    score_change. Returns {ticker: {score_100, rating, score_change}}.

    Returns {} when:
      - DATABASE_URL is unset (dev mode)
      - daily_scores table is empty (cold start before first post-close run)
      - any DB error fires (logged, swallowed — score is a nice-to-have,
        not a hard dependency of the radar push)
    """
    try:
        pool = await db.get_pool()
    except Exception as exc:
        logger.info("score overlay skipped — DB unavailable: %s", exc)
        return {}

    try:
        latest = await get_latest_scores(pool, tickers)
    except Exception as exc:
        logger.warning("score overlay failed reading latest_scores: %s", exc)
        return {}

    if not latest:
        return {}

    overlay: dict[str, dict] = {}
    for ticker in tickers:
        row = latest.get(ticker.upper())
        if row is None:
            continue
        # Score-change arrow: compare row.score_100 (most recent) to the
        # row before it. None if we only have a single day of history.
        delta: int | None = None
        try:
            _, prior = await get_score_delta(pool, ticker)
            if prior is not None:
                delta = row.score_100 - prior.score_100
        except Exception as exc:
            logger.debug("score delta lookup failed for %s: %s", ticker, exc)
        overlay[ticker.upper()] = {
            "score_100": row.score_100,
            "rating": row.rating,
            "score_change": delta,
            "why_moving": row.why_moving,
            "risk_flag": row.risk_flag,
        }
    return overlay


def _mover_dict(m: TickerMove, score_overlay: dict | None = None) -> dict:
    base = {
        "ticker": m.ticker,
        "change_pct": m.change_pct,
        "price": m.last_price,
        "prev_close": m.prev_close,
        "volume": m.volume,
        "relative_volume": m.relative_volume,
    }
    if score_overlay:
        base.update(score_overlay)
    return base


async def _build_mover_items(
    moves: list[TickerMove], limit: int | None = None,
) -> list[dict]:
    """Sort by abs(change_pct), enrich with score overlay, optionally clamp."""
    sorted_moves = sorted(moves, key=lambda m: abs(m.change_pct), reverse=True)
    if limit is not None:
        sorted_moves = sorted_moves[:limit]
    overlay = await _fetch_score_overlay([m.ticker for m in sorted_moves])
    return [_mover_dict(m, overlay.get(m.ticker.upper())) for m in sorted_moves]


async def public_premarket_brief() -> None:
    if not is_trading_day(today_et()):
        logger.info("pre-market brief skipped — not a trading day")
        return
    if not _claim("brief-premarket-public"):
        return

    date_str = today_et().strftime("%a %b %d")
    moves = await fetch_watchlist_moves(DEFAULT_WATCHLIST)
    notable = [m for m in moves if abs(m.change_pct) >= MOVE_THRESHOLD_PCT]

    if notable:
        items = await _build_mover_items(notable, limit=3)
        text = public_premarket_brief_active(date_str, items)
    else:
        text = public_premarket_brief_quiet(date_str)

    await send_channel_message(text)
    logger.info("public pre-market brief sent (%d notable)", len(notable))


async def public_midday_brief() -> None:
    """12:30 ET intraday anomaly radar — same shape as pre-market."""
    if not is_trading_day(today_et()):
        logger.info("mid-day brief skipped — not a trading day")
        return
    if not _claim("brief-midday-public"):
        return

    date_str = today_et().strftime("%a %b %d")
    moves = await fetch_watchlist_moves(DEFAULT_WATCHLIST)
    notable = [m for m in moves if abs(m.change_pct) >= MOVE_THRESHOLD_PCT]

    if notable:
        items = await _build_mover_items(notable, limit=3)
        text = public_midday_brief_active(date_str, items)
    else:
        text = public_midday_brief_quiet(date_str)

    await send_channel_message(text)
    logger.info("public mid-day brief sent (%d notable)", len(notable))


async def _compute_and_store_today_scores(
    moves_by_ticker: dict[str, TickerMove] | None = None,
) -> None:
    """
    Run xiangyu --fast on the watchlist, generate why_moving/risk_flag
    via Haiku 4.5, and upsert today's daily_scores row per ticker.

    `moves_by_ticker` carries today's intraday quotes so the narrative
    can fuse "what moved today" with "why fundamentally". When None
    (e.g. cold start), narrative still runs with components-only context.

    Best-effort across the board: any single failure is logged and the
    rest of the watchlist proceeds. Both the score AND the narrative are
    nice-to-have for downstream rendering — the radar push works either way.
    """
    try:
        pool = await db.get_pool()
    except Exception as exc:
        logger.warning("scoring: DB pool unavailable, skipping: %s", exc)
        return

    try:
        snapshots = await score_watchlist(DEFAULT_WATCHLIST)
    except Exception as exc:
        logger.warning("scoring: score_watchlist failed: %s", exc)
        return

    if not snapshots:
        logger.warning("scoring: zero snapshots returned for watchlist")
        return

    moves_map = moves_by_ticker or {}

    async def _narrate(snap: ScoreSnapshot) -> Narrative:
        move = moves_map.get(snap.ticker.upper())
        return await generate_narrative(
            ticker=snap.ticker,
            last_price=move.last_price if move else None,
            change_pct=move.change_pct if move else None,
            volume=move.volume if move else None,
            relative_volume=move.relative_volume if move else None,
            session_label="Post-close",
            score_100=snap.score_100,
            recommendation=snap.recommendation,
            components=snap.components,
        )

    narratives = await asyncio.gather(
        *[_narrate(s) for s in snapshots], return_exceptions=True,
    )

    et_date = today_et()
    stored = 0
    with_narrative = 0
    for snap, narr in zip(snapshots, narratives):
        why = None
        risk = None
        if isinstance(narr, Narrative):
            why = narr.why_moving
            risk = narr.risk_flag
            if why or risk:
                with_narrative += 1
        elif isinstance(narr, Exception):
            logger.warning("narrative: %s raised: %s", snap.ticker, narr)
        try:
            await store_score(pool, snap, et_date, why_moving=why, risk_flag=risk)
            stored += 1
        except Exception as exc:
            logger.warning("scoring: store_score failed for %s: %s",
                           snap.ticker, exc)
    logger.info(
        "scoring: stored %d/%d daily_scores rows (%d with narrative) for %s",
        stored, len(snapshots), with_narrative, et_date.isoformat(),
    )


async def public_eod_digest() -> None:
    if not is_trading_day(today_et()):
        logger.info("public EOD digest skipped — not a trading day")
        return
    if not _claim("digest-postclose-public"):
        return

    # Pull today's quotes first; pass them into _compute_and_store so the
    # narrative LLM call has "what moved today" alongside fundamentals.
    date_str = today_et().strftime("%a %b %d")
    moves = await fetch_watchlist_moves(DEFAULT_WATCHLIST)
    moves_by_ticker = {m.ticker.upper(): m for m in moves}

    # Compute today's score + narrative, persist, then read back via overlay.
    await _compute_and_store_today_scores(moves_by_ticker=moves_by_ticker)

    significant = [m for m in moves if abs(m.change_pct) >= MOVE_THRESHOLD_PCT]

    movers = await _build_mover_items(significant)
    text = public_postclose_digest(date_str, movers, notes=[])
    await send_channel_message(text)
    logger.info("public EOD digest sent (%d movers)", len(movers))


async def _send_dm(user_id: int, text: str) -> bool:
    """Send a Telegram DM to a single user. Returns True on success."""
    import os

    import httpx
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        logger.warning("send_dm: TELEGRAM_BOT_TOKEN missing")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": user_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json=payload)
        data = resp.json()
    except Exception as exc:
        logger.error("send_dm: HTTP error for %s: %s", user_id, exc)
        return False
    if not data.get("ok"):
        logger.warning(
            "send_dm: failed for %s: %s %s",
            user_id, data.get("error_code"), data.get("description"),
        )
        return False
    return True


def _build_pro_brief_for_mover(
    user_first_name: str,
    date_str: str,
    top_mover: TickerMove,
    score_row: ScoreRow | None,
    prior_score: ScoreRow | None,
    components: dict | None,
) -> str:
    mover_dict = {
        "ticker": top_mover.ticker,
        "change_pct": top_mover.change_pct,
        "price": top_mover.last_price,
        "prev_close": top_mover.prev_close,
        "relative_volume": top_mover.relative_volume,
    }

    score_change: int | None = None
    if score_row is not None and prior_score is not None:
        score_change = score_row.score_100 - prior_score.score_100

    strongest_pairs: list[tuple[str, str]] = []
    weakest_pairs: list[tuple[str, str]] = []
    peer_tickers: list[str] = []
    if components:
        strongest_keys, weakest_keys = rank_components(components, top_n=3)
        for key, _ in strongest_keys:
            hi = component_highlight(key, components.get(key))
            if hi:
                strongest_pairs.append((component_label(key), hi))
        for key, _ in weakest_keys:
            hi = component_highlight(key, components.get(key))
            if hi:
                weakest_pairs.append((component_label(key), hi))
        peer_tickers = extract_peer_tickers(components)

    return pro_daily_brief_card(
        date_str,
        user_first_name=user_first_name,
        mover=mover_dict,
        score_100=score_row.score_100 if score_row else None,
        rating=score_row.rating if score_row else None,
        score_change=score_change,
        why_moving=score_row.why_moving if score_row else None,
        risk_flag=score_row.risk_flag if score_row else None,
        strongest=strongest_pairs,
        weakest=weakest_pairs,
        peer_tickers=peer_tickers,
    )


async def _send_pro_brief_one(user_id: int, profile: dict) -> bool:
    """Build & send the 09:00 ET Pro DM for a single user."""
    import json as _json

    tickers = list(profile.get("watchlist") or [])
    threshold = float(profile.get("alert_threshold") or MOVE_THRESHOLD_PCT)
    first_name = profile.get("telegram_first_name") or "there"
    date_str = today_et().strftime("%a %b %d")

    if not tickers:
        return False  # silently skip users with empty watchlist

    moves = await fetch_watchlist_moves(tickers)
    crossings = [m for m in moves if abs(m.change_pct) >= threshold]

    if not crossings:
        text = pro_daily_brief_quiet(date_str, first_name)
        return await _send_dm(user_id, text)

    top_mover = max(crossings, key=lambda m: abs(m.change_pct))

    # Best-effort score + components lookup
    score_row: ScoreRow | None = None
    prior_score: ScoreRow | None = None
    components: dict | None = None
    try:
        pool = await db.get_pool()
        latest = await get_latest_scores(pool, [top_mover.ticker])
        score_row = latest.get(top_mover.ticker.upper())
        _, prior_score = await get_score_delta(pool, top_mover.ticker)

        # Pull the latest components_json blob for this ticker
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT components_json
                  FROM daily_scores
                 WHERE ticker = $1
                 ORDER BY date DESC
                 LIMIT 1
                """,
                top_mover.ticker.upper(),
            )
        if row and row["components_json"]:
            raw = row["components_json"]
            components = raw if isinstance(raw, dict) else _json.loads(raw)
    except Exception as exc:
        logger.debug("pro brief: score lookup failed for %s: %s",
                     top_mover.ticker, exc)

    text = _build_pro_brief_for_mover(
        user_first_name=first_name,
        date_str=date_str,
        top_mover=top_mover,
        score_row=score_row,
        prior_score=prior_score,
        components=components,
    )
    return await _send_dm(user_id, text)


async def personal_pro_daily_brief() -> None:
    """09:00 ET — DM every onboarded Pro user a personalized detail card."""
    if not is_trading_day(today_et()):
        logger.info("Pro daily brief skipped — not a trading day")
        return
    if not _claim("brief-pro-daily-personal"):
        return

    try:
        profiles = await db.get_all_active_profiles()
    except Exception as exc:
        logger.warning("pro brief: failed to load profiles: %s", exc)
        return

    if not profiles:
        logger.info("pro brief: no active profiles")
        return

    results = await asyncio.gather(*[
        _send_pro_brief_one(p["telegram_user_id"], p) for p in profiles
    ], return_exceptions=True)
    sent = sum(1 for r in results if r is True)
    logger.info("pro daily brief: sent %d/%d", sent, len(profiles))


async def _send_personal_digest(user_id: int, profile: dict) -> None:
    from ..telegram import send_channel_message as _send

    tickers = profile.get("watchlist", [])
    threshold = profile.get("alert_threshold", MOVE_THRESHOLD_PCT)
    date_str = today_et().strftime("%a %b %d")

    if not tickers:
        return

    moves = await fetch_watchlist_moves(tickers)
    crossings_raw = [m for m in moves if abs(m.change_pct) >= threshold]
    quiet_raw = [m for m in moves if abs(m.change_pct) < threshold]

    crossings = [
        {"ticker": m.ticker, "change_pct": m.change_pct, "price": m.last_price}
        for m in sorted(crossings_raw, key=lambda x: abs(x.change_pct), reverse=True)
    ]
    quiet_tickers = [m.ticker for m in quiet_raw]

    text = alert_eod_digest(crossings, quiet_tickers, date_str)

    try:
        import os
        import httpx
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": user_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json=payload)
        data = resp.json()
        if not data.get("ok"):
            logger.warning(
                "failed to send digest to %s: %s %s",
                user_id, data.get("error_code"), data.get("description"),
            )
    except Exception as exc:
        logger.error("error sending personal digest to %s: %s", user_id, exc)


async def personal_eod_digests() -> None:
    if not is_trading_day(today_et()):
        logger.info("personal EOD digests skipped — not a trading day")
        return

    profiles = await db.get_all_active_profiles()
    if not profiles:
        logger.info("no active profiles for personal EOD digest")
        return

    await asyncio.gather(*[
        _send_personal_digest(p["telegram_user_id"], p)
        for p in profiles
    ], return_exceptions=True)
    logger.info("personal EOD digests sent to %d users", len(profiles))
