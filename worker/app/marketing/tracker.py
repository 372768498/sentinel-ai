"""Deep-link payload builder for Telegram bot acquisition attribution.

Format: src_{source}_score{N}_{ticker}_{YYYYMMDD}
Example: src_xtw_score92_aapl_20260509

Aligned with worker/app/bot/handlers/onboarding.py START_PAYLOAD_RE so the
bot writes signup_source / signup_campaign / signup_ticker correctly.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Optional

# Mirrors START_PAYLOAD_RE in worker/app/bot/handlers/onboarding.py.
PAYLOAD_PATTERN = re.compile(
    r"^(?:src_)?([a-z][a-z0-9]{0,8})_score(\d{1,3})_([a-z]{1,5})_(\d{8})$"
)
SAFE_TICKER_CHARS = re.compile(r"[^a-z]")


def build_payload(
    *,
    source: str,
    score: int,
    ticker: str,
    day: Optional[date] = None,
) -> str:
    day = day or date.today()
    source_clean = source.lower()
    if not re.fullmatch(r"[a-z][a-z0-9]{0,8}", source_clean):
        raise ValueError(f"source must match /^[a-z][a-z0-9]{{0,8}}$/: {source!r}")
    if not 0 <= score <= 100:
        raise ValueError(f"score out of range 0-100: {score}")
    ticker_clean = SAFE_TICKER_CHARS.sub("", ticker.lower())[:5]
    if not ticker_clean:
        raise ValueError(f"ticker has no alpha chars: {ticker!r}")
    payload = f"src_{source_clean}_score{score}_{ticker_clean}_{day:%Y%m%d}"
    if len(payload) > 64:
        raise ValueError(f"payload exceeds Telegram 64-char limit: {payload}")
    return payload


def build_deep_link(bot_username: str, payload: str) -> str:
    bot_username = bot_username.lstrip("@")
    return f"https://t.me/{bot_username}?start={payload}"


def parse_payload(payload: str) -> Optional[dict]:
    """Inverse of build_payload. Returns None if the payload is malformed."""
    match = PAYLOAD_PATTERN.match(payload.lower())
    if match is None:
        return None
    source, score_str, ticker, day_str = match.groups()
    return {
        "source": source,
        "score": int(score_str),
        "ticker": ticker.upper(),
        "day": day_str,
    }
