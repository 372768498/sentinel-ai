"""Free Email Daily Radar — render and send the Sentinel Daily Market Radar.

Flow per call to ``send_email_digest()``:

1. Resolve audience.
   - ``only_email`` → single verified ``EmailLead`` matched by email (case-insensitive).
   - Otherwise → bulk: every ``EmailLead`` with ``verifiedAt IS NOT NULL``.
2. Build a single ``TickerIntelligenceProfile`` set covering the union of seed
   tickers across the audience (plus ``DEFAULT_SEED_TICKERS``), capped to keep
   the FMP / SEC / SERP budget bounded.
3. For each lead, pick the global top profile with state >= WATCHING as
   "today's anomaly", otherwise render the ``Nothing`` branch.
4. Resolve a per-lead ``seed_section`` mapping each of their seedTickers to a
   state (from the same profile set, or CALM fallback when no intel exists).
5. Send via Resend, unless ``dry_run`` is True.

Safety contract — every guard is enforced inside ``send_email_digest``:

- ``live=False`` is the default. Live sending requires the caller to flip it
  explicitly.
- Bulk live (``only_email`` not set) is refused unless ``allow_bulk=True``.
- ``EmailLead`` rows with ``verifiedAt IS NULL`` are never queried; the SQL
  filter is the single source of truth.
- ``only_email`` mode never accidentally fans out: it queries exactly one row.

The module never touches ``MARKETING_PUBLISH_DRY_RUN`` (Telegram kill-switch)
and never publishes to Telegram, X, or Feishu review.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Awaitable, Callable, Optional

import httpx

from .intelligence import (
    DEFAULT_SEED_TICKERS,
    TickerIntelligenceProfile,
    build_daily_profiles,
)
from .kpi_db import _connect
from .market_brief import market_brief_subject_preview, render_market_brief_text_async
from .state import STATE_DISPLAY, SentinelState
from .state_resolver import resolve_state
from .templates.free_email import (
    AnomalyEmailPayload,
    NothingEmailPayload,
    SeedTicker,
    pick_reflection_question,
    render_anomaly_email,
    render_email_html,
    render_nothing_email,
    render_seed_section,
)

logger = logging.getLogger(__name__)

RESEND_ENDPOINT = "https://api.resend.com/emails"
DEFAULT_PRO_URL_PATH = "/pro"
DEFAULT_METHODOLOGY_PATH = "/methodology"
DEFAULT_UNSUBSCRIBE_PATH = "/unsubscribe"
DEFAULT_SCAN_UNIVERSE_SIZE = 2000
INTEL_TICKER_CAP = 20
EPOCH_FOR_REFLECTION_ROTATION = date(2025, 1, 1)


# ---------------------------------------------------------------------------
# Models + DB
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VerifiedLead:
    email: str
    seed_tickers: tuple[str, ...]


VERIFIED_LEADS_SQL = """
SELECT email, COALESCE("seedTickers", ARRAY[]::text[]) AS seed_tickers
FROM "EmailLead"
WHERE "verifiedAt" IS NOT NULL
ORDER BY "verifiedAt" DESC
LIMIT $1
"""


VERIFIED_LEAD_BY_EMAIL_SQL = """
SELECT email, COALESCE("seedTickers", ARRAY[]::text[]) AS seed_tickers
FROM "EmailLead"
WHERE LOWER(email) = LOWER($1)
  AND "verifiedAt" IS NOT NULL
