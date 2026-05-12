"""Wire-up tests for USE_NEW_TEMPLATES flag (Telegram only).

Verification checklist from spec:
  [ ] New template renders without error (uses real-ish Opportunity)
  [ ] Output length < 4096 chars (Telegram limit)
  [ ] Passes redline pipeline (incl. earnings_window)
  [ ] Contains disclaimer
  [ ] No 'score' / 'X/100' / direction words
  [ ] 'nothing unusual' branch reachable (covered separately)

Plus invariants:
  - Flag off → LLM composer is called (existing behavior).
  - Flag on  → composer is NOT called for Telegram; X/Shorts still use it.
"""
from __future__ import annotations

import re

import pytest

from app.marketing.content_factory import (
    PLATFORM_SHORTS,
    PLATFORM_TELEGRAM,
    PLATFORM_X,
    _build_free_telegram_anomaly_payload,
    _render_free_telegram_body,
    _use_new_templates_for_telegram,
    create_drafts_for_opportunity,
)
from app.marketing.opportunities import (
    ACTION_CREATE_CONTENT,
    INTENT_TICKER_BUZZ,
    Opportunity,
)
from app.marketing.redline import check_no_score_references, scan as redline_scan
from app.marketing.state import SentinelState

TELEGRAM_MAX_CHARS = 4096
DIRECTION_WORDS_RE = re.compile(
    r"\b(buy|sell|hold|price target|predict|will\s+(?:rise|fall|surge|drop)|"
    r"going\s+up|going\s+down|set\s+to\s+outperform|set\s+to\s+underperform)\b",
    re.IGNORECASE,
)


def _opp(state: str = SentinelState.HEATED.value) -> Opportunity:
    return Opportunity(
        opportunity_id="OP-NVDA",
        source="intelligence",
        ticker="NVDA",
        intent=INTENT_TICKER_BUZZ,
        raw_text="$NVDA — intraday move +3.12%, social mentions doubled, 8-K filed.",
        url="https://sec.gov/x",
        author_id=None,
        opportunity_score=88,
        compliance_risk=10,
        suggested_action=ACTION_CREATE_CONTENT,
        evidence={
            "mover": {
                "price": 987.65,
                "change_pct": 3.12,
                "volume": 150_000_000,
                "relative_volume": 1.8,
                "source_url": "https://financialmodelingprep.com/stable/quote?symbol=NVDA",
            },
            "intelligence_profile": {
                "market_heat": 78,
                "social_heat": 82,
                "search_heat": 70,
                "news_heat": 55,
                "competitor_heat": 18,
                "sources_used": 4,
                "why_now": "Multi-signal anomaly confirmed by filing + volume.",
            },
        },
        state=state,
    )


class _SpyComposer:
    """Pure composer that records every compose() call for assertion."""
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def compose(self, *, opportunity, platform, cta_url):
        self.calls.append((opportunity.ticker, platform))
        return (
            f"${opportunity.ticker} — old LLM body. "
            f"https://x  Context, not financial advice."
        )


# ---- env reader ---------------------------------------------------------


def test_env_reader_falsy_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("USE_NEW_TEMPLATES", raising=False)
    assert _use_new_templates_for_telegram() is False


@pytest.mark.parametrize("truthy", ["1", "true", "TRUE", "yes", "on", "True"])
def test_env_reader_truthy_values(monkeypatch: pytest.MonkeyPatch, truthy: str) -> None:
    monkeypatch.setenv("USE_NEW_TEMPLATES", truthy)
    assert _use_new_templates_for_telegram() is True


@pytest.mark.parametrize("falsy", ["0", "false", "no", "", "off", "anything-else"])
def test_env_reader_falsy_values(monkeypatch: pytest.MonkeyPatch, falsy: str) -> None:
    monkeypatch.setenv("USE_NEW_TEMPLATES", falsy)
    assert _use_new_templates_for_telegram() is False


# ---- flag OFF: LLM still drives every platform --------------------------


