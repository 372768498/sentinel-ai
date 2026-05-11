from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from app.marketing.catalysts import Catalyst, latest_catalyst


def test_catalyst_headline_8k():
    c = Catalyst(
        ticker="AAPL", form="8-K", filing_date=date(2026, 5, 1),
        accession_no="0001-26-1", homepage_url="https://sec.gov/x",
        primary_doc_url=None,
    )
    assert c.headline() == "filed an 8-K disclosure on 1 May"


def test_catalyst_headline_10q():
    c = Catalyst(
        ticker="NVDA", form="10-Q", filing_date=date(2026, 4, 28),
        accession_no="x", homepage_url="https://sec.gov/y",
        primary_doc_url=None,
    )
    assert "10-Q quarterly report" in c.headline()
    assert "28 Apr" in c.headline()


def test_catalyst_headline_unknown_form():
    c = Catalyst(
        ticker="TSLA", form="13D", filing_date=date(2026, 5, 9),
        accession_no="x", homepage_url="https://sec.gov/z",
        primary_doc_url=None,
    )
    headline = c.headline()
    assert "13D" in headline


@pytest.mark.asyncio
async def test_latest_catalyst_returns_none_on_empty(monkeypatch):
    def _fake_sync(*args, **kwargs):
        return None
    monkeypatch.setattr("app.marketing.catalysts._fetch_latest_sync", _fake_sync)
    result = await latest_catalyst("AAPL", timeout_s=1.0)
    assert result is None


@pytest.mark.asyncio
async def test_latest_catalyst_returns_catalyst_on_hit(monkeypatch):
    fixture = Catalyst(
        ticker="AAPL", form="8-K", filing_date=date(2026, 5, 1),
        accession_no="x", homepage_url="https://sec.gov/x",
        primary_doc_url="https://sec.gov/y.htm",
    )
    def _fake_sync(*args, **kwargs):
        return fixture
    monkeypatch.setattr("app.marketing.catalysts._fetch_latest_sync", _fake_sync)
    result = await latest_catalyst("AAPL", timeout_s=1.0)
    assert result is fixture
