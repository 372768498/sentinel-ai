"""
Unit tests for the scoring subprocess wrapper.

We mock `asyncio.create_subprocess_exec` so the tests stay hermetic — no
actual xiangyu run, no yfinance network call, no python subprocess spawn.
"""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.scoring.engine import (
    ScoreSnapshot,
    rating_label_for,
    score_one,
    score_watchlist,
)


def _run(coro):
    return asyncio.run(coro)


# ── rating_label_for: pure-function table tests ───────────────────────────────


@pytest.mark.parametrize("score,label", [
    (95, "Strong Buy"),
    (80, "Strong Buy"),
    (79, "Buy"),
    (65, "Buy"),
    (64, "Hold"),
    (50, "Hold"),
    (49, "Reduce"),
    (35, "Reduce"),
    (34, "Sell"),
    (0, "Sell"),
    (-5, "Sell"),
])
def test_rating_label_for_band_boundaries(score: int, label: str) -> None:
    assert rating_label_for(score) == label


# ── score_one: subprocess mock harness ────────────────────────────────────────


def _make_proc_mock(*, stdout: bytes, stderr: bytes = b"", returncode: int = 0):
    """Build an asyncio subprocess-shaped mock."""
    proc = MagicMock()
    proc.returncode = returncode
    proc.communicate = AsyncMock(return_value=(stdout, stderr))
    proc.kill = MagicMock()
    proc.wait = AsyncMock(return_value=None)
    return proc


_GOOD_PAYLOAD = {
    "ticker": "NVDA",
    "score_100": 67,
    "rating": "Constructive",
    "recommendation": "CONSTRUCTIVE",
    "state": "Constructive",
    "confidence": 0.85,
    "supporting_points": ["EPS surprise +5%", "Analyst Buy"],
    "caveats": ["Short delay 2w"],
    "components": {
        "earnings_surprise": {"score": 0.7, "surprise_pct": 5.2},
    },
    "timestamp": "2026-05-13T08:00:00",
}


def test_score_one_parses_valid_payload() -> None:
    proc = _make_proc_mock(stdout=json.dumps(_GOOD_PAYLOAD).encode())
    with patch(
        "app.scoring.engine.asyncio.create_subprocess_exec",
        AsyncMock(return_value=proc),
    ):
        result = _run(score_one("NVDA"))

    assert result is not None
    assert isinstance(result, ScoreSnapshot)
    assert result.ticker == "NVDA"
    assert result.score_100 == 67
    # rating is locally re-derived from score_100, not xiangyu's CN label
    assert result.rating == "Buy"
    assert result.recommendation == "CONSTRUCTIVE"
    assert result.confidence == 0.85
    assert result.supporting_points == ["EPS surprise +5%", "Analyst Buy"]
    assert result.caveats == ["Short delay 2w"]
    assert "earnings_surprise" in result.components


def test_score_one_returns_none_on_nonzero_exit() -> None:
    proc = _make_proc_mock(stdout=b"", stderr=b"boom", returncode=2)
    with patch(
        "app.scoring.engine.asyncio.create_subprocess_exec",
        AsyncMock(return_value=proc),
    ):
        result = _run(score_one("NVDA"))
    assert result is None


def test_score_one_returns_none_on_invalid_json() -> None:
    proc = _make_proc_mock(stdout=b"not json at all")
    with patch(
        "app.scoring.engine.asyncio.create_subprocess_exec",
        AsyncMock(return_value=proc),
    ):
        result = _run(score_one("NVDA"))
    assert result is None


def test_score_one_returns_none_on_missing_required_field() -> None:
    bad = {k: v for k, v in _GOOD_PAYLOAD.items() if k != "score_100"}
    proc = _make_proc_mock(stdout=json.dumps(bad).encode())
    with patch(
        "app.scoring.engine.asyncio.create_subprocess_exec",
        AsyncMock(return_value=proc),
    ):
        result = _run(score_one("NVDA"))
    assert result is None


def test_score_one_returns_none_on_timeout() -> None:
    proc = MagicMock()
    proc.returncode = None
    proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError())
    proc.kill = MagicMock()
    proc.wait = AsyncMock(return_value=None)

    with patch(
        "app.scoring.engine.asyncio.create_subprocess_exec",
        AsyncMock(return_value=proc),
    ):
        result = _run(score_one("NVDA"))
    assert result is None
    proc.kill.assert_called_once()


def test_score_watchlist_drops_failed_tickers() -> None:
    # First ticker succeeds, second fails (non-zero exit), third succeeds.
    payload2 = {**_GOOD_PAYLOAD, "ticker": "AAPL", "score_100": 55}
    seq = [
        _make_proc_mock(stdout=json.dumps(_GOOD_PAYLOAD).encode()),
        _make_proc_mock(stdout=b"", stderr=b"err", returncode=1),
        _make_proc_mock(stdout=json.dumps(payload2).encode()),
    ]
    seq_iter = iter(seq)

    async def fake_exec(*args, **kwargs):
        return next(seq_iter)

    with patch(
        "app.scoring.engine.asyncio.create_subprocess_exec",
        side_effect=fake_exec,
    ):
        results = _run(score_watchlist(["NVDA", "FAIL", "AAPL"]))

    assert len(results) == 2
    tickers = {r.ticker for r in results}
    assert tickers == {"NVDA", "AAPL"}