def test_flag_off_llm_called_for_all_three_platforms(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("USE_NEW_TEMPLATES", raising=False)
    spy = _SpyComposer()
    bundle = create_drafts_for_opportunity(_opp(), composer=spy, date="20260512")
    platforms_called = {p for _, p in spy.calls}
    assert platforms_called == {PLATFORM_X, PLATFORM_TELEGRAM, PLATFORM_SHORTS}
    # Three drafts produced, body comes from LLM
    assert len(bundle.drafts) == 3
    for d in bundle.drafts:
        assert "old LLM body" in d.body


# ---- flag ON: Telegram uses template, others stay LLM -------------------


def test_flag_on_telegram_skips_llm_other_platforms_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("USE_NEW_TEMPLATES", "true")
    spy = _SpyComposer()
    bundle = create_drafts_for_opportunity(_opp(), composer=spy, date="20260512")
    platforms_called = {p for _, p in spy.calls}
    # Composer ran for X and Shorts but NOT Telegram
    assert platforms_called == {PLATFORM_X, PLATFORM_SHORTS}
    # Three drafts produced regardless
    assert len(bundle.drafts) == 3
    tg = next(d for d in bundle.drafts if d.platform == PLATFORM_TELEGRAM)
    # Telegram body is from the new template (recognisable by Sentinel header)
    assert "🛰" in tg.body
    assert "Sentinel · Anomaly Watch" in tg.body


# ---- 6-point verification checklist ------------------------------------


def test_checklist_renders_without_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("USE_NEW_TEMPLATES", "true")
    bundle = create_drafts_for_opportunity(_opp(), composer=_SpyComposer(), date="20260512")
    tg = next(d for d in bundle.drafts if d.platform == PLATFORM_TELEGRAM)
    assert tg.body  # non-empty


def test_checklist_length_under_telegram_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("USE_NEW_TEMPLATES", "true")
    bundle = create_drafts_for_opportunity(_opp(), composer=_SpyComposer(), date="20260512")
    tg = next(d for d in bundle.drafts if d.platform == PLATFORM_TELEGRAM)
    assert len(tg.body) < TELEGRAM_MAX_CHARS, f"body length {len(tg.body)} exceeds Telegram cap"


def test_checklist_passes_redline_scan(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("USE_NEW_TEMPLATES", "true")
    bundle = create_drafts_for_opportunity(_opp(), composer=_SpyComposer(), date="20260512")
    tg = next(d for d in bundle.drafts if d.platform == PLATFORM_TELEGRAM)
    redline = bundle.redlines[tg.content_id]
    # Has source + disclaimer + no forbidden phrases
    assert redline.has_source is True
    assert redline.has_disclaimer is True
    assert redline.ok is True, f"redline violations: {redline.violations}"


def test_checklist_contains_disclaimer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("USE_NEW_TEMPLATES", "true")
    body = _render_free_telegram_body(_opp(), "https://app.jilo.ai/stocks/NVDA")
    assert "not financial advice" in body.lower()


def test_checklist_no_score_references(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("USE_NEW_TEMPLATES", "true")
    body = _render_free_telegram_body(_opp(), "https://app.jilo.ai/stocks/NVDA")
    # Sprint 1 opt-in scan must report zero hits.
    assert check_no_score_references(body) == ()


def test_checklist_no_direction_words(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("USE_NEW_TEMPLATES", "true")
    body = _render_free_telegram_body(_opp(), "https://app.jilo.ai/stocks/NVDA")
    m = DIRECTION_WORDS_RE.search(body)
    assert m is None, f"direction word leaked into body: {m.group(0) if m else None}"


def test_checklist_nothing_branch_reachable() -> None:
    """The 'nothing unusual' branch is rendered by the template module
    directly (no Opportunity needed) — it fires when the daily scanner
    finds no qualified anomaly. Render it to confirm the branch is
    reachable and produces sensible content."""
    from app.marketing.templates.free_telegram import (
        NothingPayload,
        render_nothing,
    )

    body = render_nothing(NothingPayload(
        session_label="Pre-market",
        timestamp_et="08:30",
        scan_universe_size=7400,
    ))
    assert "nothing unusual" in body.lower()
    assert len(body) < TELEGRAM_MAX_CHARS
    assert check_no_score_references(body) == ()
    assert "not financial advice" in body.lower()


# ---- payload builder defaults ------------------------------------------


def test_payload_builder_uses_evidence_fields() -> None:
    payload = _build_free_telegram_anomaly_payload(
        _opp(), "https://app.jilo.ai/stocks/NVDA"
    )
    assert payload.state is SentinelState.HEATED
    assert payload.price == 987.65
    assert payload.price_change_pct == pytest.approx(3.12)
    assert payload.volume_relative == pytest.approx(1.8)
    # Confirming list picks up >=65 heats
    assert "market" in payload.confirming_list
    assert "social" in payload.confirming_list
    assert "search" in payload.confirming_list
    # Disagreeing picks up <=20 heats
    assert "competitor" in payload.disagreeing_list


def test_payload_builder_handles_missing_evidence() -> None:
    """When evidence is empty, payload still renders with safe placeholders."""
    bare = Opportunity(
        opportunity_id="OP-1",
        source="x",
        ticker="AMD",
        intent=INTENT_TICKER_BUZZ,
        raw_text="",
        url=None,
        author_id=None,
        opportunity_score=80,
        compliance_risk=0,
        suggested_action=ACTION_CREATE_CONTENT,
        evidence={},
        state=SentinelState.WATCHING.value,
    )
    payload = _build_free_telegram_anomaly_payload(bare, "https://x/y")
    assert payload.price == 0.0
    assert payload.volume_relative == 1.0
    assert payload.confirming_list  # never empty
    assert payload.disagreeing_list  # never empty


def test_unknown_state_in_opportunity_raises() -> None:
    """A bogus state string surfaces as ValueError, not silent mislabel."""
    bad = Opportunity(
        opportunity_id="OP-1",
        source="x",
        ticker="NVDA",
        intent=INTENT_TICKER_BUZZ,
        raw_text="x",
        url=None,
        author_id=None,
        opportunity_score=80,
        compliance_risk=0,
        suggested_action=ACTION_CREATE_CONTENT,
        evidence={},
        state="bogus",
    )
    with pytest.raises(ValueError):
        _render_free_telegram_body(bad, "https://x")
