"""
分析引擎 v12：7 维度分析函数。

维度清单：
1. Earnings Surprise    盈利惊喜
2. Fundamentals         基本面（板块感知阈值 + 子评分分拆）
3. Analyst Sentiment    分析师情绪
4. Historical Patterns  历史表现
5. Market Context       市场环境
6. Sector Performance   板块强度
7. Technical Analysis   技术分析（MA/MACD/BB/RSI/Vol）

其余维度在 sentiment.py：
8. Sentiment Analysis   情绪（5 子指标异步）
9. Peer Comparison      同行对比
+ Earnings Timing / Breaking News / Geopolitical Risk
"""

import sys

import pandas as pd
import yfinance as yf

from .constants import SECTOR_ETF_MAP, TECHNICAL_PARAMS, get_valuation_thresholds
from .data_fetcher import StockData, cache_get, cache_set
from .synthesizer import (
    AnalystSentiment,
    EarningsSurprise,
    Fundamentals,
    HistoricalPatterns,
    MarketContext,
    MomentumAnalysis,
    SectorComparison,
    TechnicalAnalysis,
)


# ============================================================================
# 1. Earnings Surprise
# ============================================================================

def analyze_earnings_surprise(data: StockData) -> EarningsSurprise | None:
    """最近一季 EPS 惊喜。"""
    if data.earnings_history is None or data.earnings_history.empty:
        return None

    try:
        recent = data.earnings_history.sort_index(ascending=False).head(10)
        for _, row in recent.iterrows():
            if pd.notna(row.get("Reported EPS")) and pd.notna(row.get("EPS Estimate")):
                actual = float(row["Reported EPS"])
                expected = float(row["EPS Estimate"])
                if expected == 0:
                    continue

                surprise_pct = ((actual - expected) / abs(expected)) * 100

                if surprise_pct > 10:
                    score = 1.0
                elif surprise_pct > 5:
                    score = 0.7
                elif surprise_pct > 0:
                    score = 0.3
                elif surprise_pct > -5:
                    score = -0.3
                elif surprise_pct > -10:
                    score = -0.7
                else:
                    score = -1.0

                return EarningsSurprise(
                    score=score,
                    explanation=f"{'Beat' if surprise_pct > 0 else 'Missed'} by {abs(surprise_pct):.1f}%",
                    actual_eps=actual,
                    expected_eps=expected,
                    surprise_pct=surprise_pct,
                )
        return None
    except Exception:
        return None


# ============================================================================
# 2. Fundamentals（12 指标完整估值）
# ============================================================================

def analyze_fundamentals(data: StockData, sector: str = "") -> Fundamentals | None:
    """12 指标基本面评分（板块感知阈值 + 子评分分拆）。"""
    info = data.info
    thresholds = get_valuation_thresholds(sector)
    valuation_scores: list[float] = []  # 估值面子评分
    quality_scores: list[float] = []    # 质量面子评分
    metrics: dict = {}
    explanations: list[str] = []

    try:
        # 估值指标（板块感知阈值）
        _eval_pe(info, valuation_scores, metrics, explanations, thresholds)
        _eval_peg(info, valuation_scores, metrics, explanations, thresholds)
        _eval_ps(info, valuation_scores, metrics, explanations, thresholds)
        _eval_pb(info, valuation_scores, metrics, explanations, thresholds)
        _eval_ev_ebitda(info, valuation_scores, metrics, explanations, thresholds)

        # 质量指标（通用阈值）
        _eval_roe(info, quality_scores, metrics, explanations)
        _eval_roa(info, quality_scores, metrics, explanations)
        _eval_gross_margin(info, quality_scores, metrics, explanations)
        _eval_net_margin(info, quality_scores, metrics, explanations)
        _eval_fcf(info, quality_scores, metrics, explanations, data)
        _eval_current_ratio(info, quality_scores, metrics, explanations)
        _eval_interest_coverage(info, quality_scores, metrics, explanations)
        _eval_revenue_growth(info, quality_scores, metrics, explanations, data)
        _eval_debt_equity(info, quality_scores, metrics, explanations)

        all_scores = valuation_scores + quality_scores
        if not all_scores:
            return None

        avg = sum(all_scores) / len(all_scores)

        # 子评分存入 metrics 供报告展示
        if valuation_scores:
            metrics["_valuation_sub_score"] = round(sum(valuation_scores) / len(valuation_scores), 3)
        if quality_scores:
            metrics["_quality_sub_score"] = round(sum(quality_scores) / len(quality_scores), 3)

        return Fundamentals(
            score=max(-1.0, min(1.0, avg)),
            key_metrics=metrics,
            explanation="; ".join(explanations) if explanations else "Mixed fundamentals",
        )
    except Exception:
        return None


