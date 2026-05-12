"""Tests for tier_gating.can_user_see / watchlist_limit_for_tier."""
from __future__ import annotations

import pytest

from app.marketing.tier_gating import (
    TIER_DESK,
    TIER_FREE,
    TIER_PRO,
    TIER_WATCH,
    can_user_see,
    watchlist_limit_for_tier,
)


# ---- can_user_see --------------------------------------------------------


def test_free_user_sees_no_gated_features() -> None:
    for feat in (
        "watchlist_basic",
        "divergence_compass",
        "sector_context",
        "weekly_digest",
    ):
        assert can_user_see(TIER_FREE, feat) is False
        assert can_user_see(None, feat) is False  # null == free


def test_watch_tier_basics() -> None:
    assert can_user_see(TIER_WATCH, "watchlist_basic") is True
    assert can_user_see(TIER_WATCH, "state_alerts") is True
    assert can_user_see(TIER_WATCH, "quiet_hours") is True
    # Watch does NOT get pro-only features
    assert can_user_see(TIER_WATCH, "divergence_compass") is False
    assert can_user_see(TIER_WATCH, "weekly_digest") is False


def test_pro_inherits_watch_features() -> None:
    for feat in ("watchlist_basic", "state_alerts", "quiet_hours"):
        assert can_user_see(TIER_PRO, feat) is True


def test_pro_unlocks_pro_only() -> None:
    for feat in (
        "divergence_compass",
        "sector_context",
        "weekly_digest",
        "honest_miss_log",
        "custom_notification_mode",
        "pdf_export",
        "share_cards",
        "pre_earnings_smart_muting",
        "priority_email_reply",
    ):
        assert can_user_see(TIER_PRO, feat) is True


def test_desk_inherits_pro_and_watch() -> None:
    for feat in ("watchlist_basic", "divergence_compass", "pdf_export"):
        assert can_user_see(TIER_DESK, feat) is True


def test_desk_unlocks_desk_only() -> None:
    assert can_user_see(TIER_DESK, "deck_analyst_briefings") is True
    assert can_user_see(TIER_DESK, "private_telegram_channel") is True


def test_unknown_feature_always_false() -> None:
    for tier in (TIER_FREE, TIER_WATCH, TIER_PRO, TIER_DESK):
        assert can_user_see(tier, "feature_that_does_not_exist") is False


def test_unknown_tier_treated_as_free() -> None:
    assert can_user_see("enterprise", "watchlist_basic") is False
    assert can_user_see("invalid-tier", "divergence_compass") is False


def test_tier_string_case_insensitive() -> None:
    # Uppercase tier string still gates correctly
    assert can_user_see("PRO", "divergence_compass") is True
    assert can_user_see("Watch", "watchlist_basic") is True


# ---- watchlist_limit_for_tier -------------------------------------------


def test_watchlist_limits() -> None:
    assert watchlist_limit_for_tier(None) == 0
    assert watchlist_limit_for_tier(TIER_FREE) == 0
    assert watchlist_limit_for_tier(TIER_WATCH) == 5
    assert watchlist_limit_for_tier(TIER_PRO) == 15
    assert watchlist_limit_for_tier(TIER_DESK) == 50


def test_unknown_tier_limit_zero() -> None:
    assert watchlist_limit_for_tier("enterprise") == 0
