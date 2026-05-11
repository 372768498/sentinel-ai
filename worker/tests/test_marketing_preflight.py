"""Preflight checks: do we have what we need to flip live?

These tests are advisory — they SKIP rather than FAIL when creds are missing,
so CI stays green. They are designed to be run by a human operator before
flipping X_DRY_RUN=false.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

WORKER_DIR = Path(__file__).resolve().parents[1]
COOKIE_PATH = WORKER_DIR / "data" / "x-cookies.json"


def test_module_imports_clean():
    from app.marketing import (
        Composer,
        Publisher,
        XClient,
        score_from_move,
        publish_marketing_alerts,
    )
    assert callable(score_from_move)
    assert callable(publish_marketing_alerts)


def test_anthropic_key_present():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY not set — composer will run in Mock Mode")
    assert os.environ["ANTHROPIC_API_KEY"].startswith("sk-ant-")


def test_x_cookie_present():
    if not COOKIE_PATH.exists():
        pytest.skip(
            f"X cookie missing at {COOKIE_PATH} — run scripts/x_login.py first"
        )
    assert COOKIE_PATH.stat().st_size > 0


def test_bot_regex_aligned_with_tracker():
    """Sanity that production deep-links will be parseable by the bot."""
    from datetime import date
    from app.bot.handlers.onboarding import START_PAYLOAD_RE
    from app.marketing.tracker import build_payload

    payload = build_payload(
        source="xtw", score=92, ticker="AAPL", day=date(2026, 5, 9)
    )
    match = START_PAYLOAD_RE.match(payload)
    assert match is not None, f"bot regex won't parse {payload!r}"
    assert match.group("source") == "xtw"


def test_marketing_env_flags_documented():
    """Sanity check that operators see ENV_MATRIX hints for marketing flags."""
    docs = (WORKER_DIR.parent / "docs" / "ENV_MATRIX.md").read_text(encoding="utf-8")
    for flag in ("MARKETING_ENABLED", "X_DRY_RUN", "ANTHROPIC_API_KEY"):
        assert flag in docs, f"{flag} not documented in docs/ENV_MATRIX.md"


def test_default_threshold_is_safe():
    """Default threshold must be conservative — quiet days post nothing."""
    from app.marketing.jobs import DEFAULT_THRESHOLD
    assert DEFAULT_THRESHOLD >= 80, "Default gate too low — would post on noise"


def test_dry_run_is_default():
    """Belt-and-suspenders: a fresh XClient with no env hints stays in dry-run."""
    from app.marketing import XClient
    # ensure env flag not bleeding in from outer shell
    original = os.environ.pop("X_DRY_RUN", None)
    try:
        client = XClient()
        assert client.dry_run is True
    finally:
        if original is not None:
            os.environ["X_DRY_RUN"] = original
