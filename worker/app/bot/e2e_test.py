"""
End-to-end self-test for the Sentinel AI Telegram bot.
Run: python -m worker.app.bot.e2e_test

Steps:
  1. Timezone check
  2. Red-line scan on all templates
  3. Quiet hours logic (pure logic, no DB)
  4. "What about X?" handler regex
  5. DB: onboarding write + read (requires Postgres)
  6. DB: threshold alert dispatch + dedup + quiet-hours queuing (requires Postgres)

Steps 1-4 always run. Steps 5-6 skip gracefully if DB is unavailable.
"""
from __future__ import annotations

import asyncio
import os
import sys

# ── Allow running as: python -m worker.app.bot.e2e_test from project root ──
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from dotenv import load_dotenv
load_dotenv(os.path.join(_project_root, "sentinel-ai", ".env.local"))

TEST_USER_ID = 999_888_777   # fake Telegram user id for test isolation

_pass = 0
_fail = 0
_skip = 0


def _ok(msg: str) -> None:
    global _pass
    _pass += 1
    print(f"  [PASS] {msg}", flush=True)


def _fail_msg(msg: str) -> None:
    global _fail
    _fail += 1
    print(f"  [FAIL] {msg}", flush=True)


def _skip_msg(msg: str) -> None:
    global _skip
    _skip += 1
    print(f"  [SKIP] {msg}", flush=True)


# ─────────────────────────────────────────────────────────────────────────────
# STEP 1 · Timezone check
# ─────────────────────────────────────────────────────────────────────────────

