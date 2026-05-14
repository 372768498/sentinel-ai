"""
Unit tests for the bot polling watchdog.

The watchdog runs every BOT_WATCHDOG_INTERVAL_SECONDS, calls
`bot.get_me()` + checks `updater.running`, and raises SIGTERM after
BOT_WATCHDOG_MAX_FAILURES consecutive failures. We patch
`asyncio.sleep` so the test runs in milliseconds, and patch
`os.kill` so SIGTERM is observable instead of actually firing.
"""
from __future__ import annotations

import asyncio
import os
import signal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.bot import bot as bot_module


def _make_app(*, get_me_ok: bool = True, running: bool = True):
    """Build a minimal Application-shaped mock for the watchdog."""
    me = SimpleNamespace(username="SentinelAIProChannelBot", id=1)
    bot = MagicMock()
    if get_me_ok:
        bot.get_me = AsyncMock(return_value=me)
    else:
        bot.get_me = AsyncMock(side_effect=RuntimeError("network down"))
    updater = MagicMock()
    updater.running = running
    app = MagicMock()
    app.bot = bot
    app.updater = updater
    return app


def _run_watchdog_for_cycles(app, cycles: int, *, max_failures: int = 3):
    """
    Drive the watchdog through exactly `cycles` iterations of its sleep
    loop, then break it out via CancelledError on iteration `cycles+1`.

    We MUST NOT call asyncio.sleep inside fake_sleep — bot_module.asyncio
    IS the asyncio module, so patching .sleep would catch the recursive
    call too. await on the AsyncMock get_me() is enough to yield to the
    event loop between cycles.
    """
    call_count = {"n": 0}

    async def fake_sleep(_seconds: float) -> None:
        call_count["n"] += 1
        if call_count["n"] > cycles:
            raise asyncio.CancelledError()
        # Intentionally no await — get_me's AsyncMock yields control.

    async def run():
        with (
            patch.object(bot_module, "_WATCHDOG_INTERVAL_SECONDS", 1),
            patch.object(bot_module, "_WATCHDOG_MAX_FAILURES", max_failures),
            patch.object(bot_module.asyncio, "sleep", new=fake_sleep),
        ):
            await bot_module._polling_watchdog(app)

    asyncio.run(run())


def test_watchdog_passes_when_bot_healthy():
    app = _make_app(get_me_ok=True, running=True)
    with patch.object(bot_module.os, "kill") as kill_mock:
        _run_watchdog_for_cycles(app, cycles=10, max_failures=3)
    # 10 healthy cycles → get_me called 10× → SIGTERM never raised
    assert app.bot.get_me.await_count == 10
    kill_mock.assert_not_called()


def test_watchdog_fires_sigterm_after_get_me_failures():
    app = _make_app(get_me_ok=False, running=True)
    with patch.object(bot_module.os, "kill") as kill_mock:
        _run_watchdog_for_cycles(app, cycles=10, max_failures=3)
    # After 3 consecutive failures the watchdog should SIGTERM and return,
    # so get_me is called at most 3× (then loop breaks).
    assert app.bot.get_me.await_count == 3
    kill_mock.assert_called_once()
    pid_arg, sig_arg = kill_mock.call_args.args
    assert pid_arg == os.getpid()
    assert sig_arg == signal.SIGTERM


def test_watchdog_fires_sigterm_when_updater_stops_running():
    app = _make_app(get_me_ok=True, running=False)
    with patch.object(bot_module.os, "kill") as kill_mock:
        _run_watchdog_for_cycles(app, cycles=10, max_failures=3)
    assert app.bot.get_me.await_count == 3
    kill_mock.assert_called_once()


def test_watchdog_recovers_when_intermittent_failure_clears():
    """A single failure followed by recovery must NOT trip SIGTERM."""
    me = SimpleNamespace(username="SentinelAIProChannelBot", id=1)
    fail_then_ok = AsyncMock(side_effect=[
        RuntimeError("blip"),     # 1st cycle: fail
        me, me, me, me, me,        # next 5: healthy
    ])
    bot = MagicMock()
    bot.get_me = fail_then_ok
    updater = MagicMock(); updater.running = True
    app = MagicMock(); app.bot = bot; app.updater = updater

    with patch.object(bot_module.os, "kill") as kill_mock:
        _run_watchdog_for_cycles(app, cycles=6, max_failures=3)
    # Failure counter resets on first success → SIGTERM never raised
    kill_mock.assert_not_called()


def test_watchdog_survives_swallows_swallows_get_me_exception_each_cycle():
    """get_me raising is recorded as a failure, not propagated out."""
    app = _make_app(get_me_ok=False, running=True)
    with patch.object(bot_module.os, "kill"):
        # Run exactly 2 cycles — under max_failures=3 → no SIGTERM, no raise
        _run_watchdog_for_cycles(app, cycles=2, max_failures=3)
    assert app.bot.get_me.await_count == 2
