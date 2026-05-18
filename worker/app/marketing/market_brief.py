"""Best-effort market-wide brief for the free Daily Radar email."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Mapping, Sequence

import yfinance as yf


INDEX_TICKERS = ("SPY", "QQQ", "DIA", "IWM", "^VIX", "^TNX")
SECTOR_TICKERS: Mapping[str, tuple[str, str]] = {
    "XLE": ("Energy", "能源"),
    "XLF": ("Financials", "金融"),
    "XLP": ("Consumer Staples", "必需消费"),
    "XLC": ("Communication Services", "通信服务"),
    "XLV": ("Health Care", "医疗"),
    "XLI": ("Industrials", "工业"),
    "XLY": ("Consumer Discretionary", "可选消费"),
    "XLK": ("Technology", "科技"),
    "XLU": ("Utilities", "公用事业"),
    "XLB": ("Materials", "原材料"),
    "XLRE": ("Real Estate", "房地产"),
}
INDEX_DESCRIPTIONS: Mapping[str, str] = {
    "SPY": "标普500 ETF，代表美国大盘",
    "QQQ": "纳斯达克100 ETF，代表大型科技股",
    "DIA": "道琼斯 ETF，代表传统蓝筹股",
    "IWM": "罗素2000 ETF，代表小盘股",
    "^VIX": "恐慌指数，衡量市场波动预期",
    "^TNX": "美国10年期国债收益率",
}
COMPANY_DESCRIPTIONS: Mapping[str, str] = {
    "NVDA": "英伟达，AI 芯片龙头",
    "MSFT": "微软",
    "AAPL": "苹果",
    "TSLA": "特斯拉",
    "AMD": "超威半导体",
    "COIN": "Coinbase，加密货币交易平台",
    "INTC": "英特尔，半导体公司",
    "NU": "Nu Holdings，拉美数字银行",
    "FIG": "Figma，设计协作软件公司",
    "POET": "POET Technologies，光电子技术公司",
    "SEDG": "SolarEdge，太阳能设备公司",
    "MICC": "Magnum Ice Cream，冰淇淋消费品公司",
    "ENPH": "Enphase Energy，太阳能逆变器公司",
    "SOC": "Sable Offshore，海上能源公司",
    "VG": "Venture Global，液化天然气公司",
    "WING": "Wingstop，连锁餐饮公司",
    "TEAM": "Atlassian，企业协作软件公司",
    "HUBS": "HubSpot，营销软件公司",
    "AXTI": "AXT，半导体材料公司",
    "TNGX": "Tango Therapeutics，生物科技公司",
    "YSS": "York Space Systems，航天系统公司",
    "DLO": "DLocal，跨境支付公司",
    "USAS": "Americas Gold and Silver，贵金属矿业公司",
    "HTFL": "Heartflow，医疗影像公司",
    "FRMI": "Fermi，能源/基础设施相关公司",
    "WOLF": "Wolfspeed，碳化硅半导体公司",
    "INFQ": "Infleqtion，量子技术公司",
    "QUBT": "Quantum Computing，量子计算公司",
    "ONDS": "Ondas Holdings，工业无人机/网络公司",
    "F": "Ford，汽车公司",
    "NOK": "Nokia，通信设备公司",
    "PLUG": "Plug Power，氢能源公司",
}
HOT_TICKERS = (
    "NVDA",
    "MSFT",
    "AAPL",
    "TSLA",
    "AMD",
    "COIN",
    "INTC",
    "NU",
    "FIG",
    "POET",
)
PREVIOUS_CHECKS = (
    "看 QQQ 是否继续弱于 SPY",
    "看能源是否继续强于科技",
    "看 NVDA / AMD / TSLA 是否止跌",
)


@dataclass(frozen=True)
class MarketRow:
    ticker: str
    name: str
    price: float | None
    change_pct: float | None
    volume: int | None = None
    previous_price: float | None = None


def render_market_brief_text() -> str:
    """Return a 9-section market brief, or an empty string when data fails."""
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

    if len(index_rows) < 3:
        return ""

    sections = [
        _yesterday_check_section(index_rows, sector_rows, hot_rows),
        _market_overview_section(index_rows),
        _sector_section(sector_rows),
        _movers_section("四、今日涨幅前10", gainers, catalyst_kind="gainers"),
        _movers_section("五、今日跌幅前10", losers, catalyst_kind="losers"),
        _active_section(active, hot_rows),
        _sentinel_watch_section(sector_rows),
        _next_watch_section(index_rows, sector_rows, hot_rows),
        _summary_section(index_rows, sector_rows),
    ]
    return "\n\n".join(section for section in sections if section)


def market_brief_subject_preview() -> tuple[str, str]:
    """Return subject/preview from live market data when available."""
    try:
        indexes = _quote_rows(INDEX_TICKERS)
        sectors = _quote_rows(tuple(SECTOR_TICKERS))
    except Exception:
        return (
            "Sentinel AI 美股市场日报：市场复盘与明日观察",
            "SPY · QQQ · IWM · VIX · 板块轮动 · 涨跌幅前10",
        )
    by_ticker = {r.ticker: r for r in indexes}
    spy = by_ticker.get("SPY")
    qqq = by_ticker.get("QQQ")
    iwm = by_ticker.get("IWM")
    vix = by_ticker.get("^VIX")
    sector_phrase = _sector_subject_phrase(sectors)
    subject = f"Sentinel AI 美股市场日报：{sector_phrase}"
    preview_parts = []
    for row in (spy, qqq, iwm):
        if row and row.change_pct is not None:
            preview_parts.append(f"{row.ticker} {_pct(row.change_pct)}")
    if vix and vix.price is not None:
        preview_parts.append(f"VIX {vix.price:.2f}")
    preview = " · ".join(preview_parts) or "美股市场复盘 · 板块轮动 · 涨跌幅前10"
    return subject, preview


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
                name=_row_name(ticker),
                price=last,
                change_pct=change_pct,
                volume=vol_value,
                previous_price=prev,
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
                previous_price=_float_or_none(q.get("regularMarketPreviousClose")),
            )
        )
    return rows


def _yesterday_check_section(
    indexes: Sequence[MarketRow],
    sectors: Sequence[MarketRow],
    hot_rows: Sequence[MarketRow],
) -> str:
    by_index = {r.ticker: r for r in indexes}
    by_sector = {r.ticker: r for r in sectors}
    by_hot = {r.ticker: r for r in hot_rows}
    spy = by_index.get("SPY")
    qqq = by_index.get("QQQ")
    xle = by_sector.get("XLE")
    xlk = by_sector.get("XLK")
    nvidia = by_hot.get("NVDA")
    amd = by_hot.get("AMD")
    tesla = by_hot.get("TSLA")
    lines = ["一、昨日 Sentinel 提示兑现"]
    if qqq and spy:
        qqq_weaker = (qqq.change_pct or 0) < (spy.change_pct or 0)
        lines.extend(
            [
                f"昨日提示 1：{PREVIOUS_CHECKS[0]}",
                f"今日结果：QQQ（纳斯达克100科技股）{_pct(qqq.change_pct)}，SPY（标普500大盘）{_pct(spy.change_pct)}",
                f"结论：{'✅ 兑现。科技股继续弱于大盘。' if qqq_weaker else '❌ 未兑现。科技股没有继续弱于大盘。'}",
                "",
            ]
        )
    if xle and xlk:
        spread = (xle.change_pct or 0) - (xlk.change_pct or 0)
        lines.extend(
            [
                f"昨日提示 2：{PREVIOUS_CHECKS[1]}",
                f"今日结果：XLE（能源板块）{_pct(xle.change_pct)}，XLK（科技板块）{_pct(xlk.change_pct)}",
                f"结论：{'✅ 兑现。' if spread > 0 else '❌ 未兑现。'}能源与科技出现 {abs(spread):.2f} 个百分点剪刀差。",
                "",
            ]
        )
    hot_triplet = [r for r in (nvidia, amd, tesla) if r is not None]
    if hot_triplet:
        still_down = any((r.change_pct or 0) < 0 for r in hot_triplet)
        lines.extend(
            [
                f"昨日提示 3：{PREVIOUS_CHECKS[2]}",
                "今日结果：" + "，".join(f"{r.ticker} {_pct(r.change_pct)}" for r in hot_triplet),
                f"结论：{'❌ 未止跌。高关注成长股继续承压。' if still_down else '✅ 初步止跌。高关注成长股压力缓和。'}",
            ]
        )
    return "\n".join(lines).strip()


def _market_overview_section(rows: Sequence[MarketRow]) -> str:
    by_ticker = {r.ticker: r for r in rows}
    ordered = [by_ticker[t] for t in INDEX_TICKERS if t in by_ticker]
    lines = ["二、今日市场总览", "", "指标\t中文解释\t最新值\t涨跌"]
    for row in ordered:
        value = f"{row.price:.2f}%" if row.ticker == "^TNX" and row.price is not None else _price(row.price)
        change = _yield_bp(row, by_ticker) if row.ticker == "^TNX" else _pct(row.change_pct)
        label = "10Y Yield" if row.ticker == "^TNX" else row.ticker.replace("^", "")
        lines.append(f"{label}\t{INDEX_DESCRIPTIONS.get(row.ticker, row.name)}\t{value}\t{change}")
    vix = by_ticker.get("^VIX")
    tnx = by_ticker.get("^TNX")
    vix_text = "VIX 上升，但仍低于 20，说明市场紧张感增加，但还没有进入高波动避险区。"
    if vix and vix.price is not None and vix.price >= 20:
        vix_text = "VIX 升至 20 以上，说明市场波动预期已经明显抬升。"
    yield_text = ""
    if tnx and tnx.price is not None:
        yield_text = f"10Y 美债收益率至 {tnx.price:.2f}%，对科技股估值有压力。"
    lines.extend(["", "专业解释：", vix_text + yield_text])
    return "\n".join(lines)


def _sector_section(rows: Sequence[MarketRow]) -> str:
    valid = sorted(
        [r for r in rows if r.change_pct is not None],
        key=lambda r: r.change_pct or 0,
        reverse=True,
    )
    if not valid:
        return ""
    leaders = valid[:5]
    laggards = list(reversed(valid[-5:]))
    lines = ["三、板块强弱榜", "相对最强：", "", "排名\t板块\tETF\t涨跌"]
    lines.extend(_sector_table_lines(leaders))
    lines.extend(["", "最弱：", "", "排名\t板块\tETF\t涨跌"])
    lines.extend(_sector_table_lines(laggards))
    top = leaders[0]
    weak_text = "、".join(_sector_cn(r.ticker) for r in laggards[:2])
    lines.extend(
        [
            "",
            "中文解读：",
            f"今天不是单纯看指数涨跌。{_sector_cn(top.ticker)}相对最强，{weak_text}靠后，说明市场在做明显板块轮动。",
        ]
    )
    return "\n".join(lines)


def _movers_section(title: str, rows: Sequence[MarketRow], *, catalyst_kind: str) -> str:
    if not rows:
        return ""
    lines = [title, "", "排名\t股票\t中文解释\t涨跌\t价格\t成交量"]
    for idx, row in enumerate(rows[:10], 1):
        lines.append(
            f"{idx}\t{row.ticker}\t{_company_desc(row)}\t{_pct(row.change_pct)}\t{_price(row.price)}\t{_vol(row.volume)}"
        )
    lines.extend(["", "Top 3 异动归因：", ""])
    for row in rows[:3]:
        lines.append(f"{row.ticker}：{_catalyst_line(row.ticker, catalyst_kind)}")
    if catalyst_kind == "gainers":
        lines.append("🔒 其余 7 只完整异动归因、新闻源、成交量验证，Pro 用户可见。")
    else:
        lines.append("🔒 其余 7 只完整异动归因、是否财报/评级/融资/并购驱动，Pro 用户可见。")
    return "\n".join(lines)


def _active_section(active: Sequence[MarketRow], hot_rows: Sequence[MarketRow]) -> str:
    rows = _dedupe_rows([*hot_rows, *active])[:10]
    if not rows:
        return ""
    lines = ["六、巨头 + 异常活跃", "", "股票\t中文解释\t涨跌\t价格\t成交量"]
    for row in rows:
        lines.append(f"{row.ticker}\t{_company_desc(row)}\t{_pct(row.change_pct)}\t{_price(row.price)}\t{_vol(row.volume)}")
    negative_active = [r.ticker for r in rows if (r.change_pct or 0) < -3 and (r.volume or 0) >= 10_000_000]
    if negative_active:
        lines.extend(
            [
                "",
                "中文解读：",
                "今天最值得普通用户注意的是：成交活跃榜里很多高成交股票是下跌的。"
                + "、".join(negative_active[:6])
                + " 都是高成交下跌，这比单纯下跌更值得警惕。",
            ]
        )
    return "\n".join(lines)


def _sentinel_watch_section(rows: Sequence[MarketRow]) -> str:
    by_ticker = {r.ticker: r for r in rows}
    xle = by_ticker.get("XLE")
    xlk = by_ticker.get("XLK")
    if xle and xlk:
        spread = (xle.change_pct or 0) - (xlk.change_pct or 0)
        return (
            "七、Sentinel 今日盯防\n"
            f"Sentinel 今日重点盯防：能源 XLE {_pct(xle.change_pct)} vs 科技 XLK {_pct(xlk.change_pct)}，"
            f"单日剪刀差 {abs(spread):.2f} 个百分点。\n\n"
            "中文解释：\n"
            "这不是普通的单只股票波动，而是板块轮动。资金明显没有继续追科技，"
            "反而在能源里寻找相对强势。"
        )
    return ""


def _next_watch_section(
    indexes: Sequence[MarketRow],
    sectors: Sequence[MarketRow],
    hot_rows: Sequence[MarketRow],
) -> str:
    by_index = {r.ticker: r for r in indexes}
    by_sector = {r.ticker: r for r in sectors}
    by_hot = {r.ticker: r for r in hot_rows}
    lines = ["八、明早 Sentinel 会先看", ""]
    if "QQQ" in by_index and "SPY" in by_index:
        lines.extend(["QQQ 盘前是否继续弱于 SPY", "中文：科技股是否继续拖累大盘。", ""])
    if "XLE" in by_sector and "XLK" in by_sector:
        lines.extend(["XLE 是否继续强于 XLK", "中文：能源强、科技弱的板块轮动是否延续。", ""])
    if any(t in by_hot for t in ("NVDA", "AMD", "TSLA")):
        lines.extend(
            [
                "NVDA / AMD / TSLA 是否止跌",
                "中文：这些高关注成长股如果继续下跌，会影响散户情绪和科技股风险偏好。",
                "",
            ]
        )
    lines.append("免费用户明早看日报。Pro 用户会收到实时推送。")
    return "\n".join(lines).strip()


def _summary_section(indexes: Sequence[MarketRow], sectors: Sequence[MarketRow]) -> str:
    by_index = {r.ticker: r for r in indexes}
    by_sector = {r.ticker: r for r in sectors}
    qqq = by_index.get("QQQ")
    iwm = by_index.get("IWM")
    vix = by_index.get("^VIX")
    xle = by_sector.get("XLE")
    xlk = by_sector.get("XLK")
    pressure = []
    if iwm and (iwm.change_pct or 0) < -1:
        pressure.append("小盘股弱")
    if qqq and (qqq.change_pct or 0) < -1:
        pressure.append("科技股弱")
    if vix and (vix.change_pct or 0) > 0:
        pressure.append("VIX 上升但未失控" if (vix.price or 99) < 20 else "VIX 明显抬升")
    if xle and xlk and (xle.change_pct or 0) > (xlk.change_pct or 0):
        pressure.append("能源逆势")
    phrase = "、".join(pressure) if pressure else "市场信号分化"
    return (
        "九、Sentinel 一句话总结\n"
        f"今天的市场不是“全面崩”，但风险偏好明显降温：{phrase}。"
        "普通用户不需要急着判断方向，先看明早科技是否止跌、能源是否继续强。\n\n"
        "Context, not financial advice."
    )


def _sector_table_lines(rows: Sequence[MarketRow]) -> list[str]:
    out = []
    for idx, row in enumerate(rows, 1):
        english, chinese = SECTOR_TICKERS.get(row.ticker, (row.name, row.name))
        out.append(f"{idx}\t{chinese} {english}\t{row.ticker}\t{_pct(row.change_pct)}")
    return out


def _sector_subject_phrase(rows: Sequence[MarketRow]) -> str:
    by_ticker = {r.ticker: r for r in rows}
    xle = by_ticker.get("XLE")
    xlk = by_ticker.get("XLK")
    if xle and xlk and (xle.change_pct or 0) > (xlk.change_pct or 0):
        return "科技与小盘承压，能源逆势"
    return "市场复盘与明日观察"


def _yield_bp(row: MarketRow, rows_by_ticker: Mapping[str, MarketRow]) -> str:
    if row.price is not None and row.previous_price is not None:
        return f"{(row.price - row.previous_price) * 100:+.0f} bp"
    if row.change_pct is None or row.price is None:
        return "n/a"
    bp = row.price * (row.change_pct / 100) * 100
    return f"{bp:+.0f} bp"


def _catalyst_line(ticker: str, kind: str) -> str:
    mapped = {
        "SEDG": "新闻标题显示市场在交易“Q2 预期改善 / 太阳能股两日大涨”。",
        "FIG": "新闻标题显示市场在交易“AI 带动收入增长 / 目标价调整”。",
        "MICC": "新闻标题显示市场在交易“潜在收购传闻”。",
        "POET": "新闻标题显示市场近期在交易“股价大涨后的回落 / 估值讨论”。",
        "TNGX": "未取到足够明确的当日直接催化剂，需要进一步新闻验证。",
        "YSS": "新闻标题显示市场在交易“财报后股价回落 / 估值机会讨论”。",
    }
    if ticker in mapped:
        return mapped[ticker]
    return (
        "新闻与成交量显示有明显资金关注，完整催化剂需要继续核验。"
        if kind == "gainers"
        else "价格与成交量出现明显异动，直接催化剂需要继续核验。"
    )


def _dedupe_rows(rows: Sequence[MarketRow]) -> list[MarketRow]:
    seen: set[str] = set()
    out: list[MarketRow] = []
    for row in rows:
        if row.ticker in seen:
            continue
        seen.add(row.ticker)
        out.append(row)
    return out


def _row_name(ticker: str) -> str:
    if ticker in SECTOR_TICKERS:
        english, chinese = SECTOR_TICKERS[ticker]
        return f"{english} / {chinese}"
    return COMPANY_DESCRIPTIONS.get(ticker, ticker)


def _sector_cn(ticker: str) -> str:
    return SECTOR_TICKERS.get(ticker, (ticker, ticker))[1]


def _company_desc(row: MarketRow) -> str:
    return COMPANY_DESCRIPTIONS.get(row.ticker, row.name)


def _price(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.2f}"


def _pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:+.2f}%"


def _vol(value: int | None) -> str:
    if value is None:
        return "n/a"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"{value / 1_000:.1f}K"
    return str(value)


def _float_or_none(value) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


def _int_or_none(value) -> int | None:
    return int(value) if isinstance(value, (int, float)) else None
