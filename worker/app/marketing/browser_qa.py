"""Browser QA Harness · Week 7.

Purpose: BEFORE flipping Telegram to live, every CTA URL we publish must be
rendered in a real browser and shown to:
  - return 200
  - contain the email gate input
  - contain the disclaimer line
  - optionally contain the Telegram secondary CTA

This is QA + Screenshot + Conversion-path check, NOT a scraper. It only
visits Sentinel's own landing pages. It is not used to crawl X / Reddit /
TikTok / YouTube — that is explicitly out of scope.

Design split:
  - Pure HTML detectors (regex/string match) — fully testable without a browser.
  - `check_landing_url(...)` orchestrator — uses Playwright when available,
    falls back to BrowserCheckResult(ok=False, error='playwright_not_installed')
    when not.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Awaitable, Callable, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

try:
    from playwright.async_api import async_playwright  # type: ignore
    PLAYWRIGHT_AVAILABLE = True
except ImportError:  # pragma: no cover
    async_playwright = None  # type: ignore
    PLAYWRIGHT_AVAILABLE = False


DEFAULT_TIMEOUT_MS = 20_000
DEFAULT_VIEWPORT = {"width": 1280, "height": 800}

DISCLAIMER_PHRASES = (
    "Context, not financial advice",
    "Not financial advice",
    "not financial advice",
    "Not investment advice",
)


@dataclass(frozen=True)
class BrowserCheckResult:
    url: str
    ok: bool
    status_code: int | None
    title: str | None
    checks: dict[str, bool]
    screenshot_path: str | None
    error: str | None = None


# ---------------------------------------------------------------------------
# Pure HTML detectors — safe to call without Playwright
# ---------------------------------------------------------------------------


_EMAIL_INPUT_RE = re.compile(
    r'<input[^>]*type=["\']email["\']', re.IGNORECASE
)


def detect_email_gate(html: str) -> bool:
    return bool(_EMAIL_INPUT_RE.search(html))


def detect_disclaimer(html: str) -> bool:
    return any(phrase in html for phrase in DISCLAIMER_PHRASES)


def detect_telegram_cta(html: str) -> bool:
    # Match either the CTA text or any t.me link
    if "on Telegram" in html or "Telegram channel" in html:
        return True
    if "t.me/" in html or "https://t.me" in html:
        return True
    return False


def detect_ticker_reference(html: str, *, ticker: str | None = None) -> bool:
    if "Sentinel AI" in html:
        return True
    if ticker and f"${ticker.upper()}" in html.upper():
        return True
    return False


# ---------------------------------------------------------------------------
# Screenshot path helpers
# ---------------------------------------------------------------------------


def derive_screenshot_path(url: str, screenshot_dir: str | Path) -> Path:
    """Produce a stable PNG path from a URL + timestamp."""
    parsed = urlparse(url)
    slug_parts = [parsed.netloc.replace(":", "_")] if parsed.netloc else ["local"]
    if parsed.path and parsed.path != "/":
        # strip leading slash, replace separators
        slug_parts.append(parsed.path.strip("/").replace("/", "_"))
    slug = "_".join(slug_parts)[:80] or "page"
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return Path(screenshot_dir) / f"{slug}_{ts}.png"


# ---------------------------------------------------------------------------
# Browser orchestration
# ---------------------------------------------------------------------------


FetchFn = Callable[[str, Optional[Path]], Awaitable[tuple[int | None, str | None, str]]]


async def _fetch_with_playwright(
    url: str, screenshot_path: Optional[Path]
) -> tuple[int | None, str | None, str]:
    """Real Playwright fetch — returns (status_code, title, html)."""
    if not PLAYWRIGHT_AVAILABLE or async_playwright is None:  # pragma: no cover
        raise RuntimeError("playwright_not_installed")
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        try:
            context = await browser.new_context(viewport=DEFAULT_VIEWPORT)
            page = await context.new_page()
            response = await page.goto(url, timeout=DEFAULT_TIMEOUT_MS, wait_until="networkidle")
            status = response.status if response is not None else None
            title = await page.title()
            html = await page.content()
            if screenshot_path is not None:
                screenshot_path.parent.mkdir(parents=True, exist_ok=True)
                await page.screenshot(path=str(screenshot_path), full_page=True)
            return status, title, html
        finally:
            await browser.close()


async def check_landing_url(
    url: str,
    *,
    screenshot_dir: str | Path | None = None,
    require_email_gate: bool = True,
    require_disclaimer: bool = True,
    require_telegram_cta: bool = False,
    expected_ticker: str | None = None,
    fetch_fn: FetchFn | None = None,
) -> BrowserCheckResult:
    """Render `url` in a real browser, assert the conversion-path markers.

    `fetch_fn` is injectable so tests can avoid spinning up Chromium.
    """
    if fetch_fn is None and not PLAYWRIGHT_AVAILABLE:
        return BrowserCheckResult(
            url=url,
            ok=False,
            status_code=None,
            title=None,
            checks={},
            screenshot_path=None,
            error="playwright_not_installed",
        )

    fn: FetchFn = fetch_fn or _fetch_with_playwright

    screenshot_path: Optional[Path] = None
    if screenshot_dir is not None:
        screenshot_path = derive_screenshot_path(url, screenshot_dir)

    try:
        status, title, html = await fn(url, screenshot_path)
    except Exception as exc:
        logger.warning("[browser_qa] fetch failed for %s: %s", url, exc)
        return BrowserCheckResult(
            url=url,
            ok=False,
            status_code=None,
            title=None,
            checks={},
            screenshot_path=None,
            error=f"fetch_failed:{exc}",
        )

    checks = {
        "http_ok": status is not None and 200 <= status < 400,
        "has_title": bool(title and title.strip()),
        "ticker_reference": detect_ticker_reference(html, ticker=expected_ticker),
        "email_gate": detect_email_gate(html),
        "disclaimer": detect_disclaimer(html),
        "telegram_cta": detect_telegram_cta(html),
    }

    required_pass = (
        checks["http_ok"]
        and checks["has_title"]
        and checks["ticker_reference"]
        and (checks["email_gate"] or not require_email_gate)
        and (checks["disclaimer"] or not require_disclaimer)
        and (checks["telegram_cta"] or not require_telegram_cta)
    )

    return BrowserCheckResult(
        url=url,
        ok=required_pass,
        status_code=status,
        title=title,
        checks=checks,
        screenshot_path=str(screenshot_path) if screenshot_path else None,
        error=None,
    )


# ---------------------------------------------------------------------------
# Feishu Content Queue URL extraction
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FeishuCTARow:
    record_id: str
    content_id: str
    ticker: str
    platform: str
    review_status: str
    cta_url: str


def _read_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(
            s.get("text", "") if isinstance(s, dict) else str(s) for s in value
        )
    if isinstance(value, dict):
        return value.get("text", "") or value.get("value", "") or value.get("link", "") or ""
    return str(value)


def _read_url(value: object) -> str:
    if isinstance(value, dict):
        return value.get("link", "") or value.get("text", "") or ""
    if isinstance(value, str):
        return value
    return ""


def extract_cta_rows(
    records: list[dict],
    *,
    statuses: tuple[str, ...] = ("待审核", "已通过", "已发布"),
    limit: int = 10,
) -> list[FeishuCTARow]:
    """Pull (content_id, ticker, platform, cta_url) tuples from Bitable rows.

    Filters by review_status and drops rows where cta_url is missing.
    """
    from . import bitable_fields as bf

    allowed_statuses = tuple(bf.normalize_review_status(status) for status in statuses)
    rows: list[FeishuCTARow] = []
    for record in records:
        fields = bf.normalize_fields(record.get("fields", {}) or {})
        status = bf.normalize_review_status(_read_text(fields.get(bf.REVIEW_STATUS)))
        if statuses and status not in allowed_statuses:
            continue
        cta = _read_url(fields.get(bf.CTA_URL))
        if not cta or not cta.startswith(("http://", "https://")):
            continue
        rows.append(
            FeishuCTARow(
                record_id=record.get("record_id", ""),
                content_id=_read_text(fields.get(bf.CONTENT_ID)),
                ticker=_read_text(fields.get(bf.TICKER)),
                platform=_read_text(fields.get(bf.PLATFORM)),
                review_status=status,
                cta_url=cta,
            )
        )
        if len(rows) >= limit:
            break
    return rows
