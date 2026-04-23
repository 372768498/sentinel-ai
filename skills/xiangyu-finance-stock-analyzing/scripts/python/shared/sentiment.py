"""
情绪分析 + 同行对比 + 财报时间 + 突发新闻 + 地缘风险。

从 analyzers.py 拆出以满足 ≤1200 行限制。
"""

import asyncio
import sys
from datetime import datetime, timedelta, timezone

import pandas as pd
import yfinance as yf

from .constants import CRISIS_KEYWORDS, GEOPOLITICAL_RISK_MAP, PEER_GROUPS
from .data_fetcher import StockData, cache_get, cache_set
from .synthesizer import (
    EarningsTiming,
    PeerComparison,
    SentimentAnalysis,
)


# ============================================================================
# 8. Sentiment（5 子指标异步）
# ============================================================================

async def get_fear_greed_index() -> tuple[float, int | None, str | None] | None:
    """CNN Fear & Greed Index（反向指标）。"""
    cached = cache_get("fear_greed")
    if cached is not None:
        return cached

    def _fetch():
        try:
            from fear_and_greed import get as get_fg
            return get_fg()
        except Exception:
            return None

    try:
        result = await asyncio.to_thread(_fetch)
        if result is None:
            return None

        value = result.value
        status = result.description

        if value <= 25:
            score = 0.5
        elif value <= 45:
            score = 0.2
        elif value <= 55:
            score = 0.0
        elif value <= 75:
            score = -0.2
        else:
            score = -0.5

        out = (score, value, status)
        cache_set("fear_greed", out)
        return out
    except Exception:
        return None


async def get_short_interest(data: StockData) -> tuple[float, float | None, float | None] | None:
    """空头比例。"""
    try:
        pct = data.info.get("shortPercentOfFloat")
        if pct is None:
            return None
        pct_val = float(pct) * 100
        ratio = data.info.get("shortRatio")
        dtc = float(ratio) if ratio else None

        if pct_val > 20:
            score = 0.4 if (dtc and dtc > 10) else -0.3
        elif pct_val < 5:
            score = 0.2
        else:
            score = 0.0

        return (score, pct_val, dtc)
    except Exception:
        return None


async def get_vix_term_structure() -> tuple[float, str | None, float | None] | None:
    """VIX 期限结构（VXX/VIXM 代理）。"""
    cached = cache_get("vix_structure")
    if cached is not None:
        return cached

    def _fetch():
        try:
            vxx = yf.Ticker("VXX").history(period="5d")
            vixm = yf.Ticker("VIXM").history(period="5d")
            if not vxx.empty and not vixm.empty:
                ratio = vxx["Close"].iloc[-1] / vixm["Close"].iloc[-1]
                if ratio < 0.9:
                    return ("contango", 10.0, 0.3)
                elif ratio > 1.1:
                    return ("backwardation", -5.0, -0.3)
                else:
                    return ("flat", 0.0, 0.0)
        except Exception:
            pass

        # Fallback：VIX 现货
        try:
            vix_data = yf.Ticker("^VIX").history(period="5d")
            if vix_data.empty:
                return None
            spot = vix_data["Close"].iloc[-1]
            if spot < 15:
                return ("contango", 10.0, 0.3)
            elif spot < 20:
                return ("contango", 5.0, 0.1)
            elif spot > 30:
                return ("backwardation", -5.0, -0.3)
            else:
                return ("flat", 0.0, 0.0)
        except Exception:
            return None

    try:
        result = await asyncio.to_thread(_fetch)
        if result is None:
            return None
        structure, slope, score = result
        out = (score, structure, slope)
        cache_set("vix_structure", out)
        return out
    except Exception:
        return None


