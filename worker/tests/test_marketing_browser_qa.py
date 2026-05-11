"""Unit tests for browser_qa — covers pure HTML detectors, screenshot path
derivation, orchestration with injected fetch, and Feishu CTA extraction.

No real browser is launched in this test suite — `check_landing_url` accepts
an injectable `fetch_fn` so we can return synthetic HTML.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app.marketing.browser_qa import (
    BrowserCheckResult,
    FeishuCTARow,
    check_landing_url,
    derive_screenshot_path,
    detect_disclaimer,
    detect_email_gate,
    detect_telegram_cta,
    detect_ticker_reference,
    extract_cta_rows,
)


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Pure HTML detectors
# ---------------------------------------------------------------------------


CLEAN_HTML = """
<!doctype html><html><head><title>Sentinel AI — $NVDA</title></head>
<body>
  <h1>$NVDA</h1>
  <form>
    <input type="email" placeholder="you@example.com" />
    <button>Email me the report</button>
  </form>
  <a href="https://t.me/SentinelAI_signals">Track $NVDA on Telegram →</a>
  <footer>Context, not financial advice. Sentinel AI provides analysis.</footer>
</body></html>
"""


def test_detect_email_gate_finds_input() -> None:
    assert detect_email_gate(CLEAN_HTML)
    assert detect_email_gate('<input  type="email"  />')
    assert detect_email_gate("<INPUT TYPE='email'>")


def test_detect_email_gate_misses_text_input() -> None:
    assert not detect_email_gate('<input type="text" />')
    assert not detect_email_gate("<form><button>submit</button></form>")


def test_detect_disclaimer_accepts_known_phrases() -> None:
    assert detect_disclaimer("blah Context, not financial advice. blah")
    assert detect_disclaimer("Not financial advice")
    assert detect_disclaimer("Not investment advice")


def test_detect_disclaimer_rejects_unrelated_text() -> None:
    assert not detect_disclaimer("This page contains no disclaimer text")


def test_detect_telegram_cta_text_or_link() -> None:
    assert detect_telegram_cta("Track $NVDA on Telegram →")
    assert detect_telegram_cta('<a href="https://t.me/foo">bar</a>')
    assert detect_telegram_cta("Join our Telegram channel")
    assert not detect_telegram_cta("no social CTA here")


def test_detect_ticker_reference_brand_or_symbol() -> None:
    assert detect_ticker_reference("powered by Sentinel AI")
    assert detect_ticker_reference("<h1>$NVDA</h1>", ticker="nvda")
    assert detect_ticker_reference("<h1>$nvda</h1>", ticker="NVDA")
    assert not detect_ticker_reference("random page text", ticker="NVDA")


# ---------------------------------------------------------------------------
# Screenshot path
# ---------------------------------------------------------------------------


def test_derive_screenshot_path_format(tmp_path: Path) -> None:
    p = derive_screenshot_path("https://sentinel.example.com/stocks/NVDA", tmp_path)
    assert p.parent == tmp_path
    assert p.suffix == ".png"
    name = p.name
    assert "sentinel.example.com" in name
    assert "stocks_NVDA" in name


def test_derive_screenshot_path_root_url(tmp_path: Path) -> None:
    p = derive_screenshot_path("https://sentinel.example.com/", tmp_path)
    assert "sentinel.example.com" in p.name


def test_derive_screenshot_path_truncates_long_slug(tmp_path: Path) -> None:
    long = "https://x.example.com/" + "a/" * 100 + "end"
    p = derive_screenshot_path(long, tmp_path)
    # 80-char slug cap + timestamp = total filename ≤ 150 chars
    assert len(p.name) < 200


# ---------------------------------------------------------------------------
# check_landing_url orchestration (with injected fetch_fn)
# ---------------------------------------------------------------------------


def _fetch_factory(html: str, status: int = 200, title: str = "Sentinel AI — $NVDA"):
    async def fake(url, screenshot_path):
        return status, title, html

    return fake


def test_check_landing_url_clean_passes() -> None:
    result = _run(
        check_landing_url(
            "https://sentinel.example.com/stocks/NVDA",
            fetch_fn=_fetch_factory(CLEAN_HTML),
            expected_ticker="NVDA",
        )
    )
    assert isinstance(result, BrowserCheckResult)
    assert result.ok is True
    assert result.status_code == 200
    assert result.title is not None
    assert result.checks["email_gate"] is True
    assert result.checks["disclaimer"] is True
    assert result.checks["ticker_reference"] is True
    assert result.checks["http_ok"] is True


def test_check_landing_url_missing_email_gate_fails() -> None:
    no_email = CLEAN_HTML.replace('<input type="email" placeholder="you@example.com" />', "")
    result = _run(
        check_landing_url(
            "https://x/y",
            fetch_fn=_fetch_factory(no_email),
            expected_ticker="NVDA",
        )
    )
    assert result.ok is False
    assert result.checks["email_gate"] is False
    assert result.checks["disclaimer"] is True  # still has disclaimer


def test_check_landing_url_missing_disclaimer_fails() -> None:
    no_disc = CLEAN_HTML.replace("Context, not financial advice.", "")
    result = _run(
        check_landing_url(
            "https://x/y",
            fetch_fn=_fetch_factory(no_disc),
            expected_ticker="NVDA",
        )
    )
    assert result.ok is False
    assert result.checks["disclaimer"] is False


def test_check_landing_url_http_500_fails() -> None:
    result = _run(
        check_landing_url(
            "https://x/y",
            fetch_fn=_fetch_factory(CLEAN_HTML, status=500),
            expected_ticker="NVDA",
        )
    )
    assert result.ok is False
    assert result.checks["http_ok"] is False


def test_check_landing_url_require_telegram_cta_failure() -> None:
    no_tg = CLEAN_HTML.replace("Telegram", "Discord").replace("t.me", "discord.gg")
    result = _run(
        check_landing_url(
            "https://x/y",
            fetch_fn=_fetch_factory(no_tg),
            require_telegram_cta=True,
            expected_ticker="NVDA",
        )
    )
    assert result.ok is False
    assert result.checks["telegram_cta"] is False


def test_check_landing_url_can_skip_optional_checks() -> None:
    minimal = "<html><title>x</title><body>Sentinel AI ok</body></html>"
    result = _run(
        check_landing_url(
            "https://x/y",
            fetch_fn=_fetch_factory(minimal),
            require_email_gate=False,
            require_disclaimer=False,
        )
    )
    assert result.ok is True
    assert result.checks["email_gate"] is False
    assert result.checks["disclaimer"] is False


def test_check_landing_url_fetch_exception_returns_error_result() -> None:
    async def boom(url, screenshot_path):
        raise RuntimeError("network unreachable")

    result = _run(check_landing_url("https://x/y", fetch_fn=boom, expected_ticker="NVDA"))
    assert result.ok is False
    assert result.error is not None and "network unreachable" in result.error
    assert result.status_code is None


def test_check_landing_url_screenshot_path_passed_to_fetch(tmp_path: Path) -> None:
    captured = {}

    async def capture(url, screenshot_path):
        captured["path"] = screenshot_path
        return 200, "ok", CLEAN_HTML

    _run(
        check_landing_url(
            "https://sentinel.example.com/stocks/NVDA",
            fetch_fn=capture,
            screenshot_dir=str(tmp_path),
            expected_ticker="NVDA",
        )
    )
    assert captured["path"] is not None
    assert isinstance(captured["path"], Path)
    assert captured["path"].parent == tmp_path


# ---------------------------------------------------------------------------
# Feishu Content Queue extraction
# ---------------------------------------------------------------------------


def _bitable_record(
    record_id: str,
    *,
    content_id: str,
    ticker: str,
    platform: str,
    review_status: str,
    cta_url: object,
) -> dict:
    return {
        "record_id": record_id,
        "fields": {
            "content_id": content_id,
            "ticker": ticker,
            "platform": platform,
            "review_status": review_status,
            "cta_url": cta_url,
        },
    }


def test_extract_cta_rows_handles_dict_url_field() -> None:
    records = [
        _bitable_record(
            "rec1",
            content_id="CT-1",
            ticker="NVDA",
            platform="Telegram",
            review_status="Approved",
            cta_url={"link": "https://sentinel.example.com/stocks/NVDA", "text": "..."},
        )
    ]
    rows = extract_cta_rows(records)
    assert len(rows) == 1
    assert isinstance(rows[0], FeishuCTARow)
    assert rows[0].cta_url == "https://sentinel.example.com/stocks/NVDA"
    assert rows[0].ticker == "NVDA"
    assert rows[0].platform == "Telegram"


def test_extract_cta_rows_filters_by_status() -> None:
    records = [
        _bitable_record("a", content_id="A", ticker="A", platform="X",
                        review_status="Pending", cta_url="https://a"),
        _bitable_record("b", content_id="B", ticker="B", platform="X",
                        review_status="Rejected", cta_url="https://b"),
        _bitable_record("c", content_id="C", ticker="C", platform="X",
                        review_status="Failed", cta_url="https://c"),
        _bitable_record("d", content_id="D", ticker="D", platform="X",
                        review_status="Published", cta_url="https://d"),
    ]
    rows = extract_cta_rows(records)
    ids = [r.record_id for r in rows]
    # Pending + Published in, Rejected + Failed out
    assert "a" in ids
    assert "d" in ids
    assert "b" not in ids
    assert "c" not in ids


def test_extract_cta_rows_drops_missing_or_relative_urls() -> None:
    records = [
        _bitable_record("good", content_id="X", ticker="X", platform="X",
                        review_status="Approved", cta_url="https://ok"),
        _bitable_record("none", content_id="Y", ticker="Y", platform="X",
                        review_status="Approved", cta_url=None),
        _bitable_record("rel", content_id="Z", ticker="Z", platform="X",
                        review_status="Approved", cta_url="/stocks/Z"),
    ]
    rows = extract_cta_rows(records)
    assert [r.record_id for r in rows] == ["good"]


def test_extract_cta_rows_respects_limit() -> None:
    records = [
        _bitable_record(f"r{i}", content_id=f"CT-{i}", ticker="X", platform="Y",
                        review_status="Approved", cta_url=f"https://x/{i}")
        for i in range(20)
    ]
    rows = extract_cta_rows(records, limit=5)
    assert len(rows) == 5
    assert [r.record_id for r in rows] == [f"r{i}" for i in range(5)]


# ---------------------------------------------------------------------------
# Playwright availability guard (smoke — no actual browser)
# ---------------------------------------------------------------------------


def test_check_landing_url_returns_error_when_playwright_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Simulate Playwright import failure: result should describe the missing
    dependency without raising."""
    import app.marketing.browser_qa as mod

    monkeypatch.setattr(mod, "PLAYWRIGHT_AVAILABLE", False)
    # When no fetch_fn is injected AND Playwright is unavailable, return early.
    result = _run(check_landing_url("https://x/y"))
    assert result.ok is False
    assert result.error == "playwright_not_installed"
    assert result.status_code is None
