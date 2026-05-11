import pytest

from app.marketing.composer import Composer
from app.marketing.personas import ALL_PERSONAS, SEC_FILING_REPORTER
from app.marketing.publisher import Publisher
from app.marketing.x_client import XClient


@pytest.mark.asyncio
async def test_publisher_dry_run_e2e():
    pub = Publisher(
        composer=Composer(dry_run=True),
        x_client=XClient(dry_run=True),
        bot_username="SentinelAIProChannelBot",
    )
    out = await pub.publish_alert(
        ticker="NVDA",
        change_pct=4.5,
        score=90,
        headline="filed an 8-K disclosing $3.4B buyback",
        source_url="https://www.sec.gov/x",
        persona=SEC_FILING_REPORTER,
    )
    assert out.redline_ok, out.redline_violations
    assert out.deep_link in out.text
    assert out.post_result.dry_run is True
    assert out.post_result.posted is False
    assert "xtw_score90_nvda_" in out.deep_link


@pytest.mark.asyncio
async def test_publisher_persona_rotation_deterministic():
    pub = Publisher(
        composer=Composer(dry_run=True),
        x_client=XClient(dry_run=True),
        bot_username="bot",
    )
    out_a = await pub.publish_alert(
        ticker="NVDA", change_pct=2.0, score=90,
        headline="x", source_url="https://x.com",
    )
    out_b = await pub.publish_alert(
        ticker="NVDA", change_pct=2.0, score=90,
        headline="x", source_url="https://x.com",
    )
    assert out_a.persona == out_b.persona


@pytest.mark.asyncio
async def test_publisher_different_tickers_can_get_different_personas():
    pub = Publisher(
        composer=Composer(dry_run=True),
        x_client=XClient(dry_run=True),
        bot_username="bot",
    )
    seen = set()
    for ticker in ("AAPL", "TSLA", "NVDA", "META", "AMZN", "MSFT", "GOOG", "AMD"):
        out = await pub.publish_alert(
            ticker=ticker, change_pct=2.0, score=85,
            headline="x", source_url="https://x.com",
        )
        seen.add(out.persona)
    assert len(seen) >= 2  # rotation actually rotates


@pytest.mark.asyncio
async def test_publisher_redline_metadata_propagates():
    pub = Publisher(
        composer=Composer(dry_run=True),
        x_client=XClient(dry_run=True),
        bot_username="bot",
    )
    out = await pub.publish_alert(
        ticker="AAPL", change_pct=1.5, score=80,
        headline="reported", source_url="https://www.sec.gov/x",
    )
    assert out.redline_ok
    assert out.redline_violations == ()
