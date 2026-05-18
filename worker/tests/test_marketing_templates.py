"""Tests for all Sprint 2 content templates.

Each template's contract:
  - Renders deterministically from a payload dataclass
  - Output contains the state's display label or emoji
  - Output ends with a disclaimer phrase
  - Output never contains 'score' / 'rating' / 'X/100' (Sprint 2 redline)
  - 'Nothing unusual' branch is reachable and produces sensible text
"""
from __future__ import annotations

import re

import pytest

from app.marketing.state import SentinelState
from app.marketing.templates import (
    free_email,
    free_telegram,
    pro_email,
    pro_telegram,
    x_hook,
)


FORBIDDEN_WORDS_RE = re.compile(
    r"\b(score|rating|\d{1,3}\s*/\s*100|out\s+of\s+(?:100|ten|10))\b",
    re.IGNORECASE,
)


def _assert_no_score_language(text: str) -> None:
    m = FORBIDDEN_WORDS_RE.search(text)
    assert m is None, f"forbidden word found: {m.group(0)!r}"


# ============================================================
# free_telegram
# ============================================================


def _free_tg_anomaly() -> free_telegram.AnomalyPayload:
    return free_telegram.AnomalyPayload(
        session_label="Pre-market",
        timestamp_et="08:30",
        state=SentinelState.HEATED,
        ticker="NVDA",
        price=987.65,
        session_change_label="Pre-market",
        price_change_pct=2.4,
        volume_relative=2.1,
        anomaly_one_liner="3 catalysts in 48h, social mentions doubled.",
        uniqueness_line="Only 2 of 10 sector peers show the same pattern.",
        confirming_list="market volume, social buzz, news flow",
        disagreeing_list="competitor peers, institutional flows",
        narrative_one_paragraph="Multiple confirming signals overlap.",
        risk_one_liner="Pattern can reverse fast.",
        source_categories="FMP, SEC, X SERP",
        cta_url="https://app.jilo.ai/stocks/NVDA",
        pro_url="https://app.jilo.ai/pro",
    )


def test_free_tg_anomaly_renders_with_state_emoji() -> None:
    out = free_telegram.render_anomaly(_free_tg_anomaly())
    assert "🟠" in out  # HEATED emoji
    assert "$NVDA" in out
    assert "Not financial advice" in out
    _assert_no_score_language(out)


def test_free_tg_nothing_branch_renders() -> None:
    out = free_telegram.render_nothing(
        free_telegram.NothingPayload(
            session_label="Pre-market",
            timestamp_et="08:30",
            scan_universe_size=7400,
        )
    )
    assert "nothing unusual" in out.lower()
    assert "7400" in out
    assert "see you tomorrow" in out.lower()
    _assert_no_score_language(out)


# ============================================================
# free_email
# ============================================================


def test_free_email_seed_section_with_three_states() -> None:
    seeds = [
        free_email.SeedTicker(ticker="NVDA", state=SentinelState.HEATED, one_liner="multi-signal firing"),
        free_email.SeedTicker(ticker="AMD", state=SentinelState.WATCHING, one_liner="narrative ahead of filings"),
        free_email.SeedTicker(ticker="MSFT", state=SentinelState.CALM, one_liner="no signal today"),
    ]
    section = free_email.render_seed_section(seeds)
    assert "NVDA" in section and "AMD" in section and "MSFT" in section
    assert "Heated" in section and "Watching" in section and "Calm" in section
    assert "Try Pro Watch" in section


def test_free_email_seed_section_empty_when_no_seeds() -> None:
    assert free_email.render_seed_section([]) == ""


def test_free_email_reflection_rotates_deterministically() -> None:
    q0 = free_email.pick_reflection_question(day_offset=0)
    q1 = free_email.pick_reflection_question(day_offset=1)
    q_loop = free_email.pick_reflection_question(
        day_offset=len(free_email.REFLECTION_QUESTIONS)
    )
    assert q0 != q1
    assert q0 == q_loop  # rotates cyclically