ORDER BY "verifiedAt" DESC
LIMIT 1
"""


async def fetch_verified_leads(*, limit: int = 50, conn=None) -> list[VerifiedLead]:
    if conn is not None:
        rows = await conn.fetch(VERIFIED_LEADS_SQL, max(0, int(limit)))
    else:
        async with _connect() as c:
            rows = await c.fetch(VERIFIED_LEADS_SQL, max(0, int(limit)))
    return [
        VerifiedLead(
            email=r["email"],
            seed_tickers=tuple(t.upper() for t in (r["seed_tickers"] or [])),
        )
        for r in rows
    ]


async def fetch_verified_lead_by_email(
    email: str, *, conn=None
) -> Optional[VerifiedLead]:
    if conn is not None:
        rows = await conn.fetch(VERIFIED_LEAD_BY_EMAIL_SQL, email)
    else:
        async with _connect() as c:
            rows = await c.fetch(VERIFIED_LEAD_BY_EMAIL_SQL, email)
    if not rows:
        return None
    r = rows[0]
    return VerifiedLead(
        email=r["email"],
        seed_tickers=tuple(t.upper() for t in (r["seed_tickers"] or [])),
    )


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------


def _split_subject_preview(rendered: str) -> tuple[str, str, str]:
    """Pull `Subject:` and `Preview:` headers off the rendered template.

    Returns ``(subject, preview, body_text)`` where ``body_text`` is the
    remainder with the headers and any leading blank line stripped.
    """
    subject = ""
    preview = ""
    lines = rendered.splitlines()
    rest_start = 0
    for i, line in enumerate(lines[:6]):
        stripped = line.strip()
        lowered = stripped.lower()
        if lowered.startswith("subject:"):
            subject = stripped.split(":", 1)[1].strip()
            rest_start = max(rest_start, i + 1)
        elif lowered.startswith("preview:"):
            preview = stripped.split(":", 1)[1].strip()
            rest_start = max(rest_start, i + 1)
    body = "\n".join(lines[rest_start:]).lstrip("\n")
    return subject, preview, body


def _seed_for_lead(
    seed_tickers: tuple[str, ...],
    profiles_by_ticker: dict[str, TickerIntelligenceProfile],
) -> str:
    if not seed_tickers:
        return ""
    seeds: list[SeedTicker] = []
    for ticker in seed_tickers:
        upper = ticker.upper()
        profile = profiles_by_ticker.get(upper)
        if profile is not None:
            state = resolve_state(profile)
        else:
            state = SentinelState.CALM
        seeds.append(
            SeedTicker(
                ticker=upper,
                state=state,
                one_liner=STATE_DISPLAY[state]["one_liner"],
            )
        )
    return render_seed_section(seeds)


def _select_top_profile(
    profiles: list[TickerIntelligenceProfile],
) -> Optional[TickerIntelligenceProfile]:
    for profile in profiles:
        if resolve_state(profile) != SentinelState.CALM:
            return profile
    return None


def _count_signal_bands(
    profile: TickerIntelligenceProfile,
    *,
    high: int = 65,
    low: int = 20,
) -> tuple[int, int]:
    """Return (confirming, disagreeing) signal counts mirroring state_resolver."""
    heats = (
        profile.market_heat,
        profile.social_heat,
        profile.search_heat,
        profile.news_heat,
        profile.competitor_heat,
    )
    confirming = sum(1 for h in heats if h >= high)
    disagreeing = sum(1 for h in heats if h <= low)
    return confirming, disagreeing


def _build_setup_bullets(profile: TickerIntelligenceProfile) -> str:
    bullets: list[str] = []
    for signal in profile.market_signals[:2]:
        bullets.append(f"  · {signal}")
    for catalyst in profile.catalysts[:2]:
        bullets.append(f"  · {catalyst}")
    if not bullets:
        bullets.append("  · context emerging from internal signals")
    return "\n".join(bullets)


def _build_sources_list(profile: TickerIntelligenceProfile) -> str:
    parts = list(profile.catalysts[:2]) + list(profile.social_signals[:1])
    if not parts:
        return "internal scan"
    return "; ".join(parts)


def _cta_url(base: str, ticker: str, *, content_id: str) -> str:
    return (
        f"{base.rstrip('/')}/stocks/{ticker.upper()}"
        f"?utm_source=email&utm_medium=daily_radar&utm_campaign={content_id}"
    )


def _build_anomaly_payload(
    *,
    lead: VerifiedLead,
    profile: TickerIntelligenceProfile,
    seed_section: str,
    now_et: datetime,
    public_url: str,
    pro_url: str,
    methodology_url: str,
    day_offset: int,
) -> AnomalyEmailPayload:
    state = resolve_state(profile)
    display = STATE_DISPLAY[state]
    mover = (profile.evidence or {}).get("mover", {}) or {}
    price = mover.get("price")
    change_pct = mover.get("change_pct")
    confirming, disagreeing = _count_signal_bands(profile)
    content_id = now_et.strftime("daily-%Y%m%d")
    subject = (
        f"{display['label']}: ${profile.ticker} — {profile.why_now[:60].rstrip('.')}"
    )
    preview = (
        f"{display['label']} state on ${profile.ticker}. "
        "Setup, sources, and one reflection question inside."
    )
    return AnomalyEmailPayload(
        subject_line=subject,
        preview_line=preview,
        date_long=now_et.strftime("%A, %B %d, %Y"),
        timestamp_et=now_et.strftime("%H:%M"),
        state=state,
        ticker=profile.ticker,
        price=float(price) if isinstance(price, (int, float)) else 0.0,
        price_change_pct=float(change_pct)
        if isinstance(change_pct, (int, float))
        else 0.0,
        session_label="Daily scan",
        setup_bullets=_build_setup_bullets(profile),
        matters_paragraph=profile.why_now,
        confirming_count=confirming,
        disagreeing_count=disagreeing,
        source_links_list=_build_sources_list(profile),
        cta_url=_cta_url(public_url, profile.ticker, content_id=content_id),
        seed_section=seed_section,
        reflection_question=pick_reflection_question(day_offset=day_offset),
        pro_url=pro_url,
        methodology_url=methodology_url,
        unsubscribe_url=(
            f"{public_url.rstrip('/')}{DEFAULT_UNSUBSCRIBE_PATH}?email={lead.email}"
        ),
    )


def _build_nothing_payload(
    *,
    seed_section: str,
    now_et: datetime,
    pro_url: str,
    scan_universe_size: int,
    market_brief_section: str = "",
    market_brief_subject: str = "Sentinel AI 美股市场日报：市场复盘与明日观察",
    market_brief_preview: str = "SPY · QQQ · IWM · VIX · 板块轮动 · 涨跌幅前10",
) -> NothingEmailPayload:
    return NothingEmailPayload(
        date_long=now_et.strftime("%A, %B %d, %Y"),
        timestamp_et=now_et.strftime("%H:%M"),
        scan_universe_size=scan_universe_size,
        seed_section=seed_section,
        pro_url=pro_url,
        market_brief_section=market_brief_section,
        subject_line=market_brief_subject,
        preview_line=market_brief_preview,
    )


def _render_for_lead(
    *,
    lead: VerifiedLead,
    profiles: list[TickerIntelligenceProfile],
    now_et: datetime,
    public_url: str,
    pro_url: str,
    methodology_url: str,
    scan_universe_size: int,
    day_offset: int,
    market_brief_section: str = "",
    market_brief_subject: str = "Sentinel AI 美股市场日报：市场复盘与明日观察",
    market_brief_preview: str = "SPY · QQQ · IWM · VIX · 板块轮动 · 涨跌幅前10",
) -> tuple[str, str, str, str]:
    """Return ``(subject, preview, text_body, html_body)`` for the lead."""
    profiles_by_ticker = {p.ticker.upper(): p for p in profiles}
    seed_section = _seed_for_lead(lead.seed_tickers, profiles_by_ticker)
    top = _select_top_profile(profiles)
    if top is None:
        nothing = _build_nothing_payload(
            seed_section=seed_section,
            now_et=now_et,
            pro_url=pro_url,
            scan_universe_size=scan_universe_size,
            market_brief_section=market_brief_section,
            market_brief_subject=market_brief_subject,
            market_brief_preview=market_brief_preview,
        )
        rendered = render_nothing_email(nothing)
        # The Nothing template hardcodes Subject/Preview; pull them out.
        subject, preview, body = _split_subject_preview(rendered)
        return subject, preview, body, render_email_html(
            subject=subject, preview=preview, body_text=body
        )
    anomaly = _build_anomaly_payload(
        lead=lead,
        profile=top,
        seed_section=seed_section,
        now_et=now_et,
        public_url=public_url,
        pro_url=pro_url,
        methodology_url=methodology_url,
        day_offset=day_offset,
    )
    rendered = render_anomaly_email(anomaly)
    subject, preview, body = _split_subject_preview(rendered)
    return subject, preview, body, render_email_html(
        subject=subject, preview=preview, body_text=body
    )


# ---------------------------------------------------------------------------
# Resend transport
# ---------------------------------------------------------------------------


async def send_via_resend(
    *,
    api_key: str,
    from_email: str,
    to_email: str,
    subject: str,
    text_body: str | None,
    html_body: Optional[str] = None,
    dry_run: bool,
    client: Optional[httpx.AsyncClient] = None,
) -> Optional[str]:
    """Single Resend POST. Returns the Resend message id, or ``None`` on dry-run."""
    if dry_run:
        return None
    if not api_key:
        raise RuntimeError(
            "RESEND_API_KEY not set — refusing to send live email."
        )
    payload = {
        "from": from_email,
        "to": [to_email],
        "subject": subject,
    }
    if text_body:
        payload["text"] = text_body
    if html_body:
        payload["html"] = html_body
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if client is not None:
        response = await client.post(RESEND_ENDPOINT, json=payload, headers=headers)
    else:
        async with httpx.AsyncClient(timeout=30.0) as c:
            response = await c.post(RESEND_ENDPOINT, json=payload, headers=headers)
    response.raise_for_status()
    data = response.json()
    return data.get("id")


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


IntelFetcher = Callable[..., Awaitable[list[TickerIntelligenceProfile]]]
LeadsFetcher = Callable[..., Awaitable[list[VerifiedLead]]]
SingleLeadFetcher = Callable[..., Awaitable[Optional[VerifiedLead]]]
ResendSender = Callable[..., Awaitable[Optional[str]]]
MarketBriefFetcher = Callable[[], Awaitable[str]]
MarketBriefSubjectFetcher = Callable[[], tuple[str, str]]


def _public_base() -> str:
    base = os.environ.get("GROWTH_OS_PUBLIC_URL", "").strip()
    if not base:
        base = os.environ.get("NEXT_PUBLIC_APP_URL", "").strip()
    if not base:
        base = "https://sentinelai.com"
    return base.rstrip("/")


def _pro_url() -> str:
    return _public_base() + DEFAULT_PRO_URL_PATH


def _methodology_url() -> str:
    return _public_base() + DEFAULT_METHODOLOGY_PATH


def _resend_from_email() -> str:
    value = os.environ.get("RESEND_FROM_EMAIL", "").strip()
    if value:
        return value
    return "Sentinel AI <onboarding@resend.dev>"


def _resend_api_key() -> str:
    return os.environ.get("RESEND_API_KEY", "").strip()


def _day_offset(now_utc: datetime) -> int:
    delta = now_utc.date() - EPOCH_FOR_REFLECTION_ROTATION
    return max(0, delta.days)


async def send_email_digest(
    *,
    only_email: Optional[str] = None,
    live: bool = False,
    allow_bulk: bool = False,
    limit: int = 50,
    intel_fetcher: IntelFetcher = build_daily_profiles,
    leads_fetcher: Optional[LeadsFetcher] = None,
    single_lead_fetcher: Optional[SingleLeadFetcher] = None,
    resend_sender: ResendSender = send_via_resend,
    market_brief_fetcher: MarketBriefFetcher = render_market_brief_text_async,
    market_brief_subject_fetcher: MarketBriefSubjectFetcher = market_brief_subject_preview,
    conn=None,
    now_utc: Optional[datetime] = None,
) -> dict:
    """Render and (optionally) send the daily Sentinel email digest.

    Returns a stats dict the caller (CLI or cron) can print verbatim:

        {
          "session": "email_daily",
          "mode": "dry-run" | "live",
          "only_email": str | None,
          "leads_queried": int,
          "leads_eligible": int,
          "sent": int,
          "skipped_unverified": int,
          "errors": [str, ...],
          "renders": [{"email": str, "subject": str, "branch": str}, ...],
        }
    """
    dry_run = not live
    mode = "live" if live else "dry-run"

    # --- Safety gate: bulk live without explicit opt-in is refused. ---------
    if live and not only_email and not allow_bulk:
        return {
            "session": "email_daily",
            "mode": mode,
            "only_email": None,
            "leads_queried": 0,
            "leads_eligible": 0,
            "sent": 0,
            "skipped_unverified": 0,
            "errors": [
                "bulk live send refused — pass allow_bulk=True or restrict "
                "via only_email to opt in."
            ],
            "renders": [],
        }

    # --- Resolve audience ---------------------------------------------------
    leads: list[VerifiedLead]
    skipped_unverified = 0
    if only_email:
        if single_lead_fetcher is not None:
            lead = await single_lead_fetcher(only_email)
        else:
            lead = await fetch_verified_lead_by_email(only_email, conn=conn)
        if lead is None:
            leads = []
            skipped_unverified = 1
        else:
            leads = [lead]
    else:
        if leads_fetcher is not None:
            leads = await leads_fetcher(limit=limit)
        else:
            leads = await fetch_verified_leads(limit=limit, conn=conn)

    if not leads:
        return {
            "session": "email_daily",
            "mode": mode,
            "only_email": only_email,
            "leads_queried": 0,
            "leads_eligible": 0,
            "sent": 0,
            "skipped_unverified": skipped_unverified,
            "errors": [],
            "renders": [],
        }

    # --- Build intel covering the union of seed tickers ---------------------
    seed_union: set[str] = {t.upper() for t in DEFAULT_SEED_TICKERS}
    for lead in leads:
        seed_union.update(lead.seed_tickers)
    seed_list = sorted(seed_union)[:INTEL_TICKER_CAP]

    try:
        profiles = await intel_fetcher(
            seed_tickers=seed_list, limit=len(seed_list)
        )
    except Exception as exc:
        logger.exception("[email_jobs] intel_fetcher failed")
        return {
            "session": "email_daily",
            "mode": mode,
            "only_email": only_email,
            "leads_queried": len(leads),
            "leads_eligible": len(leads),
            "sent": 0,
            "skipped_unverified": skipped_unverified,
            "errors": [f"intel: {exc}"],
            "renders": [],
        }

    now = now_utc or datetime.now(timezone.utc)
    public_url = _public_base()
    pro_url = _pro_url()
    methodology_url = _methodology_url()
    day_offset = _day_offset(now)
    api_key = _resend_api_key()
    from_email = _resend_from_email()
    market_brief_section = ""
    market_brief_subject = "Sentinel AI 美股市场日报：市场复盘与明日观察"
    market_brief_preview = "SPY · QQQ · IWM · VIX · 板块轮动 · 涨跌幅前10"
    try:
        market_brief_section = await market_brief_fetcher()
        if market_brief_section:
            market_brief_subject, market_brief_preview = market_brief_subject_fetcher()
    except Exception as exc:
        logger.warning("[email_jobs] market_brief failed: %s", exc)

    sent = 0
    errors: list[str] = []
    renders: list[dict] = []

    for lead in leads:
        try:
            subject, preview, body_text, html_body = _render_for_lead(
                lead=lead,
                profiles=profiles,
                now_et=now,
                public_url=public_url,
                pro_url=pro_url,
                methodology_url=methodology_url,
                scan_universe_size=DEFAULT_SCAN_UNIVERSE_SIZE,
                day_offset=day_offset,
                market_brief_section=market_brief_section,
                market_brief_subject=market_brief_subject,
                market_brief_preview=market_brief_preview,
            )
        except Exception as exc:
            logger.exception("[email_jobs] render failed for %s", lead.email)
            errors.append(f"render({lead.email}): {exc}")
            continue

        branch = "anomaly" if _select_top_profile(profiles) else "nothing"
        renders.append({"email": lead.email, "subject": subject, "branch": branch})
        logger.info(
            "[email_jobs] %s lead=%s subject=%r preview=%r seed_count=%d branch=%s",
            mode.upper(),
            lead.email,
            subject,
            preview,
            len(lead.seed_tickers),
            branch,
        )

        try:
            await resend_sender(
                api_key=api_key,
                from_email=from_email,
                to_email=lead.email,
                subject=subject,
                text_body=None if html_body else body_text,
                html_body=html_body,
                dry_run=dry_run,
            )
            sent += 1
        except Exception as exc:
            logger.exception("[email_jobs] send failed for %s", lead.email)
            errors.append(f"send({lead.email}): {exc}")

    return {
        "session": "email_daily",
        "mode": mode,
        "only_email": only_email,
        "leads_queried": len(leads),
        "leads_eligible": len(leads),
        "sent": sent,
        "skipped_unverified": skipped_unverified,
        "errors": errors,
        "renders": renders,
    }


# ---------------------------------------------------------------------------
# Scheduler-friendly wrapper
# ---------------------------------------------------------------------------


def _truthy(value: str) -> bool:
    return value.strip().lower() in ("1", "true", "yes", "on")


def _scheduled_dry_run() -> bool:
    raw = os.environ.get("MARKETING_EMAIL_DAILY_DRY_RUN", "true")
    return _truthy(raw) if raw else True


def _scheduled_allow_bulk() -> bool:
    return _truthy(os.environ.get("MARKETING_EMAIL_DAILY_ALLOW_BULK", "false"))


def _scheduled_limit() -> int:
    raw = os.environ.get("MARKETING_EMAIL_DAILY_LIMIT", "50")
    try:
        return max(0, int(raw))
    except ValueError:
        return 50


def _safe_scheduled_summary(stats: dict) -> dict:
    """Small production-log summary without recipient addresses or secrets."""
    renders = stats.get("renders") or []
    branches: dict[str, int] = {}
    for row in renders:
        branch = str(row.get("branch") or "unknown")
        branches[branch] = branches.get(branch, 0) + 1
    return {
        "session": stats.get("session"),
        "mode": stats.get("mode"),
        "leads_queried": stats.get("leads_queried"),
        "leads_eligible": stats.get("leads_eligible"),
        "sent": stats.get("sent"),
        "skipped_unverified": stats.get("skipped_unverified"),
        "error_count": len(stats.get("errors") or []),
        "branches": branches,
    }


async def run_scheduled_email_digest() -> dict:
    """Reads env flags and runs ``send_email_digest`` for the cron path.

    The scheduler defaults to dry-run (``MARKETING_EMAIL_DAILY_DRY_RUN=true``)
    AND bulk-disabled (``MARKETING_EMAIL_DAILY_ALLOW_BULK=false``). The two
    flags must BOTH be flipped to actually send to the whole verified list —
    a deliberate double-key so a single accidental env change does not start
    bulk email.
    """
    live = not _scheduled_dry_run()
    allow_bulk = _scheduled_allow_bulk()
    limit = _scheduled_limit()
    stats = await send_email_digest(
        only_email=None,
        live=live,
        allow_bulk=allow_bulk,
        limit=limit,
    )
    print(
        f"[email_jobs] scheduled summary={_safe_scheduled_summary(stats)}",
        flush=True,
    )
    logger.info("[email_jobs] scheduled run stats=%s", stats)
    return stats
