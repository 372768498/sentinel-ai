"""Best-effort market-wide brief for the free Daily Radar email."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Mapping, Sequence

import yfinance as yf


INDEX_TICKERS = ("SPY", "QQQ", "DIA", "IWM", "^VIX", "^TNX")
SECTOR_TICKERS: Mapping[str, str] = {
    "XLK": "Technology",
    "XLE": "Energy",
    "XLF": "Financials",
    "XLV": "Health Care",
    "XLY": "Consumer Discretionary",
    "XLP": "Consumer Staples",
    "XLI": "Industrials",
    "XLC": "Communication Services",
    "XLU": "Utilities",
    "XLB": "Materials",
    "XLRE": "Real Estate",
}
HOT_TICKERS = (
    "NVDA",
    "TSLA",
    "AAPL",
    "MSFT",
    "AMD",
    "AMZN",
    "META",
    "GOOGL",
    "COIN",
    "PLTR",
    "AVGO",
    "NFLX",
)


@dataclass(frozen=True)
class MarketRow:
    ticker: str
    name: str
    price: float | None
    change_pct: float | None
    volume: int | None = None


def render_market_brief_text() -> str:
    """Return a market brief, or an empty string when data is unavailable."""
    try:
        return _render_market_brief_text_sync()
    except Exception:
        return ""


async def render_market_brief_text_async() -> str:
    """Async wrapper so scheduled email jobs do not block the event loop."""
    return await asyncio.to_thread(render_market_brief_text)


def _render_market_brief_text_sync() -> str:
    index_rows = _quote_rows(INDEX_TICKERS)
    sector_rows = _quote_rows(tuple(SECTOR_TICKERS))
    hot_rows = _quote_rows(HOT_TICKERS)
    gainers = _screen_rows("day_gainers", count=10)
    losers = _screen_rows("day_losers", count=10)
    active = _screen_rows("most_actives", count=10)

    sections: list[str] = []
    snapshot = _market_snapshot(index_rows)
    if snapshot:
        sections.append(snapshot)

    sector_block = _sector_block(sector_rows)
    if sector_block:
        sections.append(sector_block)

    movers_block = _movers_block(gainers, losers)
    if movers_block:
        sections.append(movers_block)

    active_block = _active_block(active, hot_rows)
    if active_block:
        sections.append(active_block)

    sentry = _sentinel_watch(sector_rows, index_rows, hot_rows)
    if sentry:
        sections.append(sentry)

    next_watch = _next_watch(index_rows, sector_rows, hot_rows)
    if next_watch:
        sections.append(next_watch)

    if len(sections) < 2:
        return ""
    return "\n\n".join(sections)


def _quote_rows(tickers: Sequence[str]) -> list[MarketRow]:
    data = yf.download(
        list(tickers),
        period="7d",
        interval="1d",
        group_by="ticker",
        auto_adjust=False,
        progress=False,
        threads=True,
    )
    rows: list[MarketRow] = []
    for ticker in tickers:
        frame = data[ticker] if len(tickers) > 1 else data
        close = frame.get("Close")
        volume = frame.get("Volume")
        if close is None:
            continue
        close = close.dropna()
        if len(close) < 2:
            continue
        last = float(close.iloc[-1])
        prev = float(close.iloc[-2])
        change_pct = ((last - prev) / prev) * 100 if prev else None
        vol_value = None
        if volume is not None and not volume.dropna().empty:
            vol_value = int(volume.dropna().iloc[-1])
        rows.append(
            MarketRow(
                ticker=ticker,
                name=SECTOR_TICKERS.get(ticker, ticker),
                price=last,
                change_pct=change_pct,
                volume=vol_value,
            )
        )
    return rows


def _screen_rows(screen: str, *, count: int) -> list[MarketRow]:
    data = yf.screen(screen, count=count)
    quotes = data.get("quotes", []) if isinstance(data, dict) else []
    rows: list[MarketRow] = []
    for q in quotes[:count]:
        symbol = str(q.get("symbol") or "").upper()
        if not symbol:
            continue
        rows.append(
            MarketRow(
                ticker=symbol,
                name=str(q.get("shortName") or q.get("longName") or symbol),
                price=_float_or_none(q.get("regularMarketPrice")),
                change_pct=_float_or_none(q.get("regularMarketChangePercent")),
                volume=_int_or_none(q.get("regularMarketVolume")),
            )
        )
    return rows


def _market_snapshot(rows: Sequence[MarketRow]) -> str:
    by_ticker = {r.ticker: r for r in rows}
    parts = []
    for ticker in ("SPY", "QQQ", "DIA", "IWM"):
        row = by_ticker.get(ticker)
        if row and row.change_pct is not None:
            parts.append(f"{ticker} {_pct(row.change_pct)}")
    vix = by_ticker.get("^VIX")
    tnx = by_ticker.get("^TNX")
    extras = []
    if vix and vix.price is not None and vix.change_pct is not None:
        vix_note = "below 20 / 仍低于 20" if vix.price < 20 else "above 20 / 高于 20"
        extras.append(f"VIX {vix.price:.2f} ({_pct(vix.change_pct)}, {vix_note})")
    if tnx and tnx.price is not None:
        extras.append(f"10Y yield / 10年期美债收益率 {tnx.price:.2f}%")
    if not parts and not extras:
        return ""
    return (
        "MARKET SNAPSHOT / 市场总览\n"
        + "- Indexes / 指数: "
        + " · ".join(parts)
        + ("\n- Risk floor / 风险温度: " + " · ".join(extras) if extras else "")
    )


def _sector_block(rows: Sequence[MarketRow]) -> str:
    valid = [r for r in rows if r.change_pct is not None]
    if not valid:
        return ""
    ranked = sorted(valid, key=lambda r: r.change_pct or 0, reverse=True)
    leaders = " · ".join(_row_pct(r) for r in ranked[:3])
    laggards = " · ".join(_row_pct(r) for r in ranked[-3:])
    return (
        "SECTOR ROTATION / 板块轮动\n"
        f"- Leaders / 强势板块: {leaders}\n"
        f"- Laggards / 弱势板块: {laggards}"
    )


def _movers_block(gainers: Sequence[MarketRow], losers: Sequence[MarketRow]) -> str:
    if not gainers and not losers:
        return ""
    lines = ["TOP MOVERS / 涨跌幅前 10"]
    if gainers:
        lines.append("- Gainers / 涨幅榜: " + " · ".join(_row_pct(r) for r in gainers[:10]))
    if losers:
        lines.append("- Losers / 跌幅榜: " + " · ".join(_row_pct(r) for r in losers[:10]))
    if gainers or losers:
        lines.append(
            "- Catalyst read / 异动归因: free brief shows the move / 免费版先看异动；"
            "Pro adds the full catalyst trail / Pro 补完整催化剂链路。"
        )
    return "\n".join(lines)


def _active_block(active: Sequence[MarketRow], hot_rows: Sequence[MarketRow]) -> str:
    hot = [r for r in hot_rows if r.change_pct is not None]
    lines = ["MEGACAPS + ACTIVE FLOW / 巨头与异常活跃"]
    if active:
        lines.append(
            "- Most active / 成交活跃: "
            + " · ".join(f"{r.ticker} {_pct(r.change_pct)} ({_vol(r.volume)})" for r in active[:8])
        )
    if hot:
        lines.append(
            "- Watch names / 热门大票: "
            + " · ".join(_row_pct(r) for r in hot[:8])
        )
    return "\n".join(lines) if len(lines) > 1 else ""


def _sentinel_watch(
    sectors: Sequence[MarketRow],
    indexes: Sequence[MarketRow],
    hot_rows: Sequence[MarketRow],
) -> str:
    valid_sectors = [r for r in sectors if r.change_pct is not None]
    if len(valid_sectors) >= 2:
        ranked = sorted(valid_sectors, key=lambda r: r.change_pct or 0, reverse=True)
        spread = (ranked[0].change_pct or 0) - (ranked[-1].change_pct or 0)
        return (
            "SENTINEL WATCH / 今日盯防\n"
            f"- Biggest sector spread / 最大板块剪刀差: {ranked[0].ticker} {_pct(ranked[0].change_pct)} "
            f"vs {ranked[-1].ticker} {_pct(ranked[-1].change_pct)} = {spread:.2f} pct points / 百分点。\n"
            "- What it means / 含义: rotation may matter more than a single-stock headline / "
            "今天可能是板块轮动比单只股票新闻更重要。"
        )
    weak_hot = [r for r in hot_rows if r.change_pct is not None and r.change_pct < -3]
    if weak_hot:
        return (
            "SENTINEL WATCH / 今日盯防\n"
            "- Mega-cap pressure / 大票压力: "
            + " · ".join(_row_pct(r) for r in weak_hot[:3])
        )
    weak_indexes = [r for r in indexes if r.change_pct is not None and r.change_pct < -1]
    if weak_indexes:
        return (
            "SENTINEL WATCH / 今日盯防\n"
            "- Index pressure / 指数压力: "
            + " · ".join(_row_pct(r) for r in weak_indexes[:3])
        )
    return ""


def _next_watch(
    indexes: Sequence[MarketRow],
    sectors: Sequence[MarketRow],
    hot_rows: Sequence[MarketRow],
) -> str:
    by_ticker = {r.ticker: r for r in indexes}
    qqq = by_ticker.get("QQQ")
    spy = by_ticker.get("SPY")
    ranked_sectors = sorted(
        [r for r in sectors if r.change_pct is not None],
        key=lambda r: r.change_pct or 0,
        reverse=True,
    )
    hot = [r for r in hot_rows if r.change_pct is not None]
    lines = ["NEXT SESSION CHECKLIST / 明早先看"]
    if qqq and spy:
        lines.append(f"- QQQ vs SPY: QQQ {_pct(qqq.change_pct)} vs SPY {_pct(spy.change_pct)}")
    if ranked_sectors:
        lines.append(
            f"- Sector follow-through / 板块延续性: {ranked_sectors[0].ticker} vs {ranked_sectors[-1].ticker}"
        )
    if hot:
        lines.append("- Megacap confirmation / 大票确认: " + " · ".join(r.ticker for r in hot[:4]))
    return "\n".join(lines) if len(lines) > 1 else ""


def _row_pct(row: MarketRow) -> str:
    return f"{row.ticker} {_pct(row.change_pct)}"


def _pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:+.2f}%"


def _vol(value: int | None) -> str:
    if value is None:
        return "vol n/a"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"{value / 1_000:.1f}K"
    return str(value)


def _float_or_none(value) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


def _int_or_none(value) -> int | None:
    return int(value) if isinstance(value, (int, float)) else None