def test_free_email_anomaly_render() -> None:
    payload = free_email.AnomalyEmailPayload(
        subject_line="$NVDA: multi-signal anomaly",
        preview_line="Volume + social + news all firing.",
        date_long="Monday, May 12 2026",
        timestamp_et="07:00",
        state=SentinelState.INFLECTION,
        ticker="NVDA",
        price=987.65,
        price_change_pct=4.2,
        session_label="pre-market",
        setup_bullets="- 2.5x avg volume\n- 3 catalysts in 48h",
        matters_paragraph="When volume and filings and chatter align...",
        confirming_count=5,
        disagreeing_count=1,
        source_links_list="SEC EDGAR, FMP, X",
        cta_url="https://app.jilo.ai/stocks/NVDA",
        seed_section="",
        reflection_question=free_email.REFLECTION_QUESTIONS[0],
        pro_url="https://app.jilo.ai/pro",
        methodology_url="https://app.jilo.ai/method",
        unsubscribe_url="https://app.jilo.ai/u/abc",
    )
    out = free_email.render_anomaly_email(payload)
    assert "🔴" in out
    assert "$NVDA" in out
    assert "not financial advice" in out.lower()
    _assert_no_score_language(out)


def test_free_email_nothing_render() -> None:
    out = free_email.render_nothing_email(
        free_email.NothingEmailPayload(
            date_long="Mon May 12 2026",
            timestamp_et="07:00",
            scan_universe_size=7400,
            seed_section="",
            pro_url="https://app.jilo.ai/pro",
        )
    )
    assert "nothing unusual" in out.lower()
    _assert_no_score_language(out)


def test_free_email_html_preserves_core_text_and_links() -> None:
    body = """\
-------------------------
TODAY'S WATCHLIST PRIORITY

🟠 $NVDA - $150.0 - +3.2% intraday

Bottom line:
Something changed enough for Sentinel to move this ticker to the top.

WHY SENTINEL FLAGGED IT

- 2.5x avg volume
- 3 catalysts in 48h

YOUR WATCHLIST PRIORITY

  NVDA: 🟠 Heated - multi-signal firing
  MSFT: 🟢 Calm - no signal today

[ Open stock context preview -> https://sentinelai.com/stocks/NVDA ]
Methodology + sources: https://sentinelai.com/methodology
"""

    html = free_email.render_email_html(
        subject="$NVDA: multi-signal anomaly",
        preview="Volume + social + news all firing.",
        body_text=body,
    )

    for expected in (
        "$NVDA",
        "+3.2% intraday",
        "Something changed enough for Sentinel",
        "2.5x avg volume",
        "3 catalysts in 48h",
        "NVDA",
        "MSFT",
        "multi-signal firing",
        "https://sentinelai.com/stocks/NVDA",
        "https://sentinelai.com/methodology",
    ):
        assert expected in html


# ============================================================
# pro_telegram
# ============================================================


def test_pro_tg_compass_renders_filled_and_open_dots() -> None:
    top, bot = pro_telegram.render_compass(
        confirming=[
            pro_telegram.CompassSignal("volume", 0.9),
            pro_telegram.CompassSignal("social", 0.5),
        ],
        disagreeing=[pro_telegram.CompassSignal("peers", 0.8)],
    )
    assert "●" in top  # 0.9 > 0.7
    assert "○" in top  # 0.5 < 0.7
    assert "●" in bot
    assert "volume" in top and "social" in top
    assert "peers" in bot


def test_pro_tg_compass_caps_at_max_per_side() -> None:
    sigs = [pro_telegram.CompassSignal(f"s{i}", 0.5) for i in range(6)]
    top, _ = pro_telegram.render_compass(confirming=sigs, disagreeing=[], max_per_side=3)
    # Only 3 lines on top
    assert top.count("\n") == 2  # 3 lines