# --- 基本面子评分函数 ---

def _score(val, good_thresh, bad_thresh, higher_is_better=True):
    """通用评分：归一化到 [-1, 1]。"""
    if higher_is_better:
        if val >= good_thresh:
            return 0.5
        if val <= bad_thresh:
            return -0.5
        return 0.0
    else:
        if val <= good_thresh:
            return 0.5
        if val >= bad_thresh:
            return -0.5
        return 0.0


def _eval_pe(info, scores, metrics, explanations, thresholds):
    pe = info.get("trailingPE") or info.get("forwardPE")
    if pe and pe > 0:
        metrics["pe_ratio"] = round(pe, 2)
        s = _score(pe, thresholds["pe"][0], thresholds["pe"][1], higher_is_better=False)
        scores.append(s)
        if s > 0:
            explanations.append(f"P/E {pe:.1f}x (attractive)")
        elif s < 0:
            explanations.append(f"P/E {pe:.1f}x (elevated)")


def _eval_peg(info, scores, metrics, explanations, thresholds):
    peg = info.get("pegRatio")
    if peg and peg > 0:
        metrics["peg_ratio"] = round(peg, 2)
        s = _score(peg, thresholds["peg"][0], thresholds["peg"][1], higher_is_better=False)
        scores.append(s)
        if s > 0:
            explanations.append(f"PEG {peg:.2f} (undervalued vs growth)")


def _eval_ps(info, scores, metrics, explanations, thresholds):
    ps = info.get("priceToSalesTrailing12Months")
    if ps and ps > 0:
        metrics["ps_ratio"] = round(ps, 2)
        scores.append(_score(ps, thresholds["ps"][0], thresholds["ps"][1], higher_is_better=False))


def _eval_pb(info, scores, metrics, explanations, thresholds):
    pb = info.get("priceToBook")
    if pb and pb > 0:
        metrics["pb_ratio"] = round(pb, 2)
        scores.append(_score(pb, thresholds["pb"][0], thresholds["pb"][1], higher_is_better=False))


def _eval_ev_ebitda(info, scores, metrics, explanations, thresholds):
    ev = info.get("enterpriseToEbitda")
    if ev and ev > 0:
        metrics["ev_ebitda"] = round(ev, 2)
        scores.append(_score(ev, thresholds["ev_ebitda"][0], thresholds["ev_ebitda"][1], higher_is_better=False))


def _eval_roe(info, scores, metrics, explanations):
    roe = info.get("returnOnEquity")
    if roe is not None:
        metrics["roe"] = round(roe * 100, 1)
        s = _score(roe, 0.20, 0.10, higher_is_better=True)
        scores.append(s)
        if s > 0:
            explanations.append(f"ROE {roe * 100:.1f}% (strong)")


def _eval_roa(info, scores, metrics, explanations):
    roa = info.get("returnOnAssets")
    if roa is not None:
        metrics["roa"] = round(roa * 100, 1)
        scores.append(_score(roa, 0.15, 0.05, higher_is_better=True))


def _eval_gross_margin(info, scores, metrics, explanations):
    gm = info.get("grossMargins")
    if gm is not None:
        metrics["gross_margin"] = round(gm * 100, 1)
        s = _score(gm, 0.40, 0.20, higher_is_better=True)
        scores.append(s)
        if s > 0:
            explanations.append(f"Gross margin {gm * 100:.1f}% (strong pricing power)")


def _eval_net_margin(info, scores, metrics, explanations):
    nm = info.get("profitMargins")
    if nm is not None:
        metrics["net_margin"] = round(nm * 100, 1)
        scores.append(_score(nm, 0.20, 0.05, higher_is_better=True))


