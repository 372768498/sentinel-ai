"""Tests for sector_context.compute_sector_context()."""
from __future__ import annotations

import pytest

from app.marketing.sector_context import (
    UNIQUENESS_HIGH,
    UNIQUENESS_MIXED,
    compute_sector_context,
)
from app.marketing.state import SentinelState


def test_no_peers_returns_mixed_with_explanation() -> None:
    sc = compute_sector_context(
        ticker="NVDA", ticker_state=SentinelState.HEATED, peer_states=[]
    )
    assert sc.peer_universe_size == 0
    assert sc.uniqueness_score == 0.5
    assert "unavailable" in sc.interpretation
    assert sc.is_mixed is True


def test_unique_signal_when_no_peers_match() -> None:
    peers = [SentinelState.CALM, SentinelState.CALM, SentinelState.WATCHING, SentinelState.CALM]
    sc = compute_sector_context(
        ticker="NVDA",
        ticker_state=SentinelState.HEATED,
        peer_states=peers,
    )
    assert sc.uniqueness_score == 1.0
    assert sc.is_unique_signal is True
    assert "company-specific" in sc.interpretation


def test_mixed_when_half_peers_match() -> None:
    peers = [SentinelState.HEATED, SentinelState.HEATED, SentinelState.CALM, SentinelState.WATCHING]
    sc = compute_sector_context(
        ticker="NVDA",
        ticker_state=SentinelState.HEATED,
        peer_states=peers,
    )
    assert sc.uniqueness_score == 0.5
    assert sc.is_mixed is True
    assert "Mixed signal" in sc.interpretation


def test_sector_wide_when_most_peers_match() -> None:
    peers = [SentinelState.HEATED] * 8 + [SentinelState.CALM] * 2  # 8/10 same
    sc = compute_sector_context(
        ticker="NVDA",
        ticker_state=SentinelState.HEATED,
        peer_states=peers,
    )
    assert sc.uniqueness_score == pytest.approx(0.2)
    assert sc.is_sector_wide is True
    assert "sector rotation" in sc.interpretation


def test_interpretation_does_not_name_specific_peers() -> None:
    """We never expose individual peer tickers — only counts."""
    peers = [SentinelState.HEATED, SentinelState.HEATED, SentinelState.WATCHING, SentinelState.CALM]
    sc = compute_sector_context(
        ticker="NVDA",
        ticker_state=SentinelState.HEATED,
        peer_states=peers,
    )
    for ban in ("AMD", "INTC", "AVGO", "MU"):  # common semi peers
        assert ban not in sc.interpretation


def test_band_boundaries() -> None:
    """Boundary at 0.8 (unique) and 0.5 (mixed) — exclusive vs inclusive
    matches the constants in module."""
    assert UNIQUENESS_HIGH == 0.8
    assert UNIQUENESS_MIXED == 0.5
