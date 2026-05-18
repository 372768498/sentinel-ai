"""Tests for the free email market-wide brief."""
from __future__ import annotations

from app.marketing import market_brief
from app.marketing.market_brief import MarketRow


def test_market_brief_renders_dense_market_context(
    monkeypatch,
) -> None:
    def fake_quote_rows(tickers):
        rows = {
            "SPY": MarketRow("SPY", "SPY", 739.17, -1.20, 50_000_000),
            "QQQ": MarketRow("QQQ", "QQQ", 708.93, -1.51, 60_000_000),
            "DIA": MarketRow("DIA", "DIA", 495.37, -1.08, 20_000_000),
            "IWM": MarketRow("IWM", "IWM", 277.60, -2.41, 30_000_000),
            "^VIX": MarketRow("^VIX", "^VIX", 18.43, 6.78, None),
            "^TNX": MarketRow("^TNX", "^TNX", 4.59, 3.00, None),
            "XLE": MarketRow("XLE", "Energy", 100.0, 2.36, 10_000_000),
            "XLK": MarketRow("XLK", "Technology", 100.0, -1.81, 10_000_000),
            "XLF": MarketRow("XLF", "Financials", 100.0, -0.37, 10_000_000),
            "XLU": MarketRow("XLU", "Utilities", 100.0, -2.29, 10_000_000),
            "NVDA": MarketRow("NVDA", "NVDA", 180.0, -4.42, 180_000_000),
            "TSLA": MarketRow("TSLA", "TSLA", 424.0, -4.75, 95_000_000),
            "AAPL": MarketRow("AAPL", "AAPL", 210.0, 0.68, 54_000_000),
            "MSFT": MarketRow("MSFT", "MSFT", 425.0, 3.05, 40_000_000),
        }
        return [rows[t] for t in tickers if t in rows]

    def fake_screen_rows(screen, *, count):
        if screen == "day_gainers":
            return [
                MarketRow("SEDG", "SolarEdge", 35.0, 22.93, 14_000_000),
                MarketRow("FIG", "Figma", 60.0, 13.24, 77_000_000),
            ]
        if screen == "day_losers":
            return [
                MarketRow("POET", "POET", 4.0, -22.36, 100_000_000),
                MarketRow("TNGX", "Tango", 7.0, -17.33, 6_000_000),
            ]
        return [
            MarketRow("NVDA", "NVIDIA", 180.0, -4.42, 180_000_000),
            MarketRow("POET", "POET", 4.0, -22.36, 100_000_000),
        ]

    monkeypatch.setattr(market_brief, "_quote_rows", fake_quote_rows)
    monkeypatch.setattr(market_brief, "_screen_rows", fake_screen_rows)

    out = market_brief.render_market_brief_text()

    assert "一、昨日 Sentinel 提示兑现" in out
    assert "二、今日市场总览" in out
    assert "三、板块强弱榜" in out
    assert "四、今日涨幅前10" in out
    assert "五、今日跌幅前10" in out
    assert "六、巨头 + 异常活跃" in out
    assert "七、Sentinel 今日盯防" in out
    assert "八、明早 Sentinel 会先看" in out
    assert "九、Sentinel 一句话总结" in out
    assert "SEDG\tSolarEdge" in out
    assert "+22.93%" in out
    assert "POET\tPOET Technologies" in out
    assert "-22.36%" in out
    assert "XLE（能源板块）+2.36%" in out
    assert "XLK（科技板块）-1.81%" in out
    assert "指标\t中文解释\t最新值\t涨跌" in out
    assert "🔒 其余 7 只完整异动归因" in out