def test_pro_tg_divergence_warning_empty_below_threshold() -> None:
    assert pro_telegram.render_divergence_warning(0.49) == ""


def test_pro_tg_divergence_warning_present_at_threshold() -> None:
    w = pro_telegram.render_divergence_warning(0.5)
    assert "Divergence" in w
    assert "high-conviction" in w.lower() or "position sizing" in w.lower()


def test_pro_tg_alert_renders_with_state_transition() -> None:
    p = pro_telegram.ProAlertPayload(
        timestamp_et="09:15",
        user_first_name="Alex",
        ticker="NVDA",
        prev_state=SentinelState.WATCHING,
        new_state=SentinelState.HEATED,
        minutes_since_change=3,
        price=987.65,
        price_change_pct=2.4,
        session_label="intraday",
        volume_relative=2.1,
        change_bullets="- New 8-K filed at 09:02\n- Social mentions doubled",
        compass_top="   volume → ●",
        compass_bottom="   peers → ○",
        synthesis_paragraph="Confirming signals stacking.",
        divergence_warning="",
        pro_report_url="https://app.jilo.ai/pro/NVDA",
    )
    out = pro_telegram.render_alert(p)
    assert "Alex" in out
    assert "$NVDA" in out
    assert "🟡" in out and "🟠" in out  # both states' emojis
    assert "/why NVDA" in out
    assert "Not financial advice" in out
    _assert_no_score_language(out)


# ============================================================
# pro_email
# ============================================================


def _pro_email_minimal_payload(**overrides) -> "pro_email.ProEmailDailyPayload":
    """Build a payload with defaults, override per-test."""
    defaults = dict(
        subject_line="NVDA +3.8% pre-market — Sentinel score 67",
        preview_line="Watchlist signal pulled forward today",
        date_long="Wed May 13, 2026",
        delivery_time_et="09:30",
        watchlist_tickers_line="NVDA · AMD · TSLA · MSFT · GOOGL",
        top_ticker="NVDA",
        top_price=245.50,
        top_change_pct=3.80,
        top_session="pre-market",
        top_relative_volume=1.8,
        top_prev_close=236.50,
        top_score=67,
        top_rating="Buy",
        top_score_change=3,
        why_moving="EPS beat 5.2%; analyst upgrades push targets higher.",
        risk_flag="Trading at peer P/E premium",
        dimensions=[
            pro_email.DimensionRow("Earnings surprise", 7.0, "EPS surprise +5.2%"),
            pro_email.DimensionRow("Fundamentals", 6.5, "ROE 27% · FCF $19B"),
            pro_email.DimensionRow("Analyst consensus", 9.0, "Buy · +14% upside"),
        ],
        peer_tickers=["AMD", "INTC", "AVGO", "QCOM", "TSM"],
        peer_check_lines=[
            "AMD has stronger attention acceleration",
            "NVDA has stronger profitability",
        ],
        watchlist_movers=[
            pro_email.WatchlistMover(
                ticker="NVDA", state_emoji="📈", change_pct=3.80,
                score_100=67, rating="Buy", score_change=3,
            ),
            pro_email.WatchlistMover(
                ticker="TSLA", state_emoji="📉", change_pct=-2.40,
                score_100=52, rating="Hold", score_change=-2,
            ),
        ],
        top_report_url="https://sentinelai.com/stocks/NVDA",
        manage_url="https://app.jilo.ai/account",
        methodology_url="https://app.jilo.ai/methodology",
    )
    defaults.update(overrides)
    return pro_email.ProEmailDailyPayload(**defaults)


def test_pro_email_render_carries_score_and_narrative() -> None:
    out = pro_email.render_email(_pro_email_minimal_payload())
    assert "SENTINEL PRO" in out
    assert "67/100" in out
    assert "Buy (+3 vs prev)" in out
    assert "Why it's moving" in out
    assert "EPS beat 5.2%" in out
    assert "Risk flag" in out
    assert "Trading at peer P/E premium" in out
    assert "Context, not financial advice." in out