async def get_insider_activity(ticker: str, period_days: int = 90) -> tuple[float, int | None, float | None] | None:
    """SEC Form 4 内部交易。"""
    def _fetch():
        try:
            from edgar import Company, set_identity

            set_identity("<BOT_EMAIL>")
            company = Company(ticker)
            filings = company.get_filings(form="4")
            if filings is None or len(filings) == 0:
                return None

            cutoff = datetime.now() - timedelta(days=period_days)
            bought_shares = sold_shares = 0
            bought_value = sold_value = 0.0
            count = 0

            for filing in filings:
                if count >= 50:
                    break
                count += 1
                try:
                    fd = filing.filing_date
                    if hasattr(fd, 'to_pydatetime'):
                        fd = fd.to_pydatetime()
                    elif isinstance(fd, str):
                        fd = datetime.strptime(fd, "%Y-%m-%d")
                    if hasattr(fd, 'year') and not hasattr(fd, 'hour'):
                        fd = datetime.combine(fd, datetime.min.time())
                    if fd < cutoff:
                        continue

                    form4 = filing.obj()
                    if form4 is None:
                        continue

                    if hasattr(form4, 'common_stock_purchases'):
                        purchases = form4.common_stock_purchases
                        if isinstance(purchases, pd.DataFrame) and not purchases.empty:
                            if 'Shares' in purchases.columns:
                                bought_shares += int(purchases['Shares'].sum())
                            if 'Price' in purchases.columns and 'Shares' in purchases.columns:
                                bought_value += float((purchases['Shares'] * purchases['Price']).sum())

                    if hasattr(form4, 'common_stock_sales'):
                        sales = form4.common_stock_sales
                        if isinstance(sales, pd.DataFrame) and not sales.empty:
                            if 'Shares' in sales.columns:
                                sold_shares += int(sales['Shares'].sum())
                            if 'Price' in sales.columns and 'Shares' in sales.columns:
                                sold_value += float((sales['Shares'] * sales['Price']).sum())
                except Exception:
                    continue

            net_shares = bought_shares - sold_shares
            net_value = (bought_value - sold_value) / 1_000_000

            if net_shares > 100_000 or net_value > 1.0:
                score = 0.8
            elif net_shares > 10_000 or net_value > 0.1:
                score = 0.4
            elif net_shares < -100_000 or net_value < -1.0:
                score = -0.8
            elif net_shares < -10_000 or net_value < -0.1:
                score = -0.4
            else:
                score = 0.0

            return (score, net_shares, net_value)
        except ImportError:
            return None
        except Exception:
            return None

    try:
        return await asyncio.to_thread(_fetch)
    except Exception:
        return None


async def get_put_call_ratio(data: StockData) -> tuple[float, float | None, int | None, int | None] | None:
    """Put/Call 比率（修复：用 ticker_symbol 重新获取）。"""
    def _fetch():
        try:
            ticker_obj = yf.Ticker(data.ticker_symbol)
            expirations = ticker_obj.options
            if not expirations:
                return None

            opt_chain = ticker_obj.option_chain(expirations[0])
            put_vol = opt_chain.puts["volume"].sum() if "volume" in opt_chain.puts.columns else 0
            call_vol = opt_chain.calls["volume"].sum() if "volume" in opt_chain.calls.columns else 0

            if call_vol == 0 or put_vol == 0:
                return None

            return (put_vol / call_vol, int(put_vol), int(call_vol))
        except Exception:
            return None

    try:
        result = await asyncio.to_thread(_fetch)
        if result is None:
            return None

        ratio, put_vol, call_vol = result
        if ratio > 1.5:
            score = 0.3
        elif ratio > 1.0:
            score = 0.1
        elif ratio > 0.7:
            score = -0.1
        else:
            score = -0.3

        return (score, ratio, put_vol, call_vol)
    except Exception:
        return None


