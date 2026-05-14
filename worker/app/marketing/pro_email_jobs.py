"""Pro Email Daily Intelligence Report orchestrator.

Sister module to ``email_jobs.py`` (Free) — same Resend send path, but the
audience and payload come from the v2 stack:

  - audience:   User.proTier IN ('pro','desk') joined to
                SubscriptionStatus.telegramUserId to find the user's bot
                watchlist. Users with no bot link still receive the
                default-watchlist version.
  - payload:    today's TickerMove from yfinance.fast_info,
                last daily_scores row per ticker (score / rating /
                why_moving / risk_flag / components_json),
                peer comparison snippet rendered via highlights.py.

Safety contract identical to Free Email orchestrator:
  - dry_run is the default; live requires explicit flip.
  - bulk live requires allow_bulk=True OR only_email scoping.
  - we never touch MARKETING_PUBLISH_DRY_RUN (that gate is for Telegram).
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Awaitable, Callable, Optional

from ..scanner import TickerMove, fetch_watchlist_moves
from ..scoring import get_latest_scores, get_score_delta
from ..scoring.highlights import (
    component_highlight,
    component_label,
    extract_peer_tickers,
)
from ..watchlist import DEFAULT_WATCHLIST
from .email_jobs import send_via_resend
from .kpi_db import _connect
from .templates.pro_email import (
    DimensionRow,
    ProEmailDailyPayload,
    WatchlistMover,
    render_email,
)

logger = logging.getLogger(__name__)

DEFAULT_PUBLIC_BASE = "https://app.jilo.ai"
PRO_EMAIL_SESSION_LABEL = "Pre-market"


# ── Audience model ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ProAudienceRow:
    user_id: str
    email: str
    pro_tier: str                # 'pro' | 'desk'
    telegram_user_id: Optional[int]


PRO_AUDIENCE_SQL = """
SELECT u.id            AS user_id,
       u.email         AS email,
       u."proTier"     AS pro_tier,
       s."telegramUserId" AS tg_user_id
  FROM "User" u
  LEFT JOIN "SubscriptionStatus" s ON s."userId" = u.id
 WHERE u."proTier" IN ('pro', 'desk')
   AND u.email IS NOT NULL
 ORDER BY u.id
 LIMIT $1
"""

PRO_AUDIENCE_BY_EMAIL_SQL = """
SELECT u.id            AS user_id,
       u.email         AS email,
       u."proTier"     AS pro_tier,
       s."telegramUserId" AS tg_user_id
  FROM "User" u
  LEFT JOIN "SubscriptionStatus" s ON s."userId" = u.id
 WHERE LOWER(u.email) = LOWER($1)
   AND u."proTier" IN ('pro', 'desk')
 LIMIT 1
"""

BOT_WATCHLIST_SQL = """
SELECT watchlist
  FROM telegram_bot_profile
 WHERE telegram_user_id = $1
 LIMIT 1
