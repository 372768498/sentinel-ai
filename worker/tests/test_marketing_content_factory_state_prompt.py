"""Tests for state-language injection into Content Factory prompts."""
from __future__ import annotations

import pytest

from app.marketing.content_factory import (
    PLATFORM_TELEGRAM,
    PLATFORM_X,
    SYSTEM_PROMPTS,
    USER_PROMPT_TEMPLATE,
    _format_user_prompt,
)
from app.marketing.opportunities import (
    ACTION_CREATE_CONTENT,
    INTENT_TICKER_BUZZ,
    Opportunity,
)
from app.marketing.state import SentinelState


def _opp(state: str = "calm", ticker: str = "NVDA") -> Opportunity:
    return Opportunity(
        opportunity_id=f"OP-{ticker}",
        source="intelligence",
        ticker=ticker,
        intent=INTENT_TICKER_BUZZ,
        raw_text="sample",
        url=None,
        author_id=None,
        opportunity_score=80,
        compliance_risk=0,
        suggested_action=ACTION_CREATE_CONTENT,
        evidence={},
        state=state,
    )


# ---- USER prompt ---------------------------------------------------------


def test_user_prompt_carries_state_label_and_one_liner() -> None:
    op = _opp(state=SentinelState.WATCHING.value)
    out = _format_user_prompt(op, PLATFORM_X, "https://x/y")
    assert "Sentinel state: Watching" in out
    assert "narrative running ahead of filings" in out


def test_user_prompt_no_score_reference() -> None:
    op = _opp(state=SentinelState.HEATED.value)
    out = _format_user_prompt(op, PLATFORM_TELEGRAM, "https://x/y")
    assert "Opportunity score" not in out
    assert "/100" not in out
    assert "score given" not in out


def test_user_prompt_renders_all_four_states() -> None:
    for state in SentinelState:
        op = _opp(state=state.value)
        out = _format_user_prompt(op, PLATFORM_X, "https://x/y")
        # Label string from STATE_DISPLAY appears
        assert state.name.title() in out or state.value.title() in out


def test_user_prompt_default_state_is_calm() -> None:
    """Opportunity built without explicit state defaults to calm."""
    op = Opportunity(
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
    )
    out = _format_user_prompt(op, PLATFORM_X, "https://x/y")
    assert "Sentinel state: Calm" in out


def test_user_prompt_unknown_state_raises() -> None:
    """Defensive: an Opportunity with an unrecognized state string must fail
    loudly rather than silently mislabeling the post."""
    op = _opp(state="bogus")
    with pytest.raises(ValueError):
        _format_user_prompt(op, PLATFORM_X, "https://x/y")


# ---- SYSTEM prompt -------------------------------------------------------


@pytest.mark.parametrize("platform", [PLATFORM_X, PLATFORM_TELEGRAM])
def test_system_prompts_ban_score_word(platform: str) -> None:
    """Each platform system prompt must instruct the LLM to avoid 'score'.

    We don't enforce this in redline scan() yet (opt-in for Sprint 1), but
    the LLM-side instruction must already discourage emitting it.
    """
    prompt = SYSTEM_PROMPTS[platform].lower()
    # The forbidden-list mentions 'score'
    assert "score" in prompt
    # And uses the anomaly vocabulary
    assert any(w in prompt for w in ("state", "anomaly", "calm", "heated"))


def test_user_template_does_not_reference_score_field() -> None:
    """Template string itself should not include {score} placeholder anymore."""
    assert "{score}" not in USER_PROMPT_TEMPLATE
    assert "{state_label}" in USER_PROMPT_TEMPLATE