def test_pro_email_render_handles_missing_score_gracefully() -> None:
    out = pro_email.render_email(_pro_email_minimal_payload(
        top_score=None, top_rating=None, top_score_change=None,
        why_moving=None, risk_flag=None,
    ))
    # No crash; falls back to placeholder text
    assert "not yet computed" in out
    assert "narrative not yet generated" in out


def test_pro_email_dim_snapshot_renders_bars() -> None:
    out = pro_email.render_email(_pro_email_minimal_payload())
    # 10-dimension block label
    assert "10-DIMENSION SNAPSHOT" in out
    # Bar rendering: at least one full block and one empty block visible
    assert "#" in out
    assert "." in out
    # Each labeled row shows its highlight
    assert "ROE 27%" in out


def test_pro_email_peer_check_renders_tickers_and_lines() -> None:
    out = pro_email.render_email(_pro_email_minimal_payload())
    assert "Compared to:" in out
    assert "AMD" in out and "INTC" in out
    assert "stronger attention acceleration" in out


def test_pro_email_watchlist_table_shows_score_column() -> None:
    """v2 explicitly surfaces score; the legacy 'no score' design is gone."""
    out = pro_email.render_email(_pro_email_minimal_payload())
    assert "Score" in out
    assert "Rating" in out
    # Both watchlist movers shown
    assert "NVDA" in out and "TSLA" in out
    # Score-change arrows
    assert "+3" in out
    assert "-2" in out


def test_pro_email_empty_dimensions_fallback() -> None:
    out = pro_email.render_email(_pro_email_minimal_payload(dimensions=[]))
    assert "components not yet computed" in out


def test_pro_email_empty_peers_fallback() -> None:
    out = pro_email.render_email(_pro_email_minimal_payload(
        peer_tickers=[], peer_check_lines=[],
    ))
    assert "peer data not available" in out


# ============================================================
# x_hook
# ============================================================


def test_x_anomaly_hook_renders_single_post() -> None:
    out = x_hook.render_anomaly_hook(
        x_hook.AnomalyHookPayload(
            ticker="NVDA",
            action_verb="jumped",
            price_change_pct=2.4,
            session_label="pre-market",
            anomaly_dimension="volume",
            anomaly_value="2.1x avg",
            narrative_tension_line="Filings haven't caught up yet.",
            cta_url="https://app.jilo.ai/stocks/NVDA",
        )
    )
    # X posts are single tweets — must be < 4000 chars (X long-post limit)
    # but for an anomaly hook we aim WELL under 280 chars per line
    assert "$NVDA" in out
    assert "Full breakdown" in out
    assert "Not financial advice" in out
    _assert_no_score_language(out)
    # No newlines that imply a thread separator (---)
    assert "\n---\n" not in out
    assert "(1/" not in out


def test_x_honest_log_renders() -> None:
    out = x_hook.render_honest_log(
        x_hook.HonestLogPayload(
            days_ago=5,
            ticker="AMD",
            state_label="Heated",
            prev_state=SentinelState.WATCHING,
            curr_state=SentinelState.HEATED,
            price_move_pct=6.2,
            flag_dimension="volume + filings + social align",
            outcome_one_liner="Anomaly played out in price within 5 trading days.",
        )
    )
    assert "$AMD" in out
    assert "5 days ago" in out
    assert "We don't predict direction" in out
    assert "Position sizing" in out
    _assert_no_score_language(out)


def test_x_today_nothing_renders() -> None:
    out = x_hook.render_today_nothing(
        x_hook.TodayNothingPayload(universe_size=7400)
    )
    assert "Nothing unusual" in out
    assert "7400" in out
    assert "noise dressed as signal" in out
    _assert_no_score_language(out)