def _eval_fcf(info, scores, metrics, explanations, data=None):
    # 降级链：EDGAR > 季度 TTM > info
    fcf = None
    fcf_source = "info"

    # 1. SEC EDGAR（最权威）
    if data and hasattr(data, "sec_data") and data.sec_data:
        sec_fcf = data.sec_data.free_cash_flow
        if sec_fcf is not None:
            fcf = sec_fcf
            fcf_source = f"SEC EDGAR ({data.sec_data.filing_date})"

    # 2. 季度现金流 TTM
    if fcf is None and data is not None:
        qcf = getattr(data, "quarterly_cashflow", None)
        if qcf is not None and not qcf.empty:
            for label in ["Free Cash Flow", "FreeCashFlow"]:
                if label in qcf.index:
                    values = qcf.loc[label].dropna().head(4)
                    if len(values) >= 4:
                        fcf = float(values.sum())
                        fcf_source = "quarterly_ttm"
                    break

    # 3. info 字段
    if fcf is None:
        fcf = info.get("freeCashflow")
        fcf_source = "info"

    if fcf is not None:
        metrics["free_cashflow"] = fcf
        metrics["fcf_source"] = fcf_source
        if fcf > 0:
            scores.append(0.3)
            explanations.append(f"FCF ${fcf / 1e9:.1f}B (positive)")
        else:
            scores.append(-0.3)


def _eval_current_ratio(info, scores, metrics, explanations):
    cr = info.get("currentRatio")
    if cr is not None:
        metrics["current_ratio"] = round(cr, 2)
        s = _score(cr, 2.0, 1.0, higher_is_better=True)
        scores.append(s)
        if s < 0:
            explanations.append(f"Current ratio {cr:.2f} (liquidity risk)")


def _eval_interest_coverage(info, scores, metrics, explanations):
    ebit = info.get("ebitda")
    interest = info.get("totalDebt")
    # 近似：用 EBITDA / totalDebt 作为偿债能力代理
    if ebit and interest and interest > 0:
        coverage = ebit / interest
        metrics["debt_coverage_proxy"] = round(coverage, 2)
        scores.append(_score(coverage, 0.5, 0.2, higher_is_better=True))


def _eval_revenue_growth(info, scores, metrics, explanations, data=None):
    # 降级链：季度自计算 > info 字段
    rg = None
    if data is not None:
        qf = getattr(data, "quarterly_financials", None)
        if qf is not None and not qf.empty:
            for label in ["Total Revenue", "Revenue"]:
                if label not in qf.index:
                    continue
                vals = qf.loc[label].dropna()
                if len(vals) >= 8:
                    recent = sum(float(v) for v in vals.iloc[:4])
                    old = sum(float(v) for v in vals.iloc[4:8])
                    if old > 0:
                        rg = (recent - old) / old
                elif len(vals) >= 5:
                    r, o = float(vals.iloc[0]), float(vals.iloc[4])
                    if o > 0:
                        rg = (r - o) / o
                break
    if rg is None:
        rg = info.get("revenueGrowth")
    if rg is not None:
        metrics["revenue_growth_yoy"] = round(rg * 100, 1)
        s = _score(rg, 0.20, 0.05, higher_is_better=True)
        scores.append(s)
        if s > 0:
            explanations.append(f"Revenue growth {rg * 100:.1f}% YoY (strong)")
        elif s < 0:
            explanations.append(f"Revenue growth {rg * 100:.1f}% YoY (slow)")


def _eval_debt_equity(info, scores, metrics, explanations):
    de = info.get("debtToEquity")
    if de is not None:
        metrics["debt_to_equity"] = round(de / 100, 2)
        s = _score(de, 50, 200, higher_is_better=False)
        scores.append(s)
        if s < 0:
            explanations.append(f"D/E {de / 100:.1f}x (high leverage)")


# ============================================================================
# 3. Analyst Sentiment
# ============================================================================

