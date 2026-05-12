"""Sprint 5 integration test — exercise the full chain end-to-end.

Goal: verify the new Sprint 1-4 modules cooperate when chained:

  IntelligenceProfile
    → resolve_state
    → Opportunity (with state)
    → content_factory.create_drafts_for_opportunity (uses state prompt)
    → redline scan
    → earnings window check
    → dispatcher.should_push_alert decision
    → template rendering for a pretend Pro Telegram alert

This is a synthetic test — no LLM, no DB, no HTTP — but every module
boundary is wired together. Catches breaking changes that unit tests
would miss when a downstream consumer's contract drifts.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from app.marketing import (
    redline_earnings,
    state_resolver,
    notification_dispatcher,
    sector_context,
    tier_gating,
)
from app.marketing.content_factory import (
    PLATFORM_TELEGRAM,
    _apply_earnings_window,
    _format_user_prompt,
)
from app.marketing.intelligence import TickerIntelligenceProfile, profile_to_opportunity
from app.marketing.notification_modes import MODE_ACTIVE
from app.marketing.redline import check_no_score_references, scan as redline_scan
from app.marketing.state import SentinelState
from app.marketing.templates import pro_telegram


def _heated_profile() -> TickerIntelligenceProfile:
    """A profile with enough signal density to resolve to HEATED."""
    return TickerIntelligenceProfile(
        ticker="NVDA",
        company_name="NVIDIA Corp.",
        market_heat=78,
        social_heat=82,
        search_heat=70,
        news_heat=55,
        competitor_heat=40,
        overall_opportunity=85,
        why_now="$NVDA — intraday +3.1%, high-intent retail questions.",
        market_signals=("Intraday +3.10%", "Volume 150M", "Market cap $5.3T"),
        social_signals=(
            "[high_intent_question] $NVDA earnings preview thread",
            "[ticker_buzz] $NVDA up 3%",
        ),
        catalysts=(),
        recommended_angles=("valuation_gap", "retail_misread"),
        evidence={"sources_used": 3, "catalyst_count": 0},
        confidence="high",
    )


def _inflection_profile_with_filing() -> TickerIntelligenceProfile:
    base = _heated_profile()
    return TickerIntelligenceProfile(
        ticker="NVDA",
        company_name="NVIDIA Corp.",
        market_heat=base.market_heat,
        social_heat=base.social_heat,
        search_heat=base.search_heat,
        news_heat=70,
        competitor_heat=base.competitor_heat,
        overall_opportunity=92,
        why_now=base.why_now,
        market_signals=base.market_signals,
        social_signals=base.social_signals,
        catalysts=("8-K · big filing (2026-05-12)",),
        recommended_angles=base.recommended_angles,
        evidence={"catalyst_count": 1, "sources_used": 4},
        confidence="high",
    )


# ---- Stage 1+2: profile → state → Opportunity ----------------------------


def test_heated_profile_resolves_to_heated_state() -> None:
    p = _heated_profile()
    assert state_resolver.resolve_state(p) is SentinelState.HEATED


def test_inflection_profile_with_filing_resolves_to_inflection() -> None:
    p = _inflection_profile_with_filing()
    assert state_resolver.resolve_state(p) is SentinelState.INFLECTION


def test_profile_to_opportunity_stamps_state_value() -> None:
    p = _heated_profile()
    opp = profile_to_opportunity(p)
    assert opp.state == SentinelState.HEATED.value
    assert opp.ticker == "NVDA"


# ---- Stage 3: Opportunity → prompt → mock body → redline -----------------


class _StateAwareComposer:
    """Test composer that emits state-language output."""
    def compose(self, *, opportunity, platform, cta_url):
        return (
            f"${opportunity.ticker} — state has shifted to Heated. "
            f"Multi-signal anomaly detected. risk: volatility persists. "
            f"{cta_url}\n\nContext, not financial advice."
        )


def test_full_chain_clean_path_passes_redline_and_no_score() -> None:
    p = _heated_profile()
    opp = profile_to_opportunity(p)

    prompt = _format_user_prompt(opp, PLATFORM_TELEGRAM, "https://app.jilo.ai/stocks/NVDA")
    assert "Sentinel state: Heated" in prompt
    assert "{score}" not in prompt and "Opportunity score" not in prompt

    body = _StateAwareComposer().compose(
        opportunity=opp, platform=PLATFORM_TELEGRAM, cta_url="https://app.jilo.ai/stocks/NVDA"
    )

    rl = redline_scan(body, require_source=True, require_disclaimer=True)
    assert rl.ok, f"redline violations: {rl.violations}"
    # And the Sprint 1 opt-in score-reference scan also passes
    assert check_no_score_references(body) == ()


def test_earnings_window_layer_escalates_dangerous_phrase() -> None:
    body = "$NVDA set up for a beat with high conviction. https://x Not financial advice."
    rl = redline_scan(body, require_source=True, require_disclaimer=True)
    today = date(2026, 5, 12)
    earnings = today + timedelta(days=3)
    rl_w = _apply_earnings_window(body, rl, earnings, today=today)
    assert rl_w.ok is False
    assert any("earnings_window" in v for v in rl_w.violations)


# ---- Stage 4: state + tier → dispatcher --------------------------------


def test_active_user_at_intraday_pushes_heated() -> None:
    user = notification_dispatcher.UserNotificationProfile(
        notification_mode=MODE_ACTIVE,
        quiet_hours_start=None,
        quiet_hours_end=None,
        timezone="America/New_York",
        vacation_until=None,
    )
    alert = notification_dispatcher.AlertCandidate(
        ticker="NVDA", state=SentinelState.HEATED
    )
    intraday = datetime(2026, 5, 12, 11, 0)  # 11:00 ET, Mon
    d = notification_dispatcher.should_push_alert(user=user, alert=alert, now_et=intraday)
    assert d.should_push is True


def test_pro_tier_gates_divergence_compass() -> None:
    """Only Pro+ users see divergence compass output."""
    assert tier_gating.can_user_see(tier_gating.TIER_WATCH, "divergence_compass") is False
    assert tier_gating.can_user_see(tier_gating.TIER_PRO, "divergence_compass") is True


# ---- Stage 5: render Pro Telegram alert with all the wiring -------------


def test_pro_telegram_alert_renders_full_chain_safe() -> None:
    p = _heated_profile()
    opp = profile_to_opportunity(p)
    new_state = SentinelState(opp.state)

    compass_top, compass_bot = pro_telegram.render_compass(
        confirming=[
            pro_telegram.CompassSignal("market", 0.9),
            pro_telegram.CompassSignal("social", 0.8),
            pro_telegram.CompassSignal("news", 0.5),
        ],
        disagreeing=[pro_telegram.CompassSignal("peers", 0.4)],
    )

    out = pro_telegram.render_alert(
        pro_telegram.ProAlertPayload(
            timestamp_et="11:00",
            user_first_name="Alex",
            ticker=opp.ticker,
            prev_state=SentinelState.WATCHING,
            new_state=new_state,
            minutes_since_change=8,
            price=987.65,
            price_change_pct=3.1,
            session_label="intraday",
            volume_relative=1.6,
            change_bullets="- Volume rose to 1.6x avg in last hour\n- 8-K filed pre-open",
            compass_top=compass_top,
            compass_bottom=compass_bot,
            synthesis_paragraph="Three confirming signals overlap.",
            divergence_warning=pro_telegram.render_divergence_warning(0.3),
            pro_report_url="https://app.jilo.ai/pro/NVDA",
        )
    )

    # Output safety guarantees
    assert "$NVDA" in out
    assert "Alex" in out
    assert "Heated" in out and "Watching" in out
    assert "not financial advice" in out.lower()
    assert check_no_score_references(out) == ()


# ---- Sector context interop --------------------------------------------


def test_sector_context_band_does_not_leak_peer_tickers() -> None:
    sc = sector_context.compute_sector_context(
        ticker="NVDA",
        ticker_state=SentinelState.HEATED,
        peer_states=[
            SentinelState.HEATED, SentinelState.CALM, SentinelState.WATCHING,
            SentinelState.HEATED, SentinelState.CALM,
        ],
    )
    assert 0.5 <= sc.uniqueness_score < 0.8
    for forbidden_peer in ("AMD", "INTC", "AVGO", "MU", "TSM"):
        assert forbidden_peer not in sc.interpretation
