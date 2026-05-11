from datetime import date

import pytest

from app.marketing.tracker import build_deep_link, build_payload, parse_payload


def test_payload_format():
    payload = build_payload(
        source="xtw", score=92, ticker="AAPL", day=date(2026, 5, 9)
    )
    assert payload == "src_xtw_score92_aapl_20260509"


def test_payload_round_trip():
    payload = build_payload(
        source="rdt", score=80, ticker="TSLA", day=date(2026, 5, 9)
    )
    parsed = parse_payload(payload)
    assert parsed == {
        "source": "rdt",
        "score": 80,
        "ticker": "TSLA",
        "day": "20260509",
    }


def test_deep_link_format():
    link = build_deep_link(
        "SentinelAIProChannelBot", "src_xtw_score92_aapl_20260509"
    )
    assert link == "https://t.me/SentinelAIProChannelBot?start=src_xtw_score92_aapl_20260509"


def test_deep_link_strips_at():
    link = build_deep_link("@SentinelAIProChannelBot", "x")
    assert "@" not in link.split("/")[-1]


def test_invalid_payload_returns_none():
    assert parse_payload("garbage") is None
    assert parse_payload("xtw_score92_aapl") is None  # missing date
    assert parse_payload("xtw_aapl_20260509") is None  # missing score


def test_score_out_of_range_rejected():
    with pytest.raises(ValueError):
        build_payload(source="x", score=150, ticker="AAPL")


def test_payload_strips_special_chars_in_ticker():
    # BRK.B → brkb; the bot regex only accepts [a-z]{1,5}
    p = build_payload(source="reddit", score=85, ticker="BRK.B", day=date(2026, 5, 9))
    assert p == "src_reddit_score85_brkb_20260509"
    assert len(p) <= 64


def test_payload_matches_bot_regex():
    # Sanity: payloads we build MUST match the bot's START_PAYLOAD_RE shape.
    from app.bot.handlers.onboarding import START_PAYLOAD_RE

    payload = build_payload(source="xtw", score=92, ticker="AAPL", day=date(2026, 5, 9))
    assert START_PAYLOAD_RE.match(payload), f"payload {payload!r} won't match bot regex"
