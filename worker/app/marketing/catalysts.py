"""SEC EDGAR catalyst lookup — turns a ticker into a real primary-source URL.

Used by jobs.py to replace the Yahoo-Finance placeholder with an 8-K / 10-Q
homepage URL plus a redline-safe headline.

Fail-soft: if EDGAR is unreachable or the ticker has no recent filing, we
return None and the caller falls back to the issuer-IR page.
"""
from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_LOOKBACK_DAYS = 21
DEFAULT_FORMS_PRIORITY = ("8-K", "10-Q", "10-K")

_FORM_HEADLINE = {
    "8-K": "filed an 8-K disclosure",
    "10-Q": "filed its latest 10-Q quarterly report",
    "10-K": "filed its latest 10-K annual report",
    "S-1": "filed an S-1 registration",
    "13D": "filed a 13D ownership disclosure",
}

_identity_set = False


@dataclass(frozen=True)
class Catalyst:
    ticker: str
    form: str
    filing_date: date
    accession_no: str
    homepage_url: str
    primary_doc_url: Optional[str]

    def headline(self) -> str:
        verb = _FORM_HEADLINE.get(self.form, f"filed a {self.form}")
        # Cross-platform date formatting: "9 May" without leading zero
        if hasattr(self.filing_date, "strftime"):
            day = self.filing_date.day
            month = self.filing_date.strftime("%b")
            return f"{verb} on {day} {month}"
        return f"{verb} on {self.filing_date}"


def _ensure_identity() -> None:
    global _identity_set
    if _identity_set:
        return
    from edgar import set_identity

    identity = os.environ.get("SEC_USER_AGENT", "").strip()
    if not identity:
        identity = "Sentinel AI ops@sentinel.local"
    set_identity(identity)
    _identity_set = True


def _fetch_latest_sync(
    ticker: str,
    forms: tuple[str, ...],
    lookback_days: int,
) -> Optional[Catalyst]:
    from edgar import Company

    _ensure_identity()
    cutoff = (date.today() - timedelta(days=lookback_days)).isoformat()

    try:
        company = Company(ticker)
    except Exception as exc:
        logger.info("EDGAR Company(%s) lookup failed: %s", ticker, exc)
        return None

    for form in forms:
        try:
            filings = company.get_filings(form=form, date=f"{cutoff}:").head(1)
        except Exception as exc:
            logger.info("EDGAR get_filings(%s, %s) failed: %s", ticker, form, exc)
            continue
        if filings is None or len(filings) == 0:
            continue
        try:
            entry = filings[0]
        except Exception:
            continue
        homepage = getattr(entry, "homepage_url", None) or ""
        if not homepage:
            continue
        return Catalyst(
            ticker=ticker.upper(),
            form=str(entry.form),
            filing_date=entry.filing_date,
            accession_no=str(entry.accession_no),
            homepage_url=homepage,
            primary_doc_url=getattr(entry, "filing_url", None),
        )

    return None


async def latest_catalyst(
    ticker: str,
    *,
    forms: tuple[str, ...] = DEFAULT_FORMS_PRIORITY,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    timeout_s: float = 8.0,
) -> Optional[Catalyst]:
    loop = asyncio.get_running_loop()
    try:
        return await asyncio.wait_for(
            loop.run_in_executor(None, _fetch_latest_sync, ticker, forms, lookback_days),
            timeout=timeout_s,
        )
    except asyncio.TimeoutError:
        logger.info("EDGAR lookup for %s timed out after %.1fs", ticker, timeout_s)
        return None
    except Exception as exc:
        logger.warning("EDGAR lookup for %s errored: %s", ticker, exc)
        return None


def fallback_source(ticker: str) -> str:
    """Issuer IR page guess when EDGAR has nothing recent. Domain-known mapping."""
    return f"https://finance.yahoo.com/quote/{ticker}/news"