def analyze_analyst_sentiment(data: StockData) -> AnalystSentiment | None:
    """分析师评级与目标价。"""
    info = data.info
    try:
        current_price = info.get("regularMarketPrice") or info.get("currentPrice")
        if not current_price:
            return None

        target_price = info.get("targetMeanPrice")
        num_analysts = info.get("numberOfAnalystOpinions")
        recommendation = info.get("recommendationKey")

        if not target_price or not recommendation:
            return AnalystSentiment(score=None, summary="No analyst coverage available")

        upside_pct = ((target_price - current_price) / current_price) * 100
        rec_scores = {
            "strong_buy": 1.0, "buy": 0.7, "hold": 0.0,
            "sell": -0.7, "strong_sell": -1.0,
        }
        base = rec_scores.get(recommendation, 0.0)

        if upside_pct > 20:
            score = min(1.0, base + 0.3)
        elif upside_pct > 10:
            score = min(1.0, base + 0.15)
        elif upside_pct < -10:
            score = max(-1.0, base - 0.3)
        else:
            score = base

        rec_display = recommendation.replace("_", " ").title()
        summary = f"{rec_display} with {abs(upside_pct):.1f}% {'upside' if upside_pct > 0 else 'downside'}"
        if num_analysts:
            summary += f" ({num_analysts} analysts)"

        return AnalystSentiment(
            score=score, summary=summary, consensus_rating=rec_display,
            price_target=target_price, current_price=current_price,
            upside_pct=upside_pct, num_analysts=num_analysts,
        )
    except Exception:
        return AnalystSentiment(score=None, summary="Error analyzing analyst sentiment")


# ============================================================================
# 4. Historical Patterns
# ============================================================================

def analyze_historical_patterns(data: StockData) -> HistoricalPatterns | None:
    """历史财报反应。"""
    if data.earnings_history is None or data.price_history is None:
        return None
    if data.earnings_history.empty or data.price_history.empty:
        return None

    try:
        earnings_dates = data.earnings_history.sort_index(ascending=False).head(4)
        beats, reactions = 0, []
        valid_count = 0  # 有完整 EPS 数据的季度数

        for earnings_date, row in earnings_dates.iterrows():
            if pd.notna(row.get("Reported EPS")) and pd.notna(row.get("EPS Estimate")):
                valid_count += 1
                if float(row["Reported EPS"]) > float(row["EPS Estimate"]):
                    beats += 1
                try:
                    day = pd.Timestamp(earnings_date).date()
                    prices = data.price_history[data.price_history.index.date == day]
                    if not prices.empty:
                        change = ((prices["Close"].iloc[0] - prices["Open"].iloc[0]) / prices["Open"].iloc[0]) * 100
                        reactions.append(change)
                except Exception:
                    continue

        total = valid_count
        if total == 0:
            return None

        rate = beats / total
        if rate == 1.0:
            score = 0.8
        elif rate >= 0.75:
            score = 0.5
        elif rate >= 0.5:
            score = 0.0
        elif rate >= 0.25:
            score = -0.5
        else:
            score = -0.8

        desc = f"{beats}/{valid_count} quarters beat expectations"
        avg_reaction = None
        if reactions:
            avg_reaction = sum(reactions) / len(reactions)
            desc += f", avg reaction {avg_reaction:+.1f}%"

        return HistoricalPatterns(
            score=score, pattern_desc=desc,
            beats_last_4q=beats, avg_reaction_pct=avg_reaction,
            total_quarters=valid_count,
        )
    except Exception:
        return None


# ============================================================================
# 5. Market Context
# ============================================================================

