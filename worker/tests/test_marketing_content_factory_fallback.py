"""Tests for OpenAICompatibleComposer + FallbackComposer (Week 8.5)."""

from __future__ import annotations

import pytest

from app.marketing.content_factory import (
    ContentFactoryError,
    FallbackComposer,
    OpenAICompatibleComposer,
    build_default_composer,
)
from app.marketing.opportunities import (
    ACTION_CREATE_CONTENT,
    INTENT_TICKER_BUZZ,
    Opportunity,
)


def _opp() -> Opportunity:
    return Opportunity(
        opportunity_id="OP-1",
        source="x",
        ticker="NVDA",
        intent=INTENT_TICKER_BUZZ,
        raw_text="probe",
        url=None,
        author_id=None,
        opportunity_score=85,
        compliance_risk=0,
        suggested_action=ACTION_CREATE_CONTENT,
        evidence={},
    )


# ---- OpenAICompatibleComposer ---------------------------------------------


class _FakeOpenAIChoice:
    def __init__(self, text: str) -> None:
        self.message = type("M", (), {"content": text})()


class _FakeOpenAIResponse:
    def __init__(self, text: str) -> None:
        self.choices = [_FakeOpenAIChoice(text)]


class _FakeOpenAIClient:
    def __init__(self, reply: str = "fallback output") -> None:
        self.reply = reply
        self.calls: list[dict] = []
        self.chat = type("Chat", (), {})()
        self.chat.completions = self

    def create(self, *, model, max_tokens, messages):
        self.calls.append({"model": model, "messages": messages})
        return _FakeOpenAIResponse(self.reply + "\n")  # whitespace stripped by composer


def test_openai_composer_requires_api_key_or_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MARKETING_FALLBACK_API_KEY", raising=False)
    with pytest.raises(ContentFactoryError, match="MARKETING_FALLBACK_API_KEY"):
        OpenAICompatibleComposer()


def test_openai_composer_with_injected_client_works() -> None:
    fake = _FakeOpenAIClient(reply="hello from gpt-5.5")
    cmp = OpenAICompatibleComposer(client=fake, model="gpt-5.5")
    out = cmp.compose(opportunity=_opp(), platform="X", cta_url="https://x/y")
    assert out == "hello from gpt-5.5"
    assert len(fake.calls) == 1
    call = fake.calls[0]
    assert call["model"] == "gpt-5.5"
    assert call["messages"][0]["role"] == "system"
    assert call["messages"][1]["role"] == "user"


def test_openai_composer_unsupported_platform_raises() -> None:
    fake = _FakeOpenAIClient()
    cmp = OpenAICompatibleComposer(client=fake, model="m")
    with pytest.raises(ContentFactoryError, match="Unsupported platform"):
        cmp.compose(opportunity=_opp(), platform="Discord", cta_url="https://x")


def test_openai_composer_picks_up_fallback_model_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MARKETING_FALLBACK_MODEL", "custom-model-x")
    fake = _FakeOpenAIClient()
    cmp = OpenAICompatibleComposer(client=fake)
    cmp.compose(opportunity=_opp(), platform="X", cta_url="https://x")
    assert fake.calls[0]["model"] == "custom-model-x"


# ---- FallbackComposer -----------------------------------------------------


class _RecorderComposer:
    def __init__(self, *, raises=None, returns: str = "ok") -> None:
        self.raises = raises
        self.returns = returns
        self.calls = 0

    def compose(self, *, opportunity, platform, cta_url):
        self.calls += 1
        if self.raises is not None:
            raise self.raises
        return self.returns


def test_fallback_unused_when_primary_succeeds() -> None:
    primary = _RecorderComposer(returns="primary text")
    fallback = _RecorderComposer(returns="fallback text")
    fc = FallbackComposer(primary=primary, fallback=fallback)
    out = fc.compose(opportunity=_opp(), platform="X", cta_url="https://x")
    assert out == "primary text"
    assert primary.calls == 1
    assert fallback.calls == 0


def test_fallback_triggered_on_anthropic_rate_limit_error() -> None:
    import anthropic
    import httpx

    # Build a real anthropic.RateLimitError so isinstance checks pass
    resp = httpx.Response(429, request=httpx.Request("POST", "https://x"))
    err = anthropic.RateLimitError("rate limit", response=resp, body={})
    primary = _RecorderComposer(raises=err)
    fallback = _RecorderComposer(returns="fallback saved the day")
    fc = FallbackComposer(primary=primary, fallback=fallback)
    out = fc.compose(opportunity=_opp(), platform="X", cta_url="https://x")
    assert out == "fallback saved the day"
    assert primary.calls == 1
    assert fallback.calls == 1


def test_fallback_triggered_on_chinese_rate_limit_message() -> None:
    """Some proxies return the rate-limit body as a 200 with Chinese text
    that the SDK then re-raises as a generic Exception. Detect by message."""
    err = RuntimeError("请求过于频繁，请稍后再试")
    primary = _RecorderComposer(raises=err)
    fallback = _RecorderComposer(returns="ok")
    fc = FallbackComposer(primary=primary, fallback=fallback)
    out = fc.compose(opportunity=_opp(), platform="X", cta_url="https://x")
    assert out == "ok"
    assert fallback.calls == 1


def test_fallback_not_triggered_on_non_rate_limit_error() -> None:
    """Other failures (e.g. auth error, bad request) should propagate, NOT
    trigger fallback — fallback is only for rate limits, not for masking bugs."""
    err = ValueError("malformed request body")
    primary = _RecorderComposer(raises=err)
    fallback = _RecorderComposer(returns="should not see this")
    fc = FallbackComposer(primary=primary, fallback=fallback)
    with pytest.raises(ValueError, match="malformed"):
        fc.compose(opportunity=_opp(), platform="X", cta_url="https://x")
    assert fallback.calls == 0


def test_fallback_propagates_fallback_exception() -> None:
    """If both primary and fallback fail, fallback's exception surfaces (not
    primary's) — caller sees the most recent error."""
    rate_limit = RuntimeError("rate limit hit")
    primary = _RecorderComposer(raises=rate_limit)
    fallback_err = RuntimeError("fox is also down")
    fallback = _RecorderComposer(raises=fallback_err)
    fc = FallbackComposer(primary=primary, fallback=fallback)
    with pytest.raises(RuntimeError, match="fox is also down"):
        fc.compose(opportunity=_opp(), platform="X", cta_url="https://x")


# ---- build_default_composer factory --------------------------------------


def test_build_default_composer_no_fallback_when_env_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.delenv("MARKETING_FALLBACK_API_KEY", raising=False)
    cmp = build_default_composer()
    # Plain MultiPlatformComposer, not wrapped
    from app.marketing.content_factory import MultiPlatformComposer
    assert isinstance(cmp, MultiPlatformComposer)
    assert not isinstance(cmp, FallbackComposer)


def test_build_default_composer_wraps_with_fallback_when_env_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("MARKETING_FALLBACK_API_KEY", "sk-fb-test")
    monkeypatch.setenv("MARKETING_FALLBACK_BASE_URL", "https://example/v1")
    monkeypatch.setenv("MARKETING_FALLBACK_MODEL", "gpt-5.5")
    cmp = build_default_composer()
    assert isinstance(cmp, FallbackComposer)


def test_build_default_composer_raises_when_no_primary_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("MARKETING_FALLBACK_API_KEY", "sk-fb")
    with pytest.raises(ContentFactoryError, match="ANTHROPIC_API_KEY"):
        build_default_composer()
