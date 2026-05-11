"""Tests for the Telegram publisher."""

from __future__ import annotations

import asyncio

import pytest

from app.marketing.publishers.base import build_dry_run_url
from app.marketing.publishers.telegram import TelegramPublisher


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _clear_telegram_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in (
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CHANNEL_ID_PUBLIC",
        "TELEGRAM_CHANNEL_HANDLE",
        "TELEGRAM_CHANNEL_PUBLIC",
        "MARKETING_PUBLISH_DRY_RUN",
    ):
        monkeypatch.delenv(var, raising=False)


def test_dry_run_default_returns_dryrun_url() -> None:
    publisher = TelegramPublisher(dry_run=True)
    result = _run(
        publisher.publish(
            content_id="CT-20260511-NVDA-tg",
            ticker="NVDA",
            body="dummy body",
            cta_url="https://sentinel.example.com/stocks/NVDA",
        )
    )
    assert result.platform == "Telegram"
    assert result.dry_run is True
    assert result.published is False
    assert result.published_url == build_dry_run_url("Telegram", "CT-20260511-NVDA-tg")
    assert result.error is None


def test_master_kill_switch_forces_dry_run(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MARKETING_PUBLISH_DRY_RUN", "true")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.setenv("TELEGRAM_CHANNEL_ID_PUBLIC", "-100123")
    publisher = TelegramPublisher()  # no explicit override
    result = _run(
        publisher.publish(content_id="X", ticker="NVDA", body="hi", cta_url="https://x")
    )
    assert result.dry_run is True
    assert result.published is False


def test_live_missing_token_returns_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MARKETING_PUBLISH_DRY_RUN", "false")
    monkeypatch.setenv("TELEGRAM_CHANNEL_ID_PUBLIC", "-100123")
    publisher = TelegramPublisher()
    result = _run(
        publisher.publish(content_id="CT-1", ticker="NVDA", body="hi", cta_url="https://x")
    )
    assert result.published is False
    assert result.dry_run is False
    assert result.error == "missing_telegram_bot_token"


def test_live_missing_target_returns_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MARKETING_PUBLISH_DRY_RUN", "false")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    publisher = TelegramPublisher()
    result = _run(
        publisher.publish(content_id="CT-1", ticker="NVDA", body="hi", cta_url="https://x")
    )
    assert result.error == "missing_telegram_channel_target"


def test_live_send_success_builds_https_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MARKETING_PUBLISH_DRY_RUN", "false")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.setenv("TELEGRAM_CHANNEL_ID_PUBLIC", "-1001234567890")
    monkeypatch.setenv("TELEGRAM_CHANNEL_HANDLE", "@SentinelAI_signals")

    captured: dict = {}

    async def fake_send(text, *, parse_mode="HTML", disable_web_page_preview=True):
        captured["text"] = text
        captured["parse_mode"] = parse_mode
        return {"message_id": 42, "chat": {"id": -1001234567890}}

    publisher = TelegramPublisher(send_fn=fake_send)
    result = _run(
        publisher.publish(
            content_id="CT-20260511-NVDA-tg",
            ticker="NVDA",
            body="$NVDA score 78/100. https://sentinel/stocks/NVDA\n\nNot financial advice.",
            cta_url="https://sentinel.example.com/stocks/NVDA?utm_source=telegram",
        )
    )
    assert result.published is True
    assert result.dry_run is False
    assert result.message_id == "42"
    assert result.published_url == "https://t.me/SentinelAI_signals/42"
    # HTML escape applied
    assert "<a href=" in captured["text"]
    assert captured["parse_mode"] == "HTML"


def test_live_send_falls_back_to_telegram_uri_without_handle(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MARKETING_PUBLISH_DRY_RUN", "false")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.setenv("TELEGRAM_CHANNEL_ID_PUBLIC", "-1009999")

    async def fake_send(text, *, parse_mode="HTML", disable_web_page_preview=True):
        return {"message_id": 7}

    publisher = TelegramPublisher(send_fn=fake_send)
    result = _run(
        publisher.publish(content_id="CT-1", ticker="AAPL", body="b", cta_url="https://x")
    )
    assert result.published is True
    assert result.published_url == "telegram:message/-1009999/7"


def test_live_send_exception_returns_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MARKETING_PUBLISH_DRY_RUN", "false")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.setenv("TELEGRAM_CHANNEL_ID_PUBLIC", "-100123")

    async def boom(text, **_):
        raise RuntimeError("network blew up")

    publisher = TelegramPublisher(send_fn=boom)
    result = _run(
        publisher.publish(content_id="CT-1", ticker="NVDA", body="b", cta_url="https://x")
    )
    assert result.published is False
    assert result.dry_run is False
    assert "network blew up" in (result.error or "")


def test_live_send_missing_message_id_returns_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MARKETING_PUBLISH_DRY_RUN", "false")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.setenv("TELEGRAM_CHANNEL_ID_PUBLIC", "-100123")

    async def fake_send(text, **_):
        return {"weird": "result"}

    publisher = TelegramPublisher(send_fn=fake_send)
    result = _run(
        publisher.publish(content_id="CT-1", ticker="NVDA", body="b", cta_url="https://x")
    )
    assert result.error == "telegram_api_returned_no_message_id"


def test_html_escape_applied_to_user_content(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tags inside body must be escaped before sending — otherwise Telegram
    returns 400 Bad Request: can't parse entities."""
    monkeypatch.setenv("MARKETING_PUBLISH_DRY_RUN", "false")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.setenv("TELEGRAM_CHANNEL_ID_PUBLIC", "-100123")

    captured: dict = {}

    async def fake_send(text, **_):
        captured["text"] = text
        return {"message_id": 1}

    publisher = TelegramPublisher(send_fn=fake_send)
    _run(
        publisher.publish(
            content_id="CT-1",
            ticker="NVDA",
            body="risk <flag> & danger > 50%",
            cta_url="https://x",
        )
    )
    assert "&lt;flag&gt;" in captured["text"]
    assert "&amp;" in captured["text"]
    assert "&gt; 50%" in captured["text"]