async def analyze_sentiment(
    data: StockData, verbose: bool = False, skip_insider: bool = False,
) -> SentimentAnalysis | None:
    """5 子指标并行情绪分析。"""
    scores, explanations, warnings = [], [], []

    fg_score = fg_value = fg_status = None
    si_score = si_pct = dtc = None
    vix_s_score = vix_struct = vix_slope = None
    insider_score = insider_shares = insider_value = None
    pc_score = pc_ratio = put_vol = call_vol = None

    try:
        tasks = [
            asyncio.wait_for(get_fear_greed_index(), timeout=10),
            asyncio.wait_for(get_short_interest(data), timeout=10),
            asyncio.wait_for(get_vix_term_structure(), timeout=10),
        ]

        if skip_insider:
            tasks.append(asyncio.sleep(0))
            if verbose:
                print("    Skipping insider trading analysis (--no-insider)", file=sys.stderr)
        else:
            tasks.append(asyncio.wait_for(get_insider_activity(data.ticker, 90), timeout=10))

        tasks.append(asyncio.wait_for(get_put_call_ratio(data), timeout=10))
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Fear & Greed
        r = results[0]
        if isinstance(r, tuple) and r is not None:
            fg_score, fg_value, fg_status = r
            scores.append(fg_score)
            explanations.append(f"{fg_status} ({fg_value})")

        # Short Interest
        r = results[1]
        if isinstance(r, tuple) and r is not None:
            si_score, si_pct, dtc = r
            scores.append(si_score)
            explanations.append(f"Short interest {si_pct:.1f}%")
            warnings.append("空头数据延迟约 2 周（FINRA 滞后）")

        # VIX Structure
        r = results[2]
        if isinstance(r, tuple) and r is not None:
            vix_s_score, vix_struct, vix_slope = r
            scores.append(vix_s_score)
            explanations.append(f"VIX {vix_struct}")

        # Insider
        r = results[3]
        if isinstance(r, tuple) and r is not None:
            insider_score, insider_shares, insider_value = r
            scores.append(insider_score)
            if insider_value:
                explanations.append(f"Insider net: ${insider_value:.1f}M")
            warnings.append("内幕交易数据可能延迟 2-3 天")

        # Put/Call
        r = results[4]
        if isinstance(r, tuple) and r is not None:
            pc_score, pc_ratio, put_vol, call_vol = r
            scores.append(pc_score)
            explanations.append(f"Put/call {pc_ratio:.2f}")

    except Exception:
        return None

    if len(scores) < 2:
        return None

    return SentimentAnalysis(
        score=sum(scores) / len(scores),
        explanation="; ".join(explanations),
        fear_greed_score=fg_score, short_interest_score=si_score,
        vix_structure_score=vix_s_score, insider_activity_score=insider_score,
        put_call_score=pc_score,
        fear_greed_value=fg_value, fear_greed_status=fg_status,
        short_interest_pct=si_pct, days_to_cover=dtc,
        vix_structure=vix_struct, vix_slope=vix_slope,
        insider_net_shares=insider_shares, insider_net_value=insider_value,
        put_call_ratio=pc_ratio, put_volume=put_vol, call_volume=call_vol,
        indicators_available=len(scores),
        data_freshness_warnings=warnings if warnings else None,
    )


# ============================================================================
# 9. Peer Comparison
# ============================================================================