def analyze_market_context(verbose: bool = False) -> MarketContext | None:
    """VIX + SPY/QQQ + 安全港（GLD/TLT/UUP）。"""
    cached = cache_get("market_context")
    if cached is not None:
        if verbose:
            print("Using cached market context (< 1h old)", file=sys.stderr)
        return cached

    try:
        if verbose:
            print("Fetching market indicators (VIX, SPY, QQQ)...", file=sys.stderr)

        vix_info = yf.Ticker("^VIX").info
        vix_level = vix_info.get("regularMarketPrice") or vix_info.get("currentPrice")
        if not vix_level:
            return None

        if vix_level < 20:
            vix_status, vix_score = "calm", 0.2
        elif vix_level < 30:
            vix_status, vix_score = "elevated", 0.0
        else:
            vix_status, vix_score = "fear", -0.5

        spy_hist = yf.Ticker("SPY").history(period="1mo")
        qqq_hist = yf.Ticker("QQQ").history(period="1mo")
        if spy_hist.empty or qqq_hist.empty:
            return None

        spy_trend = _pct_change(spy_hist["Close"], 10)
        qqq_trend = _pct_change(qqq_hist["Close"], 10)

        avg_trend = (spy_trend + qqq_trend) / 2
        if avg_trend > 3:
            market_regime, regime_score = "bull", 0.3
        elif avg_trend < -3:
            market_regime, regime_score = "bear", -0.4
        else:
            market_regime, regime_score = "choppy", -0.1

        overall = (vix_score + regime_score) / 2

        # 安全港
        gld_5d = tlt_5d = uup_5d = None
        risk_off = False
        try:
            if verbose:
                print("Fetching safe-haven indicators (GLD, TLT, UUP)...", file=sys.stderr)
            gld_5d = _etf_change("GLD", 5)
            tlt_5d = _etf_change("TLT", 5)
            uup_5d = _etf_change("UUP", 5)
            if (gld_5d is not None and gld_5d >= 2.0
                    and tlt_5d is not None and tlt_5d >= 1.0
                    and uup_5d is not None and uup_5d >= 1.0):
                risk_off = True
                overall -= 0.5
        except Exception:
            pass

        explanation = f"VIX {vix_level:.1f} ({vix_status}), Market {market_regime} (SPY {spy_trend:+.1f}%, QQQ {qqq_trend:+.1f}% 10d)"
        if risk_off:
            explanation += " RISK-OFF MODE"

        result = MarketContext(
            vix_level=vix_level, vix_status=vix_status,
            spy_trend_10d=spy_trend, qqq_trend_10d=qqq_trend,
            market_regime=market_regime, score=overall,
            explanation=explanation,
            gld_change_5d=gld_5d, tlt_change_5d=tlt_5d,
            uup_change_5d=uup_5d, risk_off_detected=risk_off,
        )
        cache_set("market_context", result)
        return result
    except Exception as e:
        if verbose:
            print(f"Error analyzing market context: {e}", file=sys.stderr)
        return None


def _pct_change(series: pd.Series, days: int) -> float:
    """计算 N 日涨跌幅。"""
    old = series.iloc[-min(days, len(series))]
    cur = series.iloc[-1]
    return ((cur - old) / old) * 100


def _etf_change(symbol: str, days: int) -> float | None:
    """获取 ETF N 日涨跌幅。"""
    hist = yf.Ticker(symbol).history(period="10d")
    if hist.empty or len(hist) < days:
        return None
    return _pct_change(hist["Close"], days)


# ============================================================================
# 6. Sector Performance
# ============================================================================

def analyze_sector_performance(data: StockData, verbose: bool = False) -> SectorComparison | None:
    """板块相对强度。"""
    try:
        sector = data.info.get("sector")
        industry = data.info.get("industry")
        if not sector:
            return None

        etf_ticker = SECTOR_ETF_MAP.get(sector)
        if not etf_ticker:
            return None

        if verbose:
            print(f"Comparing to sector ETF: {etf_ticker}", file=sys.stderr)

        sector_hist = yf.Ticker(etf_ticker).history(period="3mo")
        if sector_hist.empty or data.price_history is None or data.price_history.empty:
            return None

        stock_1m = _pct_change(data.price_history["Close"], 22)
        sector_1m = _pct_change(sector_hist["Close"], 22)
        rs = stock_1m - sector_1m  # 百分点差值，正=跑赢板块

        sector_10d = _pct_change(sector_hist["Close"], 10)
        if sector_10d > 5:
            trend = "strong uptrend"
        elif sector_10d > 2:
            trend = "uptrend"
        elif sector_10d < -5:
            trend = "downtrend"
        elif sector_10d < -2:
            trend = "weak"
        else:
            trend = "neutral"

        score = 0.0
        if rs > 5:       # 跑赢板块 5pp 以上
            score += 0.3
        elif rs < -5:    # 跑输板块 5pp 以上
            score -= 0.3
        if sector_10d > 5:
            score += 0.2
        elif sector_10d < -5:
            score -= 0.2

        return SectorComparison(
            sector_name=sector, industry_name=industry or "Unknown",
            stock_return_1m=stock_1m, sector_return_1m=sector_1m,
            relative_strength=rs, sector_trend=trend,
            score=score,
            explanation=f"{sector} sector {trend} ({sector_1m:+.1f}% 1m), stock {stock_1m:+.1f}% vs sector",
        )
    except Exception as e:
        if verbose:
            print(f"Error analyzing sector performance: {e}", file=sys.stderr)
        return None


# ============================================================================
# 7. Technical Analysis（v9.0 新增）
# ============================================================================