"""


def _row_to_audience(r) -> ProAudienceRow:
    tg = r["tg_user_id"]
    return ProAudienceRow(
        user_id=str(r["user_id"]),
        email=str(r["email"]),
        pro_tier=str(r["pro_tier"]),
        telegram_user_id=int(tg) if tg is not None else None,
    )


async def fetch_pro_audience(*, limit: int = 100, conn=None) -> list[ProAudienceRow]:
    if conn is not None:
        rows = await conn.fetch(PRO_AUDIENCE_SQL, max(0, int(limit)))
    else:
        async with _connect() as c:
            rows = await c.fetch(PRO_AUDIENCE_SQL, max(0, int(limit)))
    return [_row_to_audience(r) for r in rows]


async def fetch_pro_audience_by_email(
    email: str, *, conn=None,
) -> Optional[ProAudienceRow]:
    if conn is not None:
        rows = await conn.fetch(PRO_AUDIENCE_BY_EMAIL_SQL, email)
    else:
        async with _connect() as c:
            rows = await c.fetch(PRO_AUDIENCE_BY_EMAIL_SQL, email)
    if not rows:
        return None
    return _row_to_audience(rows[0])


async def fetch_user_watchlist(
    tg_user_id: Optional[int], *, conn=None,
) -> list[str]:
    """Pull the watchlist from telegram_bot_profile; falls back to DEFAULT."""
    if tg_user_id is None:
        return list(DEFAULT_WATCHLIST)
    if conn is not None:
        row = await conn.fetchrow(BOT_WATCHLIST_SQL, tg_user_id)
    else:
        async with _connect() as c:
            row = await c.fetchrow(BOT_WATCHLIST_SQL, tg_user_id)
    if not row or not row["watchlist"]:
        return list(DEFAULT_WATCHLIST)
    return [t.upper() for t in row["watchlist"]]


# ── Payload assembly ──────────────────────────────────────────────────────────


def _component_to_dimension(name: str, comp: dict) -> Optional[DimensionRow]:
    """Convert a xiangyu component dict → 0–10 normalized DimensionRow."""
    if not isinstance(comp, dict):
        return None
    raw = comp.get("score")
    if not isinstance(raw, (int, float)):
        return None
    # xiangyu components emit roughly 0–1 (some can be slightly negative);
    # clamp & scale to 0–10 for the bar.
    norm = max(0.0, min(1.0, float(raw)))
    score_10 = norm * 10.0
    highlight = component_highlight(name, comp) or "—"
    return DimensionRow(
        label=component_label(name),
        score_10=score_10,
        highlight=highlight,
    )


def _build_dimensions(components: dict) -> list[DimensionRow]:
    if not isinstance(components, dict):
        return []
    rows: list[DimensionRow] = []
    # Stable display order: roughly score-weight descending from SKILL.md
    order = [
        "fundamentals",
        "earnings_surprise",
        "analyst_sentiment",
        "technical",
        "sentiment_analysis",
        "peer_comparison",
        "market_context",
        "sector_performance",
        "historical_patterns",
    ]
    for key in order:
        comp = components.get(key)
        if comp is None:
            continue
        row = _component_to_dimension(key, comp)
        if row is not None:
            rows.append(row)
    return rows


def _build_peer_check_lines(components: dict, top_ticker: str) -> list[str]:
    """One-liner per material peer comparison delta."""
    peer = components.get("peer_comparison") if isinstance(components, dict) else None
    if not isinstance(peer, dict):
        return []
    comparisons = peer.get("comparisons") or {}
    if not isinstance(comparisons, dict):
        return []
    lines: list[str] = []
    label_map = {
        "pe": "P/E ratio",
        "ps": "P/S ratio",
        "pb": "P/B ratio",
        "revenue_growth": "Revenue growth",
        "net_margin": "Net margin",
    }
    for key, payload in comparisons.items():
        if not isinstance(payload, dict):
            continue
        premium = payload.get("premium_pct")
        if not isinstance(premium, (int, float)):
            continue
        direction = "premium" if premium > 0 else "discount"
        lines.append(
            f"{label_map.get(key, key)}: {abs(premium):.0f}% {direction} vs peers"
        )
    return lines[:3]


async def _build_watchlist_movers(
    pool_overlay: dict[str, dict],
    moves: list[TickerMove],
) -> list[WatchlistMover]:
    """Render the at-a-glance table from per-ticker score overlay."""
    out: list[WatchlistMover] = []
    moves_map = {m.ticker.upper(): m for m in moves}
    for ticker, overlay in pool_overlay.items():
        move = moves_map.get(ticker)
        change_pct = float(move.change_pct) if move is not None else 0.0
        if change_pct > 0:
            emoji = "📈"
        elif change_pct < 0:
            emoji = "📉"
        else:
            emoji = "⏸"
        out.append(
            WatchlistMover(
                ticker=ticker,
                state_emoji=emoji,
                change_pct=change_pct,
                score_100=overlay.get("score_100"),
                rating=overlay.get("rating"),
                score_change=overlay.get("score_change"),
            )
        )
    # Sort by |change_pct| descending
    out.sort(key=lambda m: abs(m.change_pct), reverse=True)
    return out


async def _overlay_for_tickers(conn, tickers: list[str]) -> dict[str, dict]:
    """Score overlay {ticker: {score_100, rating, score_change}} via conn."""
    if not tickers:
        return {}
    latest = await get_latest_scores(conn, tickers)
    overlay: dict[str, dict] = {}
    for ticker in tickers:
        row = latest.get(ticker.upper())
        if row is None:
            continue
        delta: Optional[int] = None
        try:
            _, prior = await get_score_delta(conn, ticker)
            if prior is not None:
                delta = row.score_100 - prior.score_100
        except Exception:
            pass
        overlay[ticker.upper()] = {
            "score_100": row.score_100,
            "rating": row.rating,
            "score_change": delta,
            "why_moving": row.why_moving,
            "risk_flag": row.risk_flag,
        }
    return overlay


async def _load_components(conn, ticker: str) -> dict:
    row = await conn.fetchrow(
        """
        SELECT components_json
          FROM daily_scores
         WHERE ticker = $1
         ORDER BY date DESC
         LIMIT 1
        """,
        ticker.upper(),
    )
    if not row or not row["components_json"]:
        return {}
    raw = row["components_json"]
    return raw if isinstance(raw, dict) else json.loads(raw)


def _public_base() -> str:
    base = (
        os.environ.get("GROWTH_OS_PUBLIC_URL", "").strip()
        or os.environ.get("NEXT_PUBLIC_APP_URL", "").strip()
    )
    return (base or DEFAULT_PUBLIC_BASE).rstrip("/")


def _resend_from_email() -> str:
    return (
        os.environ.get("RESEND_FROM_EMAIL", "").strip()
        or "Sentinel Pro <onboarding@resend.dev>"
    )


def _resend_api_key() -> str:
    return os.environ.get("RESEND_API_KEY", "").strip()


def _truthy(v: str) -> bool:
    return v.strip().lower() in ("1", "true", "yes", "on")


async def build_payload_for_user(
    *,
    audience: ProAudienceRow,
    conn,
    now_et: datetime,
) -> Optional[ProEmailDailyPayload]:
    """
    Build the email payload for one Pro user. Returns None when there is
    not enough data to produce a meaningful email (no quotes / no movers).
    """
    tickers = await fetch_user_watchlist(audience.telegram_user_id, conn=conn)
    if not tickers:
        return None

    moves = await fetch_watchlist_moves(tickers)
    if not moves:
        return None

    overlay = await _overlay_for_tickers(conn, tickers)

    # Top mover = max |change_pct|, falling back to first available quote.
    top_move = max(moves, key=lambda m: abs(m.change_pct))
    top_overlay = overlay.get(top_move.ticker.upper(), {})

    components = await _load_components(conn, top_move.ticker)
    dimensions = _build_dimensions(components)
    peer_tickers = extract_peer_tickers(components)
    peer_lines = _build_peer_check_lines(components, top_move.ticker)
    watchlist_movers = await _build_watchlist_movers(overlay, moves)

    public_base = _public_base()
    top_report_url = f"{public_base}/stocks/{top_move.ticker.upper()}"
    manage_url = f"{public_base}/account"
    methodology_url = f"{public_base}/methodology"

    score = top_overlay.get("score_100")
    rating = top_overlay.get("rating")
    score_change = top_overlay.get("score_change")
    why_moving = top_overlay.get("why_moving")
    risk_flag = top_overlay.get("risk_flag")

    direction = "+" if top_move.change_pct >= 0 else ""
    subject_line = (
        f"${top_move.ticker} {direction}{top_move.change_pct:.1f}% "
        f"— Sentinel score {score if score is not None else '—'}"
    )
    preview_line = (
        f"Today's biggest move on your watchlist with a 10-dim breakdown."
    )

    return ProEmailDailyPayload(
        subject_line=subject_line,
        preview_line=preview_line,
        date_long=now_et.strftime("%A, %B %d, %Y"),
        delivery_time_et=now_et.strftime("%H:%M"),
        watchlist_tickers_line=" · ".join(tickers),
        top_ticker=top_move.ticker.upper(),
        top_price=float(top_move.last_price),
        top_change_pct=float(top_move.change_pct),
        top_session=PRO_EMAIL_SESSION_LABEL,
        top_relative_volume=float(top_move.relative_volume or 0.0),
        top_prev_close=float(top_move.prev_close),
        top_score=score,
        top_rating=rating,
        top_score_change=score_change,
        why_moving=why_moving,
        risk_flag=risk_flag,
        dimensions=dimensions,
        peer_tickers=peer_tickers,
        peer_check_lines=peer_lines,
        watchlist_movers=watchlist_movers,
        top_report_url=top_report_url,
        manage_url=manage_url,
        methodology_url=methodology_url,
    )


# ── Orchestrator ──────────────────────────────────────────────────────────────


AudienceFetcher = Callable[..., Awaitable[list[ProAudienceRow]]]
SingleAudienceFetcher = Callable[..., Awaitable[Optional[ProAudienceRow]]]
ResendSender = Callable[..., Awaitable[Optional[str]]]
PayloadBuilder = Callable[..., Awaitable[Optional[ProEmailDailyPayload]]]


def _split_subject_preview(rendered: str) -> tuple[str, str, str]:
    """Strip Subject: / Preview: lines off the rendered template."""
    subject = preview = ""
    lines = rendered.splitlines()
    rest_start = 0
    for i, line in enumerate(lines[:6]):
        stripped = line.strip()
        lower = stripped.lower()
        if lower.startswith("subject:"):
            subject = stripped.split(":", 1)[1].strip()
            rest_start = max(rest_start, i + 1)
        elif lower.startswith("preview:"):
            preview = stripped.split(":", 1)[1].strip()
            rest_start = max(rest_start, i + 1)
    body = "\n".join(lines[rest_start:]).lstrip("\n")
    return subject, preview, body


async def send_pro_email_digest(
    *,
    only_email: Optional[str] = None,
    live: bool = False,
    allow_bulk: bool = False,
    limit: int = 100,
    audience_fetcher: Optional[AudienceFetcher] = None,
    single_audience_fetcher: Optional[SingleAudienceFetcher] = None,
    payload_builder: Optional[PayloadBuilder] = None,
    resend_sender: ResendSender = send_via_resend,
    conn=None,
    now_utc: Optional[datetime] = None,
) -> dict:
    """Render and (optionally) send the Pro Email Daily Intelligence Report.

    Mirrors the Free email orchestrator surface so ops/CLI can call either
    with the same patterns.
    """
    dry_run = not live
    mode = "live" if live else "dry-run"

    # Safety: bulk live without explicit opt-in is refused
    if live and not only_email and not allow_bulk:
        return {
            "session": "pro_email_daily",
            "mode": mode,
            "only_email": None,
            "leads_queried": 0,
            "leads_eligible": 0,
            "sent": 0,
            "errors": [
                "bulk live send refused — pass allow_bulk=True or restrict "
                "via only_email to opt in."
            ],
            "renders": [],
        }

    # Resolve audience
    audience: list[ProAudienceRow]
    if only_email:
        fetcher = single_audience_fetcher or fetch_pro_audience_by_email
        one = await fetcher(only_email, conn=conn) if conn is not None \
            else await fetcher(only_email)
        audience = [one] if one is not None else []
    else:
        fetcher2 = audience_fetcher or fetch_pro_audience
        if conn is not None:
            audience = await fetcher2(limit=limit, conn=conn)
        else:
            audience = await fetcher2(limit=limit)

    if not audience:
        return {
            "session": "pro_email_daily",
            "mode": mode,
            "only_email": only_email,
            "leads_queried": 0,
            "leads_eligible": 0,
            "sent": 0,
            "errors": [],
            "renders": [],
        }

    now = now_utc or datetime.now(timezone.utc)
    api_key = _resend_api_key()
    from_email = _resend_from_email()

    sent = 0
    errors: list[str] = []
    renders: list[dict] = []

    # Open one DB conn for all payload builds if caller didn't pass one in
    own_conn = conn is None

    async def _build(a: ProAudienceRow, c) -> Optional[ProEmailDailyPayload]:
        if payload_builder is not None:
            return await payload_builder(audience=a, conn=c, now_et=now)
        return await build_payload_for_user(audience=a, conn=c, now_et=now)

    if own_conn:
        # All builds share one Pool connection
        async with _connect() as c:
            for a in audience:
                try:
                    payload = await _build(a, c)
                except Exception as exc:
                    logger.exception("[pro_email_jobs] build failed for %s", a.email)
                    errors.append(f"build({a.email}): {exc}")
                    continue
                await _render_and_send(
                    a, payload, dry_run, api_key, from_email,
                    resend_sender, renders, errors,
                )
                if payload is not None and a.email not in {r.get("email") for r in renders}:
                    pass
                if payload is not None:
                    sent += 1 if any(
                        r["email"] == a.email and r.get("status") == "sent"
                        for r in renders
                    ) else 0
    else:
        for a in audience:
            try:
                payload = await _build(a, conn)
            except Exception as exc:
                logger.exception("[pro_email_jobs] build failed for %s", a.email)
                errors.append(f"build({a.email}): {exc}")
                continue
            await _render_and_send(
                a, payload, dry_run, api_key, from_email,
                resend_sender, renders, errors,
            )

    # Recount sent so dry-run also reports renders
    sent = sum(1 for r in renders if r.get("status") in ("sent", "dry-run"))

    return {
        "session": "pro_email_daily",
        "mode": mode,
        "only_email": only_email,
        "leads_queried": len(audience),
        "leads_eligible": len(audience),
        "sent": sent,
        "errors": errors,
        "renders": renders,
    }


async def _render_and_send(
    a: ProAudienceRow,
    payload: Optional[ProEmailDailyPayload],
    dry_run: bool,
    api_key: str,
    from_email: str,
    resend_sender: ResendSender,
    renders: list[dict],
    errors: list[str],
) -> None:
    if payload is None:
        renders.append({"email": a.email, "status": "skipped",
                        "reason": "no movers / empty watchlist"})
        return
    rendered = render_email(payload)
    subject, preview, body_text = _split_subject_preview(rendered)
    logger.info(
        "[pro_email_jobs] %s lead=%s subject=%r preview=%r top=%s",
        "DRY-RUN" if dry_run else "LIVE",
        a.email, subject, preview, payload.top_ticker,
    )
    try:
        await resend_sender(
            api_key=api_key,
            from_email=from_email,
            to_email=a.email,
            subject=subject,
            text_body=body_text,
            dry_run=dry_run,
        )
        renders.append({
            "email": a.email,
            "subject": subject,
            "top": payload.top_ticker,
            "status": "dry-run" if dry_run else "sent",
        })
    except Exception as exc:
        logger.exception("[pro_email_jobs] send failed for %s", a.email)
        errors.append(f"send({a.email}): {exc}")
        renders.append({"email": a.email, "status": "error", "reason": str(exc)})


# ── Scheduler-friendly wrapper ────────────────────────────────────────────────


def _scheduled_dry_run() -> bool:
    return _truthy(os.environ.get("MARKETING_PRO_EMAIL_DAILY_DRY_RUN", "true"))


def _scheduled_allow_bulk() -> bool:
    return _truthy(os.environ.get("MARKETING_PRO_EMAIL_DAILY_ALLOW_BULK", "false"))


def _scheduled_limit() -> int:
    raw = os.environ.get("MARKETING_PRO_EMAIL_DAILY_LIMIT", "100")
    try:
        return max(0, int(raw))
    except ValueError:
        return 100


async def run_scheduled_pro_email_digest() -> dict:
    """Read env flags + run send_pro_email_digest for the cron path."""
    live = not _scheduled_dry_run()
    allow_bulk = _scheduled_allow_bulk()
    limit = _scheduled_limit()
    stats = await send_pro_email_digest(
        only_email=None,
        live=live,
        allow_bulk=allow_bulk,
        limit=limit,
    )
    logger.info("[pro_email_jobs] scheduled run stats=%s", stats)
    return stats