def analyze_peer_comparison(data: StockData, verbose: bool = False) -> PeerComparison | None:
    """同行对比：估值、增长、利润率。"""
    try:
        sector = data.info.get("sector")
        industry = data.info.get("industry")
        if not sector:
            return None

        my_market_cap = data.info.get("marketCap")
        peer_tickers = _select_peers(data.ticker, sector, industry, market_cap=my_market_cap)
        if not peer_tickers:
            return None

        if verbose:
            print(f"Comparing to peers: {', '.join(peer_tickers)}", file=sys.stderr)

        peer_metrics = []
        for pt in peer_tickers:
            try:
                pinfo = yf.Ticker(pt).info
                peer_metrics.append({
                    "ticker": pt,
                    "pe": pinfo.get("trailingPE"),
                    "ps": pinfo.get("priceToSalesTrailing12Months"),
                    "pb": pinfo.get("priceToBook"),
                    "market_cap": pinfo.get("marketCap"),
                    "revenue_growth": pinfo.get("revenueGrowth"),
                    "net_margin": pinfo.get("profitMargins"),
                })
            except Exception:
                continue

        if not peer_metrics:
            return None

        def _median(key):
            vals = sorted(m[key] for m in peer_metrics if m.get(key) is not None and m[key] > 0)
            return vals[len(vals) // 2] if vals else None

        peer_pe, peer_ps, peer_pb = _median("pe"), _median("ps"), _median("pb")
        peer_growth, peer_margin = _median("revenue_growth"), _median("net_margin")

        my_pe = data.info.get("trailingPE")
        my_ps = data.info.get("priceToSalesTrailing12Months")
        my_pb = data.info.get("priceToBook")
        my_growth = data.info.get("revenueGrowth")
        my_margin = data.info.get("profitMargins")

        scores, explanations, comparisons = [], [], {}

        def _compare(name, mine, peer_med):
            if mine is not None and peer_med is not None and peer_med > 0:
                premium = ((mine - peer_med) / peer_med) * 100
                # 小于 1 的比率（如增长率/利润率）展示更多精度
                precision = 3 if abs(mine) < 1 and abs(peer_med) < 1 else 2
                comparisons[name] = {
                    "stock": round(mine, precision), "peer_avg": round(peer_med, precision),
                    "premium_pct": round(premium, 1),
                }
                return premium
            return None

        pe_prem = _compare("pe", my_pe, peer_pe)
        if pe_prem is not None:
            if pe_prem < -15:
                scores.append(0.4)
                explanations.append(f"P/E {pe_prem:+.0f}% vs peers (discount)")
            elif pe_prem > 15:
                scores.append(-0.3)
                explanations.append(f"P/E {pe_prem:+.0f}% vs peers (premium)")
            else:
                scores.append(0.0)

        # P/S 评分（v12 新增）
        ps_prem = _compare("ps", my_ps, peer_ps)
        if ps_prem is not None:
            if ps_prem < -20:
                scores.append(0.3)
            elif ps_prem > 50:
                scores.append(-0.3)
                explanations.append(f"P/S {ps_prem:+.0f}% vs peers (extreme premium)")
            elif ps_prem > 20:
                scores.append(-0.15)
            else:
                scores.append(0.0)

        # P/B 评分（v12 新增）
        pb_prem = _compare("pb", my_pb, peer_pb)
        if pb_prem is not None:
            if pb_prem < -20:
                scores.append(0.3)
            elif pb_prem > 50:
                scores.append(-0.3)
                explanations.append(f"P/B {pb_prem:+.0f}% vs peers (extreme premium)")
            elif pb_prem > 20:
                scores.append(-0.15)
            else:
                scores.append(0.0)

        growth_prem = _compare("revenue_growth", my_growth, peer_growth)
        if growth_prem is not None:
            if growth_prem > 20:
                scores.append(0.4)
                explanations.append("Revenue growth leads peers")
            elif growth_prem < -20:
                scores.append(-0.3)
            else:
                scores.append(0.1)

        margin_prem = _compare("net_margin", my_margin, peer_margin)
        if margin_prem is not None:
            if margin_prem > 20:
                scores.append(0.3)
            elif margin_prem < -20:
                scores.append(-0.2)
            else:
                scores.append(0.0)

        if not scores:
            return None

        avg = sum(scores) / len(scores)
        return PeerComparison(
            score=max(-1.0, min(1.0, avg)),
            peer_tickers=peer_tickers, comparisons=comparisons,
            explanation="; ".join(explanations) if explanations else "In line with peers",
        )
    except Exception as e:
        if verbose:
            print(f"Error in peer comparison: {e}", file=sys.stderr)
        return None


def _select_peers(ticker: str, sector: str, industry: str | None, market_cap: float | None = None) -> list[str]:
    """选取 3-5 个同行（排除自身 + 市值过滤）。"""
    sector_groups = PEER_GROUPS.get(sector, {})
    peers = []
    industry_match = False
    if industry:
        for gn, ts in sector_groups.items():
            if gn == "_default":
                continue
            if gn.lower() in (industry or "").lower() or (industry or "").lower() in gn.lower():
                peers = ts
                industry_match = True
                break
    if not peers:
        peers = sector_groups.get("_default", [])

    candidates = [p for p in peers if p.upper() != ticker.upper()]

    # 市值过滤
    if market_cap and market_cap > 0:
        # 行业精确匹配时用宽松阈值（保留行业内同行），否则用严格阈值
        lo = 0.01 if industry_match else 0.05
        hi = 100 if industry_match else 20
        filtered = []
        for p in candidates:
            try:
                p_cap = yf.Ticker(p).info.get("marketCap")
                if p_cap and (market_cap * lo) <= p_cap <= (market_cap * hi):
                    filtered.append(p)
            except Exception:
                filtered.append(p)
        # 行业匹配且过滤后不足 2 个 → 直接放弃过滤，保留所有行业同行
        if industry_match and len(filtered) < 2:
            filtered = candidates
        # 非行业匹配且过滤后不足 2 个 → 回退到 _default 放宽阈值
        elif not industry_match and len(filtered) < 2:
            defaults = [p for p in sector_groups.get("_default", []) if p.upper() != ticker.upper()]
            for p in defaults:
                if p not in filtered:
                    try:
                        p_cap = yf.Ticker(p).info.get("marketCap")
                        if p_cap and (market_cap * 0.01) <= p_cap <= (market_cap * 50):
                            filtered.append(p)
                    except Exception:
                        filtered.append(p)
        candidates = filtered if filtered else candidates

    return candidates[:5]


# ============================================================================
# Earnings Timing（修正器）
# ============================================================================

def analyze_earnings_timing(data: StockData) -> EarningsTiming | None:
    """财报时间风险。"""
    try:
        if data.earnings_history is None or data.earnings_history.empty:
            return None

        now = datetime.now()
        earnings_dates = data.earnings_history.sort_index(ascending=False)

        next_ed = last_ed = None
        for ed in earnings_dates.index:
            dt = pd.Timestamp(ed).to_pydatetime()
            if dt > now and next_ed is None:
                next_ed = dt
            elif dt <= now and last_ed is None:
                last_ed = dt
                break

        days_until = (next_ed - now).days if next_ed else None
        days_since = (now - last_ed).days if last_ed else None

        timing_flag = "safe"
        confidence_adj = 0.0
        caveats = []

        if days_until is not None and days_until <= 14:
            timing_flag = "pre_earnings"
            confidence_adj = -0.3
            caveats.append(f"Earnings in {days_until} days - high volatility expected")

        price_change_5d = None
        if days_since is not None and days_since <= 5:
            if data.price_history is not None and len(data.price_history) >= 5:
                p5 = data.price_history["Close"].iloc[-5]
                pc = data.price_history["Close"].iloc[-1]
                price_change_5d = ((pc - p5) / p5) * 100
                if price_change_5d > 15:
                    timing_flag = "post_earnings"
                    confidence_adj = -0.2
                    caveats.append(f"Up {price_change_5d:.1f}% in 5 days - gains may be priced in")

        return EarningsTiming(
            days_until_earnings=days_until, days_since_earnings=days_since,
            next_earnings_date=next_ed.strftime("%Y-%m-%d") if next_ed else None,
            last_earnings_date=last_ed.strftime("%Y-%m-%d") if last_ed else None,
            timing_flag=timing_flag, price_change_5d=price_change_5d,
            confidence_adjustment=confidence_adj, caveats=caveats,
        )
    except Exception:
        return None


# ============================================================================
# Breaking News & Geopolitical Risk
# ============================================================================

def check_breaking_news(verbose: bool = False) -> list[str] | None:
    """Google News RSS 扫描（24h 内危机关键词）。"""
    cached = cache_get("breaking_news")
    if cached is not None:
        return cached

    alerts = []
    try:
        import feedparser

        if verbose:
            print("Checking breaking news (Google News RSS)...", file=sys.stderr)

        urls = [
            "https://news.google.com/rss/search?q=stock+market+when:24h&hl=en-US&gl=US&ceid=US:en",
            "https://news.google.com/rss/search?q=economy+crisis+when:24h&hl=en-US&gl=US&ceid=US:en",
        ]
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=24)

        for url in urls:
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries[:20]:
                    pub_date = None
                    if hasattr(entry, "published_parsed") and entry.published_parsed:
                        pub_date = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                    if pub_date and pub_date < cutoff:
                        continue

                    text = f"{entry.get('title', '')} {entry.get('summary', '')}".lower()
                    for _, keywords in CRISIS_KEYWORDS.items():
                        for kw in keywords:
                            if kw in text:
                                title = entry.get("title", "Unknown alert")
                                hours = int((now - pub_date).total_seconds() / 3600) if pub_date else None
                                alert = f"{title} ({hours}h ago)" if hours is not None else title
                                if alert not in alerts:
                                    alerts.append(alert)
                                break
                        if len(alerts) >= 3:
                            break
                    if len(alerts) >= 3:
                        break
            except Exception:
                continue

        result = alerts if alerts else None
        cache_set("breaking_news", result)
        return result
    except Exception:
        return None


def check_sector_geopolitical_risk(
    ticker: str, sector: str | None,
    breaking_news: list[str] | None, verbose: bool = False,
) -> tuple[str | None, float]:
    """地缘政治风险检测。返回 (warning, penalty)。"""
    if not breaking_news:
        return None, 0.0

    news_text = " ".join(breaking_news).lower()
    for _, event in GEOPOLITICAL_RISK_MAP.items():
        found = [kw for kw in event["keywords"] if kw in news_text]
        if not found:
            continue
        if ticker in event["affected_tickers"]:
            return (f"SECTOR RISK: {event['impact']} (detected: {', '.join(found)})", 0.3)
        if sector and sector in event["sectors"]:
            return (f"SECTOR RISK: {sector} sector exposed to {event['impact']}", 0.15)

    return None, 0.0