def analyze_technical(data: StockData) -> TechnicalAnalysis | None:
    """MA 交叉 + MACD + 布林带 + RSI + 成交量确认 + 52w 范围。"""
    if data.price_history is None or data.price_history.empty:
        return None

    try:
        close = data.price_history["Close"]
        p = TECHNICAL_PARAMS

        # MA
        ma5 = close.rolling(p["ma_short"]).mean()
        ma20 = close.rolling(p["ma_mid"]).mean()
        ma50 = close.rolling(p["ma_long"]).mean()

        ma5_val = ma5.iloc[-1] if len(ma5.dropna()) > 0 else None
        ma20_val = ma20.iloc[-1] if len(ma20.dropna()) > 0 else None
        ma50_val = ma50.iloc[-1] if len(ma50.dropna()) > 0 else None

        # MA 交叉评分
        ma_score = 0.0
        ma_alignment = "mixed"
        if ma5_val and ma20_val and ma50_val:
            if ma5_val > ma20_val > ma50_val:
                ma_score = 0.5
                ma_alignment = "bullish"
            elif ma5_val < ma20_val < ma50_val:
                ma_score = -0.5
                ma_alignment = "bearish"

        # MACD
        ema_fast = close.ewm(span=p["macd_fast"], adjust=False).mean()
        ema_slow = close.ewm(span=p["macd_slow"], adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=p["macd_signal"], adjust=False).mean()
        macd_val = macd_line.iloc[-1]
        signal_val = signal_line.iloc[-1]
        macd_histogram = macd_val - signal_val

        macd_score = 0.0
        macd_signal_str = "neutral"
        if macd_val > signal_val:
            macd_score = 0.3
            macd_signal_str = "bullish"
        elif macd_val < signal_val:
            macd_score = -0.3
            macd_signal_str = "bearish"

        # 布林带
        bb_mid = close.rolling(p["bb_period"]).mean()
        bb_std = close.rolling(p["bb_period"]).std()
        bb_upper = bb_mid + p["bb_std"] * bb_std
        bb_lower = bb_mid - p["bb_std"] * bb_std

        current_price = close.iloc[-1]
        bb_position = "middle"
        bb_score = 0.0
        if len(bb_upper.dropna()) > 0 and len(bb_lower.dropna()) > 0:
            upper = bb_upper.iloc[-1]
            lower = bb_lower.iloc[-1]
            if current_price >= upper:
                bb_position = "above_upper"
                bb_score = -0.3
            elif current_price <= lower:
                bb_position = "below_lower"
                bb_score = 0.3
            else:
                bb_width = upper - lower
                if bb_width > 0:
                    pos = (current_price - lower) / bb_width
                    if pos > 0.8:
                        bb_position = "near_upper"
                        bb_score = -0.2
                    elif pos < 0.2:
                        bb_position = "near_lower"
                        bb_score = 0.2

        # RSI
        rsi = _calculate_rsi(close, p["rsi_period"])
        rsi_score = 0.0
        rsi_status = "neutral"
        if rsi is not None:
            if rsi > 70:
                rsi_score, rsi_status = -0.5, "overbought"
            elif rsi < 30:
                rsi_score, rsi_status = 0.5, "oversold"

        # 成交量确认
        volume_ratio = None
        volume_score = 0.0
        vol_period = p["volume_avg_period"]
        if "Volume" in data.price_history.columns and len(data.price_history) >= vol_period + 5:
            recent_vol = data.price_history["Volume"].iloc[-5:].mean()
            avg_vol = data.price_history["Volume"].iloc[-vol_period - 5:-5].mean()
            if avg_vol > 0:
                volume_ratio = recent_vol / avg_vol
                if volume_ratio > 1.5:
                    # 高成交量 + 价格上涨 = 看多确认
                    price_5d = _pct_change(close, 5)
                    volume_score = 0.2 if price_5d > 0 else -0.2

        # 52 周范围
        high_52w = data.info.get("fiftyTwoWeekHigh")
        low_52w = data.info.get("fiftyTwoWeekLow")
        range_score = 0.0
        range_position = None
        near_52w_high = False
        near_52w_low = False

        if high_52w and low_52w and current_price:
            span = high_52w - low_52w
            if span > 0:
                range_position = ((current_price - low_52w) / span) * 100
                near_52w_high = range_position > 90
                near_52w_low = range_position < 10
                if near_52w_high:
                    range_score = -0.3
                elif near_52w_low:
                    range_score = 0.3

        # 趋势判断
        scores = [s for s in [ma_score, macd_score, bb_score, rsi_score, volume_score, range_score] if s != 0.0]
        total = sum([ma_score, macd_score, bb_score, rsi_score, volume_score, range_score])
        avg = total / 6

        if avg > 0.15:
            short_term_trend = "uptrend"
        elif avg < -0.15:
            short_term_trend = "downtrend"
        else:
            short_term_trend = "sideways"

        # 支撑阻力
        support = round(bb_lower.iloc[-1], 2) if len(bb_lower.dropna()) > 0 else low_52w
        resistance = round(bb_upper.iloc[-1], 2) if len(bb_upper.dropna()) > 0 else high_52w

        return TechnicalAnalysis(
            score=max(-1.0, min(1.0, avg)),
            short_term_trend=short_term_trend,
            ma5=round(ma5_val, 2) if ma5_val else None,
            ma20=round(ma20_val, 2) if ma20_val else None,
            ma50=round(ma50_val, 2) if ma50_val else None,
            ma_alignment=ma_alignment,
            macd_value=round(macd_val, 4),
            macd_signal=round(signal_val, 4),
            macd_histogram=round(macd_histogram, 4),
            macd_trend=macd_signal_str,
            bb_upper=round(bb_upper.iloc[-1], 2) if len(bb_upper.dropna()) > 0 else None,
            bb_lower=round(bb_lower.iloc[-1], 2) if len(bb_lower.dropna()) > 0 else None,
            bb_position=bb_position,
            rsi_14d=rsi,
            rsi_status=rsi_status,
            volume_ratio=round(volume_ratio, 2) if volume_ratio else None,
            range_position=round(range_position, 1) if range_position else None,
            near_52w_high=near_52w_high,
            near_52w_low=near_52w_low,
            support=support,
            resistance=resistance,
            explanation=_build_technical_explanation(
                short_term_trend, ma_alignment, macd_signal_str,
                rsi, rsi_status, bb_position, volume_ratio, near_52w_high, near_52w_low,
            ),
        )
    except Exception:
        return None


