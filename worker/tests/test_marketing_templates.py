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


def test_pro_email_watchlist_table_has_no_score_column() -> None:
    items = [
        pro_email.TickerStatus(
            ticker="NVDA",
            state=SentinelState.HEATED,
            volume_relative=2.1,
            days_in_calm=0,
            short_note="multi-signal",
        ),
        pro_email.TickerStatus(
            ticker="AMD",
            state=SentinelState.CALM,
            volume_relative=0.9,
            days_in_calm=20,
            short_note="—",
        ),
    ]
    table = pro_email.render_watchlist_table(items)
    assert "NVDA" in table and "AMD" in table
    assert "State" in table
    _assert_no_score_language(table)
    # The 14+ days nudge fires for AMD
    assert "AMD" in table and "Calm for 14+ days" in table
    assert "Consider removing" in table


def test_pro_email_watchlist_no_nudge_when_no_quiet_tickers() -> None:
    items = [
        pro_email.TickerStatus(
            ticker="NVDA",
            state=SentinelState.WATCHING,
            volume_relative=1.5,
            days_in_calm=2,
            short_note="-",
        ),
    ]
    table = pro_email.render_watchlist_table(items)
    assert "Calm for 14+ days" not in table
    assert "Consider removing" not in table


def test_pro_email_render_full() -> None:
    items = [
        pro_email.TickerStatus(
            ticker="NVDA",
            state=SentinelState.HEATED,
            volume_relative=2.1,
            days_in_calm=0,
            short_note="multi-signal",
        ),
    ]
    payload = pro_email.ProEmailDailyPayload(
        subject_dynamic="3 alerts today",
        preview_dynamic="NVDA Heated, AMD Calm, MSFT Watching",
        date_long="Mon May 12 2026",
        delivery_time_et="07:00",
        watchlist_count=5,
        alert_count_today=3,
        state_distribution="2 Calm, 2 Watching, 1 Heated",
        biggest_change_block="NVDA: Watching → Heated at 09:02 ET",
        week_ahead_calendar="Tue: AMD earnings\nThu: NVDA Investor Day",
        watchlist_table=pro_email.render_watchlist_table(items),
        sector_context_paragraph="Semis pattern is uniquely NVDA today.",
        manage_url="https://app.jilo.ai/manage",
        mode_url="https://app.jilo.ai/mode",
        current_mode="active",
        quiet_hours_url="https://app.jilo.ai/quiet",
        methodology_url="https://app.jilo.ai/method",
    )
    out = pro_email.render_email(payload)
    assert "SENTINEL PRO" in out
    assert "Not financial advice" in out
    _assert_no_score_language(out)


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
