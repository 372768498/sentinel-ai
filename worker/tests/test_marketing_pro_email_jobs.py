"""
Unit tests for the Pro Email Daily Intelligence Report orchestrator.

We bypass the live DB / Resend / yfinance pipeline by injecting
fakes through send_pro_email_digest's keyword-argument seams
(audience_fetcher / payload_builder / resend_sender). This keeps
the test hermetic — runs in <100ms.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from app.marketing import pro_email_jobs
from app.marketing.pro_email_jobs import (
    ProAudienceRow,
    send_pro_email_digest,
)
from app.marketing.templates.pro_email import (
    DimensionRow,
    ProEmailDailyPayload,
    WatchlistMover,
)


def _run(coro):
    return asyncio.run(coro)


def _audience_row(email="pro@example.com", user_id="u1",
                  tier="pro", tg_id=10001):
    return ProAudienceRow(
        user_id=user_id, email=email, pro_tier=tier,
        telegram_user_id=tg_id,
    )


def _payload(top_ticker="NVDA"):
    return ProEmailDailyPayload(
        subject_line=f"${top_ticker} test",
        preview_line="Preview line",
        date_long="Wed May 13, 2026",
        delivery_time_et="09:30",
        watchlist_tickers_line="NVDA · AMD",
        top_ticker=top_ticker,
        top_price=245.50,
        top_change_pct=3.80,
        top_session="pre-market",
        top_relative_volume=1.8,
        top_prev_close=236.50,
        top_score=67, top_rating="Buy", top_score_change=3,
        why_moving="EPS beat 5.2%",
        risk_flag="Premium valuation",
        dimensions=[DimensionRow("Earnings surprise", 7.0, "EPS surprise +5.2%")],
        peer_tickers=["AMD", "INTC"],
        peer_check_lines=["AMD has stronger attention"],
        watchlist_movers=[
            WatchlistMover(top_ticker, "📈", 3.80, 67, "Buy", 3),
        ],
        top_report_url="https://sentinelai.com/stocks/NVDA",
        manage_url="https://app.jilo.ai/account",
        methodology_url="https://app.jilo.ai/methodology",
    )


# ── Audience resolution ───────────────────────────────────────────────────────


def test_send_returns_no_op_when_no_audience() -> None:
    audience_fetcher = AsyncMock(return_value=[])
    sender = AsyncMock(return_value=None)
    result = _run(send_pro_email_digest(
        live=False,
        audience_fetcher=audience_fetcher,
        resend_sender=sender,
        conn=object(),  # any non-None so we skip the own_conn path
    ))
    assert result["session"] == "pro_email_daily"
    assert result["leads_queried"] == 0
    assert result["sent"] == 0
    sender.assert_not_called()


def test_send_refuses_bulk_live_without_allow_bulk() -> None:
    audience_fetcher = AsyncMock(return_value=[_audience_row()])
    sender = AsyncMock(return_value=None)
    result = _run(send_pro_email_digest(
        live=True,
        allow_bulk=False,
        only_email=None,
        audience_fetcher=audience_fetcher,
        resend_sender=sender,
        conn=object(),
    ))
    assert result["mode"] == "live"
    assert result["sent"] == 0
    assert any("bulk live send refused" in e for e in result["errors"])
    sender.assert_not_called()
    audience_fetcher.assert_not_called()


# ── Dry-run path ──────────────────────────────────────────────────────────────


def test_dry_run_renders_but_does_not_send() -> None:
    audience_fetcher = AsyncMock(return_value=[_audience_row()])
    builder = AsyncMock(return_value=_payload())
    sender = AsyncMock(return_value=None)
    result = _run(send_pro_email_digest(
        live=False,
        audience_fetcher=audience_fetcher,
        payload_builder=builder,
        resend_sender=sender,
        conn=object(),
    ))
    assert result["mode"] == "dry-run"
    assert result["leads_queried"] == 1
    assert result["sent"] == 1
    assert result["renders"][0]["status"] == "dry-run"
    assert result["renders"][0]["top"] == "NVDA"
    # Resend sender was called with dry_run=True
    sender.assert_awaited_once()
    assert sender.await_args.kwargs["dry_run"] is True


def test_live_only_email_sends_once() -> None:
    single_fetcher = AsyncMock(return_value=_audience_row("vip@example.com"))
    builder = AsyncMock(return_value=_payload("AMD"))
    sender = AsyncMock(return_value="resend-id-123")
    result = _run(send_pro_email_digest(
        live=True,
        only_email="vip@example.com",
        single_audience_fetcher=single_fetcher,
        payload_builder=builder,
        resend_sender=sender,
        conn=object(),
    ))
    assert result["mode"] == "live"
    assert result["sent"] == 1
    assert result["renders"][0]["status"] == "sent"
    assert result["renders"][0]["top"] == "AMD"
    assert sender.await_args.kwargs["dry_run"] is False
    assert sender.await_args.kwargs["to_email"] == "vip@example.com"


def test_skips_users_without_movers() -> None:
    audience_fetcher = AsyncMock(return_value=[
        _audience_row("a@example.com"),
        _audience_row("b@example.com"),
    ])
    builder = AsyncMock(side_effect=[_payload("NVDA"), None])
    sender = AsyncMock(return_value=None)
    result = _run(send_pro_email_digest(
        live=False,
        audience_fetcher=audience_fetcher,
        payload_builder=builder,
        resend_sender=sender,
        conn=object(),
    ))
    assert result["leads_queried"] == 2
    # Only one was actually rendered+sent
    statuses = [r["status"] for r in result["renders"]]
    assert statuses == ["dry-run", "skipped"]


def test_swallows_build_exception() -> None:
    audience_fetcher = AsyncMock(return_value=[
        _audience_row("a@example.com"),
        _audience_row("b@example.com"),
    ])

    async def maybe_raise(*args, **kwargs):
        if kwargs["audience"].email == "a@example.com":
            raise RuntimeError("yfinance hiccup")
        return _payload("AMD")

    builder = AsyncMock(side_effect=maybe_raise)
    sender = AsyncMock(return_value=None)
    result = _run(send_pro_email_digest(
        live=False,
        audience_fetcher=audience_fetcher,
        payload_builder=builder,
        resend_sender=sender,
        conn=object(),
    ))
    assert result["leads_queried"] == 2
    assert any("build(a@example.com)" in e for e in result["errors"])
    # The other user still went through
    assert any(r.get("status") == "dry-run" for r in result["renders"])


def test_sender_exception_logged_in_errors_and_render() -> None:
    audience_fetcher = AsyncMock(return_value=[_audience_row()])
    builder = AsyncMock(return_value=_payload())
    sender = AsyncMock(side_effect=RuntimeError("resend 500"))
    result = _run(send_pro_email_digest(
        live=True,
        only_email="pro@example.com",
        single_audience_fetcher=AsyncMock(return_value=_audience_row()),
        payload_builder=builder,
        resend_sender=sender,
        conn=object(),
    ))
    assert any("send(pro@example.com)" in e for e in result["errors"])
    assert any(r["status"] == "error" for r in result["renders"])


# ── _split_subject_preview helper ─────────────────────────────────────────────


def test_split_subject_preview_strips_headers() -> None:
    rendered = (
        "Subject: NVDA +3.8%\n"
        "Preview: Quick look\n"
        "\n"
        "Body content here\n"
        "More body\n"
    )
    subject, preview, body = pro_email_jobs._split_subject_preview(rendered)
    assert subject == "NVDA +3.8%"
    assert preview == "Quick look"
    assert body.startswith("Body content here")
    # Headers are NOT in body
    assert "Subject:" not in body
    assert "Preview:" not in body


# ── Component → dimension normalization ───────────────────────────────────────


def test_component_to_dimension_clamps_and_scales() -> None:
    # score=0.7 → 7.0/10
    row = pro_email_jobs._component_to_dimension(
        "fundamentals", {"score": 0.7, "roe": 0.27, "free_cashflow": 19e9},
    )
    assert row is not None
    assert row.score_10 == pytest.approx(7.0, abs=0.01)
    assert row.label == "Fundamentals"
    assert "ROE 27%" in row.highlight


def test_component_to_dimension_clamps_negative_to_zero() -> None:
    row = pro_email_jobs._component_to_dimension(
        "sentiment_analysis", {"score": -0.15},
    )
    assert row is not None
    assert row.score_10 == 0.0


def test_component_to_dimension_returns_none_when_no_score() -> None:
    row = pro_email_jobs._component_to_dimension("technical", {})
    assert row is None


def test_build_dimensions_preserves_display_order_and_drops_unknowns() -> None:
    components = {
        "fundamentals": {"score": 0.6, "roe": 0.27},
        "earnings_surprise": {"score": 0.7, "surprise_pct": 5.2},
        "what_even": {"score": 0.5},  # unknown key — dropped
    }
    rows = pro_email_jobs._build_dimensions(components)
    labels = [r.label for r in rows]
    # Order: fundamentals before earnings_surprise (per display order)
    assert labels[0] == "Fundamentals"
    assert labels[1] == "Earnings surprise"
    # Unknown key not present
    assert all("what_even" not in lbl.lower() for lbl in labels)


def test_build_peer_check_lines_renders_known_keys() -> None:
    components = {
        "peer_comparison": {
            "peer_tickers": ["AMD", "INTC"],
            "comparisons": {
                "pe": {"premium_pct": 44.0},
                "revenue_growth": {"premium_pct": -12.0},
            },
        },
    }
    lines = pro_email_jobs._build_peer_check_lines(components, "NVDA")
    assert any("P/E ratio: 44%" in l and "premium" in l for l in lines)
    assert any("Revenue growth: 12%" in l and "discount" in l for l in lines)


def test_build_peer_check_lines_empty_when_no_comparisons() -> None:
    assert pro_email_jobs._build_peer_check_lines({}, "NVDA") == []
    assert pro_email_jobs._build_peer_check_lines(
        {"peer_comparison": {}}, "NVDA",
    ) == []