def _calculate_rsi(prices: pd.Series, period: int = 14) -> float | None:
    """RSI (Relative Strength Index)。"""
    try:
        if len(prices) < period + 1:
            return None
        delta = prices.diff()
        gains = delta.where(delta > 0, 0)
        losses = -delta.where(delta < 0, 0)
        avg_gain = gains.rolling(window=period).mean()
        avg_loss = losses.rolling(window=period).mean()
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return round(float(rsi.iloc[-1]), 1)
    except Exception:
        return None


def _build_technical_explanation(
    trend, ma_align, macd_sig, rsi, rsi_status,
    bb_pos, vol_ratio, near_high, near_low,
) -> str:
    parts = [f"Trend: {trend}"]
    parts.append(f"MA: {ma_align}")
    parts.append(f"MACD: {macd_sig}")
    if rsi:
        parts.append(f"RSI {rsi:.0f} ({rsi_status})")
    if bb_pos != "middle":
        parts.append(f"BB: {bb_pos}")
    if vol_ratio and vol_ratio > 1.5:
        parts.append(f"Vol {vol_ratio:.1f}x avg")
    if near_high:
        parts.append("Near 52w high")
    elif near_low:
        parts.append("Near 52w low")
    return "; ".join(parts)


# ============================================================================
# 兼容旧接口 — analyze_momentum (委托给 analyze_technical)
# ============================================================================

def analyze_momentum(data: StockData) -> MomentumAnalysis | None:
    """兼容旧接口：从 TechnicalAnalysis 提取动量数据。"""
    tech = analyze_technical(data)
    if tech is None:
        return None

    return MomentumAnalysis(
        rsi_14d=tech.rsi_14d,
        rsi_status=tech.rsi_status,
        price_vs_52w_low=tech.range_position,
        price_vs_52w_high=(100 - tech.range_position) if tech.range_position else None,
        near_52w_high=tech.near_52w_high,
        near_52w_low=tech.near_52w_low,
        volume_ratio=tech.volume_ratio,
        relative_strength_vs_sector=None,
        score=tech.score,
        explanation=tech.explanation,
    )
