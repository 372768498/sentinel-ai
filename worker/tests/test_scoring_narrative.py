"""
Unit tests for the why_moving + risk_flag narrative generator.

We patch the `anthropic.AsyncAnthropic` constructor so no real network
call happens — the tests verify request shaping, response parsing, and
all the failure-mode return paths return an empty Narrative.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.scoring.narrative import Narrative, generate_narrative


def _run(coro):
    return asyncio.run(coro)


_MOVER_KWARGS = dict(
    ticker="NVDA",
    last_price=245.50,
    change_pct=1.2,
    volume=20_000_000,
    relative_volume=1.8,
    session_label="Post-close",
    score_100=67,
    recommendation="CONSTRUCTIVE",
    components={
        "earnings_surprise": {"score": 0.7, "surprise_pct": 5.2},
        "fundamentals": {"score": 0.6, "roe": 0.27},
    },
)


def _mock_client_with_body(body_text: str) -> MagicMock:
    """Build an AsyncAnthropic-shaped mock whose messages.create returns body_text."""
    response = SimpleNamespace(content=[SimpleNamespace(text=body_text)])
    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = AsyncMock(return_value=response)
    return client


def test_returns_empty_when_api_key_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    result = _run(generate_narrative(**_MOVER_KWARGS))
    assert result == Narrative(None, None)


def test_parses_valid_response(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    # Model emits the JSON body *without* the opening `{` (because of the
    # assistant-prefill trick). narrative.py stitches it back.
    body = '"why_moving": "EPS beat 5.2%; analyst upgrades push targets higher.", "risk_flag": "Trading at peer P/E premium"}'
    client = _mock_client_with_body(body)

    with patch("anthropic.AsyncAnthropic", return_value=client):
        result = _run(generate_narrative(**_MOVER_KWARGS))

    assert result.why_moving == "EPS beat 5.2%; analyst upgrades push targets higher."
    assert result.risk_flag == "Trading at peer P/E premium"


def test_parses_when_model_emits_leading_brace(monkeypatch: pytest.MonkeyPatch) -> None:
    """Some model versions ignore the prefill and emit the full JSON."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    body = '{"why_moving": "X", "risk_flag": "Y"}'
    # narrative.py prepends "{" unconditionally → we'd get "{{...}" which
    # is invalid JSON. This documents the current behavior:
    # the LLM must NOT lead with `{`. We strip code fences but not braces.
    # So this case fails gracefully to empty.
    client = _mock_client_with_body(body)
    with patch("anthropic.AsyncAnthropic", return_value=client):
        result = _run(generate_narrative(**_MOVER_KWARGS))
    # Documented failure-mode: bad JSON → empty Narrative
    assert result == Narrative(None, None)


def test_strips_code_fences(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    body = '```\n"why_moving": "X", "risk_flag": "Y"}\n```'
    client = _mock_client_with_body(body)
    with patch("anthropic.AsyncAnthropic", return_value=client):
        result = _run(generate_narrative(**_MOVER_KWARGS))
    assert result.why_moving == "X"
    assert result.risk_flag == "Y"


def test_truncates_overlong_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    long_why = "x" * 200
    long_risk = "y" * 100
    body = f'"why_moving": "{long_why}", "risk_flag": "{long_risk}"}}'
    client = _mock_client_with_body(body)
    with patch("anthropic.AsyncAnthropic", return_value=client):
        result = _run(generate_narrative(**_MOVER_KWARGS))
    assert result.why_moving is not None
    assert result.risk_flag is not None
    assert len(result.why_moving) <= 95
    assert len(result.risk_flag) <= 45
    assert result.why_moving.endswith("…")
    assert result.risk_flag.endswith("…")


def test_empty_strings_become_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    body = '"why_moving": "", "risk_flag": "   "}'
    client = _mock_client_with_body(body)
    with patch("anthropic.AsyncAnthropic", return_value=client):
        result = _run(generate_narrative(**_MOVER_KWARGS))
    assert result.why_moving is None
    assert result.risk_flag is None


def test_returns_empty_on_api_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = AsyncMock(side_effect=RuntimeError("rate limit"))
    with patch("anthropic.AsyncAnthropic", return_value=client):
        result = _run(generate_narrative(**_MOVER_KWARGS))
    assert result == Narrative(None, None)


def test_returns_empty_on_unparseable_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    body = "not json at all"
    client = _mock_client_with_body(body)
    with patch("anthropic.AsyncAnthropic", return_value=client):
        result = _run(generate_narrative(**_MOVER_KWARGS))
    assert result == Narrative(None, None)


def test_returns_empty_on_missing_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    # Valid JSON but no expected keys
    body = '"other": "stuff"}'
    client = _mock_client_with_body(body)
    with patch("anthropic.AsyncAnthropic", return_value=client):
        result = _run(generate_narrative(**_MOVER_KWARGS))
    assert result == Narrative(None, None)


def test_request_payload_contains_essentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify we're shipping the right context to the model."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    body = '"why_moving": "x", "risk_flag": "y"}'
    client = _mock_client_with_body(body)
    with patch("anthropic.AsyncAnthropic", return_value=client):
        _run(generate_narrative(**_MOVER_KWARGS))

    call_kwargs = client.messages.create.call_args.kwargs
    assert call_kwargs["model"] == "claude-haiku-4-5"
    # System prompt is set up for prompt cache
    assert call_kwargs["system"][0]["cache_control"] == {"type": "ephemeral"}
    # User message + assistant prefill of "{"
    msgs = call_kwargs["messages"]
    assert msgs[-1] == {"role": "assistant", "content": "{"}
    user_payload = msgs[0]["content"]
    assert "NVDA" in user_payload
    assert "67" in user_payload  # score_100
    assert "1.2" in user_payload  # change_pct