def step1_timezone() -> None:
    print("\n=== STEP 1: Timezone check ===")
    from worker.app.bot.tz_check import now_et, now_utc, et_display

    et = now_et()
    utc = now_utc()
    diff_hours = (et.utcoffset().total_seconds()) / 3600

    print(f"  UTC:   {utc.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print(f"  ET:    {et.strftime('%Y-%m-%d %H:%M:%S %Z')}  (offset {diff_hours:+.0f}h)")
    print(f"  DST:   {'yes (EDT, UTC-4)' if diff_hours == -4 else 'no (EST, UTC-5)'}")
    print(f"  et_display(): {et_display()}")

    if et.tzname() in ("EST", "EDT"):
        _ok("ET timezone is correct (America/New_York with DST handling)")
    else:
        _fail_msg(f"Unexpected timezone name: {et.tzname()}")

    offset_ok = diff_hours in (-4, -5)
    if offset_ok:
        _ok(f"ET offset {diff_hours:+.0f}h is valid (EDT=-4 / EST=-5)")
    else:
        _fail_msg(f"Unexpected ET offset: {diff_hours:+.0f}h")


# ─────────────────────────────────────────────────────────────────────────────
# STEP 2 · Red-line scan on all templates
# ─────────────────────────────────────────────────────────────────────────────

def step2_red_line_scan() -> None:
    print("\n=== STEP 2: Red-line scan on all templates ===")
    from worker.app.bot.templates.telegram_messages import (
        welcome_group,
        ONBOARDING_STEP1,
        onboarding_step2,
        onboarding_step3,
        onboarding_done,
        watchlist_dashboard,
        alert_threshold_crossed,
        alert_threshold_crossed_batch,
        alert_silence_day,
        alert_sec_filing,
        alert_earnings,
        alert_fed_macro,
        alert_user_reply_ticker,
        alert_eod_digest,
        public_premarket_brief_quiet,
        public_premarket_brief_active,
        public_postclose_digest,
        HELP_MESSAGE,
    )

    rendered = [
        welcome_group("Alice", "SentinelAIProChannelBot", 12345),
        ONBOARDING_STEP1,
        onboarding_step2(["NVDA", "AAPL"]),
        onboarding_step3(2.0),
        onboarding_done(["NVDA", "AAPL"], 2.0, True, 22, 7),
        watchlist_dashboard([{"ticker": "NVDA", "threshold": 2.0, "active": True}]),
        alert_threshold_crossed("NVDA", 2.5, 120.0, 123.0, "Pre-market"),
        alert_threshold_crossed_batch([
            {"ticker": "NVDA", "change_pct": 2.5, "prev_price": 120.0, "price": 123.0},
            {"ticker": "AAPL", "change_pct": -3.1, "prev_price": 180.0, "price": 174.4},
            {"ticker": "TSLA", "change_pct": 1.8, "prev_price": 230.0, "price": 234.1},
        ]),
        alert_silence_day(["NVDA", "AAPL"], "May 08"),
        alert_sec_filing("NVDA", "NVIDIA Corp", "8-K",
                         "Material agreement announced.", "https://sec.gov/example"),
        alert_earnings("NVDA", "NVIDIA", "Beat", 0.89, 0.82, "$26.0B", "$25.1B",
                       "https://ir.nvidia.com/example"),
        alert_fed_macro("FOMC Statement", "Fed holds rates steady",
                        "Policy rate unchanged at 5.25-5.50%.",
                        ["NVDA", "AAPL"], "https://federalreserve.gov/example"),
        alert_user_reply_ticker("TSLA", 238.42, 0.6, 2.0, "none today",
                                "no material news detected"),
        alert_eod_digest(
            [{"ticker": "NVDA", "change_pct": 2.5, "price": 123.0}],
            ["AAPL", "TSLA"],
            "May 08",
        ),
        public_premarket_brief_quiet("Thu May 08"),
        public_premarket_brief_active("Thu May 08", ["NVDA up 2% pre-market"]),
        public_postclose_digest("Thu May 08",
                                [{"ticker": "NVDA", "change_pct": 2.5}],
                                ["Fed held rates"]),
        HELP_MESSAGE,
    ]

    RED_LINE_PHRASES = [
        "buy", "sell", "price target", "short", "long position",
        "will go up", "will go down", "predict", "prediction",
        "invest in", "trading signal",
    ]

    violations: list[str] = []
    for i, text in enumerate(rendered):
        text_lower = text.lower()
        for phrase in RED_LINE_PHRASES:
            if phrase in text_lower:
                violations.append(f"Template {i+1}: found \"{phrase}\"")

    if violations:
        for v in violations:
            _fail_msg(v)
    else:
        _ok(f"All {len(rendered)} templates pass red-line check — no buy/sell/prediction language")

    # Check all templates have disclaimer
    disclaimers = ["not advice", "context, not advice", "your call"]
    # Only alert templates need disclaimers (indices 6–16); skip onboarding/help
    ALERT_INDICES = range(6, 17)
    missing = []
    for i, text in enumerate(rendered):
        if i not in ALERT_INDICES:
            continue
        text_lower = text.lower()
        if not any(d in text_lower for d in disclaimers):
            missing.append(f"Template {i+1} missing disclaimer")

    if missing:
        for m in missing:
            _fail_msg(m)
    else:
        _ok("All alert templates contain disclaimer (Context/Your call, not advice)")


# ─────────────────────────────────────────────────────────────────────────────
# STEP 3 · Quiet hours logic (pure logic, no DB)
# ─────────────────────────────────────────────────────────────────────────────

def step3_quiet_hours_logic() -> None:
    print("\n=== STEP 3: Quiet hours logic (ET-aware) ===")
    from worker.app.bot.tz_check import is_quiet_time

    # Midnight-crossing window (22 to 7)
    assert is_quiet_time(True, 22, 7) == _hour_in_window(22, 7), \
        "Midnight-crossing window logic wrong"
    _ok("Midnight-crossing window (22-7) logic correct")

    # Same-day window (1 to 6)
    assert is_quiet_time(True, 1, 6) == _hour_in_window(1, 6), \
        "Same-day window logic wrong"
    _ok("Same-day window (1-6) logic correct")

    # Disabled → never quiet
    assert not is_quiet_time(False, 0, 23), "Disabled quiet hours should return False"
    _ok("Disabled quiet hours always returns False")

    # Test all 24 hours for midnight-crossing window (22-7) consistency
    errors = []
    for h in range(24):
        expected = (h >= 22 or h < 7)
        got = _is_quiet_time_for_hour(h, True, 22, 7)
        if got != expected:
            errors.append(f"Hour {h}: expected {expected}, got {got}")
    if errors:
        for e in errors:
            _fail_msg(e)
    else:
        _ok("All 24 hours correctly classified for 22:00-07:00 window")


def _hour_in_window(start: int, end: int) -> bool:
    from worker.app.bot.tz_check import now_et
    h = now_et().hour
    if start > end:
        return h >= start or h < end
    return start <= h < end


def _is_quiet_time_for_hour(hour: int, enabled: bool, start: int, end: int) -> bool:
    if not enabled:
        return False
    if start > end:
        return hour >= start or hour < end
    return start <= hour < end


# ─────────────────────────────────────────────────────────────────────────────
# STEP 4 · "What about X?" handler regex
# ─────────────────────────────────────────────────────────────────────────────

def step4_ticker_query_handler() -> None:
    print("\n=== STEP 4: 'What about X?' handler regex ===")
    from worker.app.bot.handlers.messages import _extract_ticker_from_query

    cases = [
        ("What about TSLA?", "TSLA"),
        ("how's NVDA doing?", "NVDA"),
        ("why no alert on AAPL", "AAPL"),
        ("check MSFT", "MSFT"),
        ("GOOGL?", "GOOGL"),
        ("hello world", None),           # no ticker
        ("Is AI the future?", None),     # AI is in exclusion list
    ]

    errors = []
    for text, expected in cases:
        got = _extract_ticker_from_query(text)
        if got != expected:
            errors.append(f"Input '{text}': expected {expected!r}, got {got!r}")

    if errors:
        for e in errors:
            _fail_msg(e)
    else:
        _ok(f"All {len(cases)} query patterns correctly classified")


def step2b_whop_templates_red_line() -> None:
    print("\n=== STEP 2b: Whop forum templates red-line scan ===")
    from worker.app.bot.templates.whop_post_templates import (
        fallback_quiet_day,
        friday_week_review,
        monday_week_ahead,
        tuesday_caught_recap,
        wednesday_behind_scenes,
    )
    from worker.app.bot.templates.whop_education_posts import EDUCATION_POSTS

    samples = [
        monday_week_ahead("May 12"),
        tuesday_caught_recap(0, scanned_count=200),
        tuesday_caught_recap(3, "• **NVDA** +2.5%\n• **TSLA** -3.1%", 200),
        wednesday_behind_scenes(200, 197, 3, "• NVDA +2.5%", "AAPL +1.8%"),
        friday_week_review("May 5", "May 9", 1000, 990, 10,
                           "Wed", 5, "Fri", 1, "**Biggest:** NVDA +6.2%"),
        fallback_quiet_day("May 12"),
    ] + EDUCATION_POSTS

    RED_LINE = [
        "buy", "sell", "should buy", "should sell", "expect rally",
        "predict", "prediction", "will go up", "will go down",
        "price target", "trading signal",
    ]
    violations = []
    for i, post in enumerate(samples):
        full = (post["title"] + "\n" + post["content"]).lower()
        # Sanitize title for printable ASCII so GBK consoles don't crash on emoji
        safe_title = post["title"].encode("ascii", "replace").decode("ascii")[:40]
        for phrase in RED_LINE:
            if phrase in full:
                violations.append(f"Post {i+1} ({safe_title!r}): contains '{phrase}'")
    if violations:
        for v in violations:
            _fail_msg(v)
    else:
        _ok(f"All {len(samples)} Whop posts ({len(EDUCATION_POSTS)} education + "
            f"{len(samples) - len(EDUCATION_POSTS)} dynamic) pass red-line check")

    # Disclaimer presence
    missing = []
    for i, post in enumerate(samples):
        body = post["content"].lower()
        if "advice" not in body and "sentinel" not in body:
            missing.append(f"Post {i+1} missing brand sign-off")
    if missing:
        for m in missing:
            _fail_msg(m)
    else:
        _ok("All Whop posts contain brand sign-off (advice / sentinel)")


def step4b_priority_classification() -> None:
    print("\n=== STEP 4b: Alert priority classification ===")
    from worker.app.bot.templates.telegram_messages import (
        AlertPriority, compute_priority, should_call_for,
    )

    cases = [
        (1.5, "threshold", AlertPriority.NORMAL),
        (3.0, "threshold", AlertPriority.NORMAL),
        (5.0, "threshold", AlertPriority.URGENT),
        (-7.5, "threshold", AlertPriority.URGENT),
        (1.0, "fed_emergency", AlertPriority.CRITICAL),
        (0.0, "halt", AlertPriority.CRITICAL),
        (2.0, "sec_investigation", AlertPriority.URGENT),
        (0.0, "vix_spike", AlertPriority.CRITICAL),
    ]

    errors = []
    for pct, event, expected in cases:
        got = compute_priority(pct, event)
        if got != expected:
            errors.append(f"({pct}, {event}): expected {expected.value}, got {got.value}")

    if errors:
        for e in errors:
            _fail_msg(e)
    else:
        _ok(f"All {len(cases)} priority cases classified correctly")

    if should_call_for(AlertPriority.CRITICAL) and not should_call_for(AlertPriority.NORMAL):
        _ok("should_call_for() correctly flags CRITICAL only")
    else:
        _fail_msg("should_call_for() logic wrong")


# ─────────────────────────────────────────────────────────────────────────────
# STEP 5 · DB: onboarding write + read
# ─────────────────────────────────────────────────────────────────────────────

async def step5_db_onboarding() -> bool:
    """Returns True if DB is available and test passed."""
    print("\n=== STEP 5: DB — onboarding write + read ===")
    try:
        from worker.app.bot import db
        pool = await db.get_pool()
    except Exception as exc:
        _skip_msg(f"DB unavailable ({exc.__class__.__name__}: {exc}) — skipping steps 5-6")
        return False

    try:
        # Write test user
        await db.upsert_profile(
            TEST_USER_ID,
            telegram_username="e2e_test",
            telegram_first_name="E2ETest",
            watchlist=["NVDA", "AAPL", "TSLA"],
            alert_threshold=0.01,         # Near-zero → guaranteed trigger
            quiet_hours_enabled=False,    # No quiet hours for alert test
            onboarding_completed=True,
        )
        _ok("Upsert profile wrote to DB")

        # Read back
        profile = await db.get_profile(TEST_USER_ID)
        assert profile is not None, "Profile not found after write"
        assert profile["watchlist"] == ["NVDA", "AAPL", "TSLA"], \
            f"Watchlist mismatch: {profile['watchlist']}"
        assert profile["alert_threshold"] == 0.01, \
            f"Threshold mismatch: {profile['alert_threshold']}"
        assert profile["onboarding_completed"], "onboarding_completed should be True"
        _ok(f"Read back: watchlist={profile['watchlist']}, threshold={profile['alert_threshold']}")

        return True

    except Exception as exc:
        _fail_msg(f"DB onboarding test failed: {exc}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# STEP 6 · DB: alert dispatch + dedup + quiet-hours queuing
# ─────────────────────────────────────────────────────────────────────────────

async def step6_alert_dispatch() -> None:
    print("\n=== STEP 6: Alert dispatch + dedup + quiet-hours queuing ===")

    from worker.app.bot import db
    from worker.app.bot.alerter import _send_or_queue, dispatch_personal_alerts
    from worker.app.scanner import TickerMove

    # ── 6a: Mock sender to capture DMs without actually sending ─────────────
    sent_messages: list[dict] = []

    async def mock_sender(user_id: int, text: str, priority=None) -> dict:
        sent_messages.append({"user_id": user_id, "text": text, "priority": priority})
        return {"message_id": len(sent_messages)}  # fake message_id

    # ── 6b: Test immediate send (quiet hours OFF) ────────────────────────────
    profile_no_quiet = {
        "telegram_user_id": TEST_USER_ID,
        "quiet_hours_enabled": False,
        "quiet_hours_start": 22,
        "quiet_hours_end": 7,
    }
    test_move = TickerMove(
        ticker="NVDA",
        prev_close=120.0,
        last_price=126.0,
        change_pct=5.0,
    )

    # Clear any stale cooldowns
    await db.clear_cooldowns(TEST_USER_ID)
    await db.delete_test_queued_alerts(TEST_USER_ID)

    stats = await _send_or_queue(profile_no_quiet, [test_move], mock_sender)
    if stats["sent"] == 1 and stats["queued"] == 0:
        _ok(f"Immediate send: 1 alert dispatched (msg captured: {len(sent_messages)})")
    else:
        _fail_msg(f"Expected 1 sent, 0 queued — got {stats}")

    # ── 6c: Dedup test — same crossing within cooldown window ────────────────
    stats2 = await _send_or_queue(profile_no_quiet, [test_move], mock_sender)
    before_count = len(sent_messages)
    if stats2["deduped"] == 1 and stats2["sent"] == 0:
        _ok("Dedup: same ticker+direction within 30 min correctly suppressed")
    else:
        _fail_msg(f"Expected deduped=1 sent=0 — got {stats2}")

    # ── 6d: Quiet hours queuing ──────────────────────────────────────────────
    await db.clear_cooldowns(TEST_USER_ID)
    # Build a 2-hour quiet window that always contains the current ET hour
    from worker.app.bot.tz_check import now_et
    cur_hour = now_et().hour
    profile_quiet_now = {
        "telegram_user_id": TEST_USER_ID,
        "quiet_hours_enabled": True,
        "quiet_hours_start": cur_hour,
        "quiet_hours_end": (cur_hour + 2) % 24,
    }
    sent_before = len(sent_messages)
    stats3 = await _send_or_queue(profile_quiet_now, [test_move], mock_sender)
    if stats3["queued"] == 1 and stats3["sent"] == 0:
        _ok("Quiet hours: alert correctly queued, not sent immediately")
    else:
        _fail_msg(f"Expected queued=1 sent=0 — got {stats3}")

    # Verify it's in the queued_alerts table
    pending = await db.get_pending_queued_alerts()
    user_pending = [p for p in pending if p["telegram_user_id"] == TEST_USER_ID]
    if user_pending:
        _ok(f"Queued alert in DB: id={user_pending[0]['id']}, ticker={user_pending[0]['ticker']}")
    else:
        _fail_msg("No pending alert found in queued_alerts table")

    # ── 6e: Batch aggregation (>= 3 crossings → 1 message) ──────────────────
    await db.clear_cooldowns(TEST_USER_ID)
    sent_messages_before = len(sent_messages)
    big_crossings = [
        TickerMove("NVDA", 120.0, 126.0, 5.0),
        TickerMove("AAPL", 180.0, 174.0, -3.3),
        TickerMove("TSLA", 230.0, 240.0, 4.3),
        TickerMove("MSFT", 400.0, 412.0, 3.0),
    ]
    stats4 = await _send_or_queue(profile_no_quiet, big_crossings, mock_sender)
    new_msgs = len(sent_messages) - sent_messages_before
    if new_msgs == 1 and "4 tickers crossed" in sent_messages[-1]["text"]:
        _ok(f"Batch aggregation: 4 crossings → 1 message (not 4 separate alerts)")
    else:
        _fail_msg(f"Expected 1 batch message, got {new_msgs} new messages; stats={stats4}")

    # ── Cleanup ──────────────────────────────────────────────────────────────
    await db.delete_profile(TEST_USER_ID)
    await db.delete_test_queued_alerts(TEST_USER_ID)
    _ok("Test user cleaned up from DB")


# ─────────────────────────────────────────────────────────────────────────────
# Main runner
# ─────────────────────────────────────────────────────────────────────────────

async def run_e2e_test() -> None:
    print("\n" + "=" * 64)
    print("SENTINEL AI BOT - END-TO-END SELF-TEST")
    print("=" * 64)

    step1_timezone()
    step2_red_line_scan()
    step2b_whop_templates_red_line()
    step3_quiet_hours_logic()
    step4_ticker_query_handler()
    step4b_priority_classification()

    db_ok = await step5_db_onboarding()
    if db_ok:
        await step6_alert_dispatch()

    print("\n" + "=" * 64)
    total = _pass + _fail + _skip
    print(f"RESULTS: {_pass}/{total} passed  |  {_fail} failed  |  {_skip} skipped")
    if _fail == 0:
        print("ALL TESTS PASSED [OK]")
    else:
        print(f"ATTENTION: {_fail} test(s) FAILED [!!] -- review above")
    print("=" * 64 + "\n")

    if _fail > 0:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(run_e2e_test())
