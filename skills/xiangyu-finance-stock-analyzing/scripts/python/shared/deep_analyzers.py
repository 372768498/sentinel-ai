"""
深度分析引擎 v12 — 6 个领域深度分析函数。

领域：valuation | growth | technical | fundamentals | peers | dividends
"""

import sys
from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd
import yfinance as yf

from .data_fetcher import StockData, fetch_deep_data, cache_get, cache_set
from .constants import PEER_GROUPS, TECHNICAL_PARAMS


# ============================================================================
# 动态无风险利率
# ============================================================================

def _get_risk_free_rate() -> float:
    """动态获取 10Y 美债收益率（^TNX），失败时回退 4.5%。"""
    cached = cache_get("risk_free_rate")
    if cached is not None:
        return cached
    try:
        tnx = yf.Ticker("^TNX").info
        rate = tnx.get("regularMarketPrice") or tnx.get("currentPrice")
        if rate and 1.0 < rate < 10.0:
            result = rate / 100  # ^TNX 报价单位是百分点
            cache_set("risk_free_rate", result)
            return result
    except Exception:
        pass
    return 0.045  # 回退值


def _get_best_fcf(data: "StockData", info: dict) -> tuple[float | None, str]:
    """
    获取最佳 FCF。降级链：EDGAR > 季度 TTM > info。
    返回 (value, source_description)。
    """
    # 1. SEC EDGAR（最权威）
    if hasattr(data, "sec_data") and data.sec_data and data.sec_data.free_cash_flow:
        fcf = data.sec_data.free_cash_flow
        if fcf > 0:
            return fcf, f"SEC EDGAR ({data.sec_data.filing_date})"

    # 2. 季度现金流 TTM
    qcf = data.quarterly_cashflow
    if qcf is not None and not qcf.empty:
        for label in ["Free Cash Flow", "FreeCashFlow"]:
            if label in qcf.index:
                values = qcf.loc[label].dropna().head(4)
                if len(values) >= 4:
                    ttm_fcf = float(values.sum())
                    if ttm_fcf > 0:
                        return ttm_fcf, "季度现金流 TTM（最近 4 季度）"
                break

    # 3. info 字段
    fcf = info.get("freeCashflow")
    return fcf, "Yahoo info 字段（可能滞后 1-3 周）"


def _calc_revenue_growth(data: "StockData") -> float | None:
    """从季度财务数据自行计算营收 YoY 增长率。"""
    qf = data.quarterly_financials
    if qf is None or qf.empty:
        return None
    for label in ["Total Revenue", "Revenue"]:
        if label not in qf.index:
            continue
        vals = qf.loc[label].dropna()
        if len(vals) >= 8:
            recent_4q = sum(float(v) for v in vals.iloc[:4])
            old_4q = sum(float(v) for v in vals.iloc[4:8])
            if old_4q > 0:
                return (recent_4q - old_4q) / old_4q
        elif len(vals) >= 5:
            recent = float(vals.iloc[0])
            year_ago = float(vals.iloc[4])
            if year_ago > 0:
                return (recent - year_ago) / year_ago
    return None


def _calc_earnings_growth(data: "StockData") -> float | None:
    """从 earnings_history 自行计算 EPS YoY 增长率。"""
    eh = data.earnings_history
    if eh is None or eh.empty:
        return None
    try:
        recent = eh.sort_index(ascending=False)
        eps_vals = []
        for _, row in recent.iterrows():
            val = row.get("Reported EPS")
            if pd.notna(val):
                eps_vals.append(float(val))
        if len(eps_vals) >= 8:
            recent_4q = sum(eps_vals[:4])
            old_4q = sum(eps_vals[4:8])
            if abs(old_4q) > 0.01:
                return (recent_4q - old_4q) / abs(old_4q)
    except Exception:
        pass
    return None


# ============================================================================
# Dataclass 定义
# ============================================================================

@dataclass
class ValuationDeep:
    """估值深度分析结果。"""
    # DCF
    dcf_value: float | None = None
    current_price: float | None = None
    safety_margin_pct: float | None = None
    dcf_scenarios: list[dict] | None = None  # [{scenario, value, vs_current}]
    # DCF 假设
    wacc: float | None = None
    fcf_ttm: float | None = None
    growth_rates: dict | None = None  # {conservative, base, optimistic}
    fcf_projections: list[dict] | None = None  # [{year, fcf, pv}]
    terminal_value: float | None = None
    enterprise_value: float | None = None
    # 历史估值
    pe_range: dict | None = None  # {low, median, high, current, percentile}
    ps_range: dict | None = None
    ev_ebitda_range: dict | None = None
    # 行业相对
    industry_comparison: list[dict] | None = None  # [{metric, stock, industry, premium}]
    # 综合
    verdict: str = ""
    # 数据来源追踪
    data_sources: dict = field(default_factory=dict)


@dataclass
class GrowthDeep:
    """成长性深度分析结果。"""
    # 营收
    quarterly_revenue: list[dict] | None = None  # [{quarter, revenue, yoy, qoq}]
    annual_revenue: list[dict] | None = None  # [{year, revenue, yoy}]
    rev_cagr_3y: float | None = None
    rev_cagr_5y: float | None = None
    # EPS
    quarterly_eps: list[dict] | None = None  # [{quarter, actual, estimate, surprise, yoy}]
    # 净利率趋势
    margin_trend: list[dict] | None = None  # [{quarter, net_margin}]
    # 分析师预测
    analyst_forecasts: dict | None = None  # {current_q, next_q, current_fy, next_fy}
    # PEG
    peg_ratio: float | None = None
    trailing_pe: float | None = None
    forward_pe: float | None = None
    forward_growth: float | None = None
    # 增长质量
    growth_quality: dict | None = None  # {rev_cagr, ni_cagr, ocf_cagr, fcf_cagr}
    # 毛利率趋势
    gross_margin_trend: list[dict] | None = None
    # 综合
    growth_rating: str = ""
    growth_attitude: str = ""  # 加速/稳定/减速


@dataclass
class TechnicalDeep:
    """技术面深度分析结果。"""
    # 日线
    daily_ma: dict | None = None  # {ma5, ma20, ma50, ma200, alignment}
    weekly_ma: dict | None = None  # {w10, w30, trend}
    # MACD
    macd: dict | None = None  # {line, signal, histogram, trend, divergence, last_cross}
    # RSI
    rsi: dict | None = None  # {value, status, trend, divergence}
    # 布林带
    bollinger: dict | None = None  # {upper, mid, lower, pct_b, bandwidth}
    # ATR
    atr: dict | None = None  # {value, pct, volatility}
    # 关键价位
    support_resistance: list[dict] | None = None  # [{type, price, source, strength}]
    week_52: dict | None = None  # {high, low, days_from_high, days_from_low, pct_from_high, pct_from_low}
    # 成交量
    volume_analysis: dict | None = None  # {today, avg_5d, avg_20d, ratio, price_volume}
    # 信号汇总
    signal_summary: list[dict] | None = None  # [{indicator, signal, direction, strength}]
    overall_signal: str = ""
    bullish_count: int = 0
    bearish_count: int = 0
    neutral_count: int = 0


@dataclass
class FundamentalsDeep:
    """基本面深度分析结果。"""
    # 估值全景
    valuation_metrics: list[dict] | None = None  # [{metric, current, industry, hist_5y, verdict}]
    # 利润率趋势
    margin_trend: list[dict] | None = None  # [{quarter, gross, operating, net, trend}]
    # 资本回报
    return_metrics: list[dict] | None = None  # [{quarter, roe, roa, roic}]
    dupont: dict | None = None  # {net_margin, asset_turnover, equity_multiplier, driver}
    # 资产负债表
    balance_trend: list[dict] | None = None  # [{quarter, current_ratio, quick_ratio, de_ratio, cash_pct}]
    # 现金流
    cashflow_trend: list[dict] | None = None  # [{quarter, ocf, ni, ocf_ni_ratio, fcf}]
    # CapEx
    capex_trend: list[dict] | None = None  # [{year, capex, capex_rev_pct, capex_ocf_pct}]
    # 综合
    health_rating: str = ""


@dataclass
class PeersDeep:
    """同行对比深度分析结果。"""
    target_ticker: str = ""
    peers: list[dict] | None = None  # [{ticker, name, market_cap, sector}]
    # 对比矩阵
    valuation_matrix: list[dict] | None = None  # [{company, pe, ps, pb, ev_ebitda, peg}]
    profitability_matrix: list[dict] | None = None  # [{company, gross_margin, net_margin, roe, roa}]
    growth_matrix: list[dict] | None = None  # [{company, rev_growth, eps_growth, fwd_growth}]
    health_matrix: list[dict] | None = None  # [{company, current_ratio, de_ratio, fcf}]
    # 排名
    rankings: list[dict] | None = None  # [{dimension, vs_peers, rank, assessment}]
    # 综合
    competitive_position: str = ""
    strengths: list[str] | None = None
    weaknesses: list[str] | None = None


@dataclass
class DividendsDeep:
    """股息深度分析结果。"""
    # 概览
    current_price: float | None = None
    annual_dividend: float | None = None
    dividend_yield: float | None = None
    payment_frequency: str | None = None
    ex_dividend_date: str | None = None
    # 安全性
    payout_ratio: float | None = None
    payout_status: str = ""
    fcf_coverage: float | None = None
    fcf_coverage_status: str = ""
    earnings_vs_div_growth: dict | None = None  # {earnings_g, div_g, sustainable}
    # 增长
    yearly_dividends: list[dict] | None = None  # [{year, amount, yoy_growth}]
    cagr_5y: float | None = None
    cagr_3y: float | None = None
    last_raise_pct: float | None = None
    consecutive_years: int | None = None
    is_aristocrat: bool = False
    # 安全评分
    safety_score: int = 0
    safety_factors: list[dict] | None = None  # [{factor, contribution, description}]
    # 评级
    income_rating: str = ""
    summary: str = ""


# ============================================================================
# 路由函数
# ============================================================================

def run_deep_analysis(domain: str, data: StockData, signal, verbose: bool = False):
    """根据领域路由到对应深度分析函数。"""
    if verbose:
        print(f"Fetching deep data for {data.ticker}...", file=sys.stderr)
    data = fetch_deep_data(data, verbose=verbose)

    dispatch = {
        "valuation": _analyze_valuation_deep,
        "growth": _analyze_growth_deep,
        "technical": _analyze_technical_deep,
        "fundamentals": _analyze_fundamentals_deep,
        "peers": _analyze_peers_deep,
        "dividends": _analyze_dividends_deep,
    }

    fn = dispatch.get(domain)
    if fn is None:
        return None
    return fn(data, signal, verbose=verbose)


# ============================================================================
# 1. 估值深度分析
# ============================================================================

def _analyze_valuation_deep(data: StockData, signal, verbose: bool = False) -> ValuationDeep:
    result = ValuationDeep()
    info = data.info

    result.current_price = info.get("regularMarketPrice") or info.get("currentPrice")

    # sharesOutstanding：降级链 EDGAR > yfinance > marketCap/price
    shares = None
    if hasattr(data, "sec_data") and data.sec_data and data.sec_data.shares_outstanding:
        shares = data.sec_data.shares_outstanding
    if not shares or shares < 1_000_000:
        shares = info.get("sharesOutstanding")
    if not shares or shares < 1_000_000:
        mkt_cap = info.get("marketCap")
        price = result.current_price
        if mkt_cap and price and price > 0:
            shares = mkt_cap / price
        else:
            shares = None

    total_debt = info.get("totalDebt") or 0
    total_cash = info.get("totalCash") or 0

    # 数据来源追踪
    sources: dict[str, str] = {}

    # DCF 参数 — FCF 降级链：EDGAR > 季度 TTM > info
    fcf_ttm, fcf_source = _get_best_fcf(data, info)
    result.fcf_ttm = fcf_ttm
    sources["fcf"] = fcf_source

    # Beta：范围校验 0.3-3.0，超限用 1.2（科技行业合理默认值）
    raw_beta = info.get("beta")
    beta = raw_beta if raw_beta is not None else 1.2
    if beta < 0.3 or beta > 3.0:
        sources["beta"] = f"假设值 1.2（原始值 {raw_beta} 超出 0.3-3.0 范围）"
        beta = 1.2
    elif raw_beta is None:
        sources["beta"] = "假设值 1.2（API 返回 None）"
    else:
        sources["beta"] = f"Yahoo Finance（{beta:.2f}）"

    risk_free = _get_risk_free_rate()
    sources["risk_free"] = f"10Y 美债（{risk_free*100:.2f}%）" if risk_free != 0.045 else "假设值 4.50%（API 获取失败）"

    market_premium = 0.06
    wacc = risk_free + beta * market_premium
    result.wacc = round(wacc * 100, 2)

    # 增长率估算 — 降级链：自计算 > info > 假设值
    raw_rg = _calc_revenue_growth(data)
    raw_eg = _calc_earnings_growth(data)
    growth_parts = []

    if raw_rg is not None:
        growth_parts.append(f"revenue={raw_rg*100:.1f}%（季度 TTM YoY 自计算）")
    else:
        raw_rg = info.get("revenueGrowth")
        if raw_rg is not None:
            growth_parts.append(f"revenue={raw_rg*100:.1f}%（Yahoo info）")

    if raw_eg is not None:
        growth_parts.append(f"earnings={raw_eg*100:.1f}%（EPS TTM YoY 自计算）")
    else:
        raw_eg = info.get("earningsGrowth")
        if raw_eg is not None:
            growth_parts.append(f"earnings={raw_eg*100:.1f}%（Yahoo info）")

    earnings_g = raw_eg if raw_eg is not None else 0.1
    revenue_g = raw_rg if raw_rg is not None else 0.1
    if raw_eg is None:
        growth_parts.append("earningsGrowth=None→假设值 10%")
    if raw_rg is None:
        growth_parts.append("revenueGrowth=None→假设值 10%")

    base_g = max(0.02, min(0.30, (earnings_g + revenue_g) / 2))
    sources["growth"] = "；".join(growth_parts) if growth_parts else "无数据"

    result.data_sources = sources
    result.growth_rates = {
        "conservative": round((base_g * 0.6) * 100, 1),
        "base": round(base_g * 100, 1),
        "optimistic": round((base_g * 1.4) * 100, 1),
    }

    # DCF 三情景（需 shares 有效）
    if fcf_ttm and fcf_ttm > 0 and result.current_price and shares:
        scenarios = []
        for label, g_mult in [("conservative", 0.6), ("base", 1.0), ("optimistic", 1.4)]:
            g = base_g * g_mult
            terminal_g = 0.025 + (g_mult - 0.6) * 0.0125
            projections = []
            pv_sum = 0.0
            fcf = fcf_ttm
            for yr in range(1, 6):
                fcf = fcf * (1 + g)
                pv = fcf / ((1 + wacc) ** yr)
                pv_sum += pv
                projections.append({"year": yr, "fcf": round(fcf, 2), "pv": round(pv, 2)})

            # 防护：wacc 必须大于 terminal_g，否则 Gordon 模型失效
            if wacc <= terminal_g + 0.005:
                terminal = fcf * 20  # 回退：20x FCF 作为终端价值上限
            else:
                terminal = fcf * (1 + terminal_g) / (wacc - terminal_g)
            pv_terminal = terminal / ((1 + wacc) ** 5)
            ev = pv_sum + pv_terminal
            equity_value = ev + total_cash - total_debt
            per_share = equity_value / shares if shares > 0 else 0

            vs_current = ((per_share - result.current_price) / result.current_price * 100) if result.current_price else 0
            scenarios.append({
                "scenario": label,
                "value": round(per_share, 2),
                "vs_current": round(vs_current, 1),
                "verdict": "低估" if vs_current > 10 else ("高估" if vs_current < -10 else "合理"),
            })

            if label == "base":
                result.dcf_value = round(per_share, 2)
                result.safety_margin_pct = round(vs_current, 1)
                result.fcf_projections = projections
                result.terminal_value = round(terminal)
                result.enterprise_value = round(ev)

        result.dcf_scenarios = scenarios

    # 历史估值范围（用 price_history_2y 近似 5 年，实际可能只有 2 年）
    hist = data.price_history_2y
    if hist is not None and not hist.empty and len(hist) > 60:
        trailing_eps = info.get("trailingEps")
        if trailing_eps and trailing_eps > 0:
            pe_series = hist["Close"] / trailing_eps
            result.pe_range = _range_stats(pe_series, info.get("trailingPE"))

        rev_per_share = info.get("revenuePerShare")
        if rev_per_share and rev_per_share > 0:
            ps_series = hist["Close"] / rev_per_share
            current_ps = info.get("priceToSalesTrailing12Months")
            result.ps_range = _range_stats(ps_series, current_ps)

    # 行业相对估值 — 用同行数据填充行业中位数（v12）
    industry_comps = []
    sector = info.get("sector")
    industry = info.get("industry")
    if sector:
        from .sentiment import _select_peers
        peer_tickers = _select_peers(data.ticker, sector, industry, market_cap=info.get("marketCap"))
        peer_infos = []
        for pt in peer_tickers:
            try:
                pi = yf.Ticker(pt).info
                peer_infos.append(pi)
            except Exception:
                continue

        def _median(key):
            vals = [p.get(key) for p in peer_infos if p.get(key) and p.get(key) > 0]
            return sorted(vals)[len(vals) // 2] if vals else None

        for metric, key in [
            ("P/E", "trailingPE"),
            ("P/S", "priceToSalesTrailing12Months"),
            ("P/B", "priceToBook"),
            ("EV/EBITDA", "enterpriseToEbitda"),
        ]:
            stock_val = info.get(key)
            ind_val = _median(key) if peer_infos else None
            premium = None
            if stock_val and ind_val and ind_val > 0:
                premium = round(((stock_val - ind_val) / ind_val) * 100, 1)
            if stock_val or ind_val:
                industry_comps.append({
                    "metric": metric,
                    "stock": round(stock_val, 2) if stock_val else None,
                    "industry": round(ind_val, 2) if ind_val else None,
                    "premium": premium,
                })
    result.industry_comparison = industry_comps if industry_comps else None

    # 综合判定
    if result.dcf_scenarios:
        base = next((s for s in result.dcf_scenarios if s["scenario"] == "base"), None)
        if base:
            if base["vs_current"] > 20:
                result.verdict = "被低估"
            elif base["vs_current"] < -20:
                result.verdict = "被高估"
            else:
                result.verdict = "合理"

    return result


def _range_stats(series: pd.Series, current_val) -> dict | None:
    """计算范围统计。"""
    try:
        clean = series.dropna()
        clean = clean[(clean > 0) & (clean < clean.quantile(0.99))]
        if len(clean) < 30:
            return None
        low = round(float(clean.quantile(0.05)), 2)
        median = round(float(clean.median()), 2)
        high = round(float(clean.quantile(0.95)), 2)
        if current_val:
            pct = round(float((current_val - low) / (high - low) * 100), 1) if high > low else 50
        else:
            pct = 50
        return {
            "low": low, "median": median, "high": high,
            "current": round(current_val, 2) if current_val else None,
            "percentile": max(0, min(100, pct)),
        }
    except Exception:
        return None


# ============================================================================
# 2. 成长性深度分析
# ============================================================================

def _analyze_growth_deep(data: StockData, signal, verbose: bool = False) -> GrowthDeep:
    result = GrowthDeep()
    info = data.info
    qf = data.quarterly_financials
    qc = data.quarterly_cashflow

    # 季度营收
    if qf is not None and not qf.empty:
        rev_row = _get_row(qf, ["Total Revenue", "Revenue"])
        if rev_row is not None:
            quarterly_rev = []
            values = rev_row.dropna().sort_index()
            for i, (dt, val) in enumerate(values.items()):
                q_label = f"{dt.year}Q{(dt.month - 1) // 3 + 1}"
                yoy = None
                if i >= 4:
                    prev = values.iloc[i - 4]
                    if prev > 0:
                        yoy = round((val - prev) / prev * 100, 1)
                qoq = None
                if i >= 1:
                    prev_q = values.iloc[i - 1]
                    if prev_q > 0:
                        qoq = round((val - prev_q) / prev_q * 100, 1)
                quarterly_rev.append({
                    "quarter": q_label, "revenue": round(float(val)),
                    "yoy": yoy, "qoq": qoq,
                })
            result.quarterly_revenue = quarterly_rev[-8:]  # 最近 8 季

            # 年度汇总（仅保留完整年份：4 个季度）
            yearly = {}
            q_count = {}
            for dt, val in values.items():
                yr = dt.year
                yearly[yr] = yearly.get(yr, 0) + float(val)
                q_count[yr] = q_count.get(yr, 0) + 1
            # 过滤不完整年份（< 4 季度）
            complete_years = {yr: rev for yr, rev in yearly.items() if q_count[yr] >= 4}
            annual = []
            sorted_years = sorted(complete_years.keys())
            for i, yr in enumerate(sorted_years):
                yoy = None
                if i >= 1:
                    prev_yr = sorted_years[i - 1]
                    if complete_years[prev_yr] > 0:
                        yoy = round((complete_years[yr] - complete_years[prev_yr]) / complete_years[prev_yr] * 100, 1)
                annual.append({"year": yr, "revenue": round(complete_years[yr]), "yoy": yoy})
            result.annual_revenue = annual[-5:]

            # CAGR
            if len(annual) >= 4:
                result.rev_cagr_3y = _cagr(annual[-4]["revenue"], annual[-1]["revenue"], 3)
            if len(annual) >= 6:
                result.rev_cagr_5y = _cagr(annual[-6]["revenue"], annual[-1]["revenue"], 5)

    # 季度 EPS（从 earnings_history）
    if data.earnings_history is not None and not data.earnings_history.empty:
        eps_data = []
        recent = data.earnings_history.sort_index(ascending=False).head(8)
        for dt, row in recent.iterrows():
            actual = row.get("Reported EPS")
            estimate = row.get("EPS Estimate")
            if pd.notna(actual):
                surprise = None
                if pd.notna(estimate) and estimate != 0:
                    surprise = round((float(actual) - float(estimate)) / abs(float(estimate)) * 100, 1)
                # 回退约 46 天对齐财报期末（SEC 要求 40-45 天内提交 10-Q）
                if hasattr(dt, 'year'):
                    from datetime import timedelta
                    adj = dt - timedelta(days=46)
                    q_label = f"{adj.year}Q{(adj.month - 1) // 3 + 1}"
                else:
                    q_label = str(dt)[:7]
                eps_data.append({
                    "quarter": q_label,
                    "actual": round(float(actual), 2),
                    "estimate": round(float(estimate), 2) if pd.notna(estimate) else None,
                    "surprise": surprise,
                    "yoy": None,
                })
        result.quarterly_eps = list(reversed(eps_data))

    # 净利率趋势
    if qf is not None and not qf.empty:
        rev_row = _get_row(qf, ["Total Revenue", "Revenue"])
        ni_row = _get_row(qf, ["Net Income", "Net Income Common Stockholders"])
        if rev_row is not None and ni_row is not None:
            margin_data = []
            for dt in rev_row.dropna().sort_index().index:
                if dt in ni_row.index and pd.notna(ni_row[dt]) and pd.notna(rev_row[dt]) and rev_row[dt] != 0:
                    nm = round(float(ni_row[dt]) / float(rev_row[dt]) * 100, 1)
                    q_label = f"{dt.year}Q{(dt.month - 1) // 3 + 1}"
                    margin_data.append({"quarter": q_label, "net_margin": nm})
            result.margin_trend = margin_data[-8:]

    # PEG 和前瞻
    result.peg_ratio = info.get("pegRatio")
    result.trailing_pe = info.get("trailingPE")
    result.forward_pe = info.get("forwardPE")
    result.forward_growth = info.get("earningsGrowth")
    if result.forward_growth:
        result.forward_growth = round(result.forward_growth * 100, 1)

    # PEG 手动计算回退：优先用 Forward P/E（与「前瞻 PEG」标签一致）
    if result.peg_ratio is None:
        eg = info.get("earningsGrowth")
        pe = result.forward_pe or result.trailing_pe
        if pe and eg and eg > 0:
            result.peg_ratio = round(pe / (eg * 100), 2)

    # 分析师预测
    fwd_eps = info.get("forwardEps")
    trailing_eps = info.get("trailingEps")
    if fwd_eps and trailing_eps and trailing_eps > 0:
        result.analyst_forecasts = {
            "forward_eps": round(fwd_eps, 2),
            "trailing_eps": round(trailing_eps, 2),
            "eps_growth_pct": round((fwd_eps - trailing_eps) / abs(trailing_eps) * 100, 1),
        }

    # 增长质量（现金流 vs 利润）
    if qc is not None and not qc.empty and qf is not None:
        quality = {}
        ocf_row = _get_row(qc, ["Operating Cash Flow", "Total Cash From Operating Activities"])
        fcf_row = _get_row(qc, ["Free Cash Flow"])
        ni_row = _get_row(qf, ["Net Income", "Net Income Common Stockholders"])
        rev_row = _get_row(qf, ["Total Revenue", "Revenue"])

        for label, row in [("ocf", ocf_row), ("fcf", fcf_row), ("ni", ni_row), ("rev", rev_row)]:
            if row is not None:
                vals = row.dropna().sort_index()
                # TTM 对比消除季节性：最近 4 季 vs 前 4 季 → YoY 增长
                if len(vals) >= 8:
                    recent_ttm = sum(float(v) for v in vals.iloc[-4:])
                    old_ttm = sum(float(v) for v in vals.iloc[-8:-4])
                    if old_ttm > 0:
                        quality[f"{label}_cagr"] = round((recent_ttm / old_ttm - 1) * 100, 1)
                elif len(vals) >= 5:
                    # 回退：同季 YoY（最近一季 vs 4 季前 = 1 年前同季）
                    recent_q = float(vals.iloc[-1])
                    old_q = float(vals.iloc[-5])
                    if old_q > 0:
                        quality[f"{label}_cagr"] = round((recent_q / old_q - 1) * 100, 1)
        result.growth_quality = quality if quality else None

    # rev_cagr_3y 回退：年度数据不足时用季度数据推算
    if result.rev_cagr_3y is None:
        rev_cagr_from_q = (result.growth_quality or {}).get("rev_cagr")
        if rev_cagr_from_q is not None:
            result.rev_cagr_3y = rev_cagr_from_q

    # 毛利率趋势
    if qf is not None and not qf.empty:
        gp_row = _get_row(qf, ["Gross Profit"])
        rev_row = _get_row(qf, ["Total Revenue", "Revenue"])
        if gp_row is not None and rev_row is not None:
            gm_data = []
            for dt in gp_row.dropna().sort_index().index:
                if dt in rev_row.index and pd.notna(rev_row[dt]) and rev_row[dt] != 0:
                    gm = round(float(gp_row[dt]) / float(rev_row[dt]) * 100, 1)
                    q_label = f"{dt.year}Q{(dt.month - 1) // 3 + 1}"
                    gm_data.append({"quarter": q_label, "gross_margin": gm})
            result.gross_margin_trend = gm_data[-8:]

    # 综合评级（多信号：CAGR、PEG、最新季度 YoY、净利润趋势）
    scores = []
    if result.rev_cagr_3y:
        scores.append("A" if result.rev_cagr_3y > 20 else ("B" if result.rev_cagr_3y > 10 else ("C" if result.rev_cagr_3y > 5 else "D")))
    if result.peg_ratio:
        scores.append("A" if result.peg_ratio < 1 else ("B" if result.peg_ratio < 2 else "C"))

    # 补充信号：最新季度 YoY（当 CAGR/PEG 不可用时兜底）
    if result.quarterly_revenue:
        recent_yoy = next((q["yoy"] for q in reversed(result.quarterly_revenue) if q["yoy"] is not None), None)
        if recent_yoy is not None:
            scores.append("A" if recent_yoy > 25 else ("B" if recent_yoy > 10 else ("C" if recent_yoy > 0 else "D")))

    # 补充信号：净利润 CAGR（从 growth_quality 字典）
    ni_cagr = (result.growth_quality or {}).get("ni_cagr")
    if ni_cagr is not None:
        scores.append("A" if ni_cagr > 20 else ("B" if ni_cagr > 10 else ("C" if ni_cagr > 0 else "D")))

    rating_map = {"A": 4, "B": 3, "C": 2, "D": 1}
    if scores:
        avg = sum(rating_map.get(s, 2) for s in scores) / len(scores)
        result.growth_rating = "A" if avg >= 3.5 else ("B" if avg >= 2.5 else ("C" if avg >= 1.5 else "D"))
    else:
        result.growth_rating = "C"

    # 增长态势（YoY 优先，QoQ 回退）
    if result.quarterly_revenue and len(result.quarterly_revenue) >= 3:
        recent_yoys = [q["yoy"] for q in result.quarterly_revenue[-4:] if q["yoy"] is not None]
        if len(recent_yoys) >= 2:
            if recent_yoys[-1] > recent_yoys[0]:
                result.growth_attitude = "加速"
            elif recent_yoys[-1] < recent_yoys[0]:
                result.growth_attitude = "减速"
            else:
                result.growth_attitude = "稳定"
        else:
            # YoY 不足，用 QoQ 趋势判断
            recent_qoqs = [q["qoq"] for q in result.quarterly_revenue[-4:] if q.get("qoq") is not None]
            if len(recent_qoqs) >= 2:
                positives = sum(1 for q in recent_qoqs if q > 0)
                if positives >= len(recent_qoqs) * 0.7:
                    result.growth_attitude = "扩张"
                elif positives <= len(recent_qoqs) * 0.3:
                    result.growth_attitude = "收缩"
                else:
                    result.growth_attitude = "波动"

    return result


def _get_row(df: pd.DataFrame, names: list[str]) -> pd.Series | None:
    """从 DataFrame 获取指定行名。"""
    for name in names:
        if name in df.index:
            return df.loc[name]
    return None


def _cagr(start: float, end: float, years: int) -> float | None:
    """计算 CAGR。"""
    if start <= 0 or end <= 0 or years <= 0:
        return None
    return round(((end / start) ** (1 / years) - 1) * 100, 1)


# ============================================================================
# 3. 技术面深度分析
# ============================================================================

def _analyze_technical_deep(data: StockData, signal, verbose: bool = False) -> TechnicalDeep:
    result = TechnicalDeep()
    hist = data.price_history_2y if data.price_history_2y is not None else data.price_history
    if hist is None or hist.empty:
        return result

    close = hist["Close"]
    current = float(close.iloc[-1])
    p = TECHNICAL_PARAMS

    # 日线均线
    ma5 = _ma(close, 5)
    ma20 = _ma(close, 20)
    ma50 = _ma(close, 50)
    ma200 = _ma(close, 200)

    alignment = "mixed"
    if ma5 and ma20 and ma50 and ma200:
        if ma5 > ma20 > ma50 > ma200:
            alignment = "多头排列"
        elif ma5 < ma20 < ma50 < ma200:
            alignment = "空头排列"

    result.daily_ma = {
        "ma5": ma5, "ma20": ma20, "ma50": ma50, "ma200": ma200,
        "alignment": alignment,
    }

    # 周线均线（用日线近似）
    weekly_close = close.resample("W").last().dropna()
    w10 = _ma(weekly_close, 10)
    w30 = _ma(weekly_close, 30)
    w_trend = "横盘"
    if w10 and w30:
        if w10 > w30:
            w_trend = "上升"
        elif w10 < w30:
            w_trend = "下降"
    result.weekly_ma = {"w10": w10, "w30": w30, "trend": w_trend}

    # MACD
    ema_fast = close.ewm(span=p["macd_fast"], adjust=False).mean()
    ema_slow = close.ewm(span=p["macd_slow"], adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=p["macd_signal"], adjust=False).mean()
    histogram = macd_line - signal_line

    macd_val = round(float(macd_line.iloc[-1]), 4)
    signal_val = round(float(signal_line.iloc[-1]), 4)
    hist_val = round(float(histogram.iloc[-1]), 4)

    # 背离检测
    divergence = "无背离"
    if len(close) > 20:
        price_high = close.iloc[-20:].max() == close.iloc[-5:].max()
        macd_high = macd_line.iloc[-20:].max() == macd_line.iloc[-5:].max()
        price_low = close.iloc[-20:].min() == close.iloc[-5:].min()
        macd_low = macd_line.iloc[-20:].min() == macd_line.iloc[-5:].min()
        if price_high and not macd_high and close.iloc[-1] > close.iloc[-10]:
            divergence = "顶背离"
        elif price_low and not macd_low and close.iloc[-1] < close.iloc[-10]:
            divergence = "底背离"

    # 最近交叉
    last_cross = "无"
    cross_days = None
    for i in range(len(histogram) - 1, max(0, len(histogram) - 30), -1):
        if i > 0:
            if histogram.iloc[i] > 0 and histogram.iloc[i-1] <= 0:
                last_cross = "金叉"
                cross_days = len(histogram) - 1 - i
                break
            elif histogram.iloc[i] < 0 and histogram.iloc[i-1] >= 0:
                last_cross = "死叉"
                cross_days = len(histogram) - 1 - i
                break

    result.macd = {
        "line": macd_val, "signal": signal_val, "histogram": hist_val,
        "trend": "看多" if hist_val > 0 else "看空",
        "histogram_expanding": abs(hist_val) > abs(float(histogram.iloc[-2])) if len(histogram) > 1 else False,
        "divergence": divergence,
        "last_cross": last_cross,
        "cross_days_ago": cross_days,
    }

    # RSI
    rsi_val = _calculate_rsi(close, p["rsi_period"])
    rsi_status = "中性"
    if rsi_val:
        if rsi_val > 70:
            rsi_status = "超买"
        elif rsi_val < 30:
            rsi_status = "超卖"
    result.rsi = {"value": rsi_val, "status": rsi_status, "trend": "—", "divergence": "无背离"}

    # 布林带
    bb_mid = close.rolling(p["bb_period"]).mean()
    bb_std = close.rolling(p["bb_period"]).std()
    bb_upper = bb_mid + p["bb_std"] * bb_std
    bb_lower = bb_mid - p["bb_std"] * bb_std

    if len(bb_upper.dropna()) > 0:
        upper = round(float(bb_upper.iloc[-1]), 2)
        lower = round(float(bb_lower.iloc[-1]), 2)
        mid = round(float(bb_mid.iloc[-1]), 2)
        bandwidth = round((upper - lower) / mid * 100, 2) if mid > 0 else 0
        pct_b = round((current - lower) / (upper - lower) * 100, 1) if upper > lower else 50
        result.bollinger = {
            "upper": upper, "mid": mid, "lower": lower,
            "pct_b": pct_b,
            "bandwidth": bandwidth,
            "bandwidth_status": "收窄" if bandwidth < 5 else ("扩张" if bandwidth > 15 else "正常"),
        }

    # ATR
    if len(hist) > 14:
        high = hist["High"]
        low = hist["Low"]
        prev_close = close.shift(1)
        tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
        atr = float(tr.rolling(14).mean().iloc[-1])
        atr_pct = round(atr / current * 100, 2) if current > 0 else 0
        result.atr = {
            "value": round(atr, 2),
            "pct": atr_pct,
            "volatility": "高" if atr_pct > 3 else ("低" if atr_pct < 1.5 else "中"),
        }

    # 52 周位置
    info = data.info
    high_52w = info.get("fiftyTwoWeekHigh")
    low_52w = info.get("fiftyTwoWeekLow")
    if high_52w and low_52w:
        pct_from_high = round((current - high_52w) / high_52w * 100, 1) if high_52w else 0
        pct_from_low = round((current - low_52w) / low_52w * 100, 1) if low_52w else 0
        result.week_52 = {
            "high": high_52w, "low": low_52w,
            "pct_from_high": pct_from_high,
            "pct_from_low": pct_from_low,
        }

    # 支撑阻力
    levels = []
    if result.bollinger:
        levels.append({"type": "支撑", "price": result.bollinger["lower"], "source": "BB 下轨", "strength": "中"})
        levels.append({"type": "阻力", "price": result.bollinger["upper"], "source": "BB 上轨", "strength": "中"})
    if ma50:
        levels.append({"type": "支撑" if current > ma50 else "阻力", "price": ma50, "source": "MA50", "strength": "中"})
    if ma200:
        levels.append({"type": "支撑" if current > ma200 else "阻力", "price": ma200, "source": "MA200", "strength": "强"})
    if low_52w:
        levels.append({"type": "强支撑", "price": low_52w, "source": "52 周低点", "strength": "强"})
    if high_52w:
        levels.append({"type": "强阻力", "price": high_52w, "source": "52 周高点", "strength": "强"})
    result.support_resistance = sorted(levels, key=lambda x: x["price"])

    # 成交量
    if "Volume" in hist.columns and len(hist) >= 25:
        today_vol = int(hist["Volume"].iloc[-1])
        avg_5d = int(hist["Volume"].iloc[-5:].mean())
        avg_20d = int(hist["Volume"].iloc[-20:].mean())
        ratio = round(avg_5d / avg_20d, 2) if avg_20d > 0 else 1.0
        price_5d = float(close.iloc[-1] - close.iloc[-5]) / float(close.iloc[-5]) * 100 if len(close) >= 5 else 0

        if ratio > 1.3 and price_5d > 0:
            pv = "量增价涨"
        elif ratio > 1.3 and price_5d < 0:
            pv = "量增价跌"
        elif ratio < 0.7 and price_5d > 0:
            pv = "量减价涨"
        elif ratio < 0.7 and price_5d < 0:
            pv = "量减价跌"
        else:
            pv = "正常"

        result.volume_analysis = {
            "today": today_vol, "avg_5d": avg_5d, "avg_20d": avg_20d,
            "ratio": ratio, "price_volume": pv,
        }

    # 信号汇总
    signals = []
    bull = bear = neutral = 0

    def add_signal(indicator, sig, direction, strength):
        nonlocal bull, bear, neutral
        signals.append({"indicator": indicator, "signal": sig, "direction": direction, "strength": strength})
        if direction == "多":
            bull += 1
        elif direction == "空":
            bear += 1
        else:
            neutral += 1

    # 均线
    if alignment == "多头排列":
        add_signal("均线排列", "多头排列", "多", "强")
    elif alignment == "空头排列":
        add_signal("均线排列", "空头排列", "空", "强")
    else:
        add_signal("均线排列", "混合", "中", "弱")

    # MACD
    if result.macd:
        if result.macd["trend"] == "看多":
            add_signal("MACD", result.macd.get("last_cross", "看多"), "多", "中")
        else:
            add_signal("MACD", result.macd.get("last_cross", "看空"), "空", "中")

    # RSI
    if rsi_status == "超买":
        add_signal("RSI", f"RSI {rsi_val:.0f}", "空", "中")
    elif rsi_status == "超卖":
        add_signal("RSI", f"RSI {rsi_val:.0f}", "多", "中")
    else:
        add_signal("RSI", f"RSI {rsi_val:.0f}" if rsi_val else "N/A", "中", "弱")

    # 布林带
    if result.bollinger:
        pct_b = result.bollinger["pct_b"]
        if pct_b > 80:
            add_signal("布林带", f"%B {pct_b:.0f}", "空", "弱")
        elif pct_b < 20:
            add_signal("布林带", f"%B {pct_b:.0f}", "多", "弱")
        else:
            add_signal("布林带", f"%B {pct_b:.0f}", "中", "弱")

    # 成交量
    if result.volume_analysis:
        pv = result.volume_analysis["price_volume"]
        if pv == "量增价涨":
            add_signal("成交量", pv, "多", "中")
        elif pv == "量增价跌":
            add_signal("成交量", pv, "空", "中")
        else:
            add_signal("成交量", pv, "中", "弱")

    # 趋势
    if w_trend == "上升":
        add_signal("中期趋势", "上升", "多", "强")
    elif w_trend == "下降":
        add_signal("中期趋势", "下降", "空", "强")
    else:
        add_signal("中期趋势", "横盘", "中", "弱")

    result.signal_summary = signals
    result.bullish_count = bull
    result.bearish_count = bear
    result.neutral_count = neutral
    result.overall_signal = "偏多" if bull > bear + 1 else ("偏空" if bear > bull + 1 else "中性")

    return result


def _ma(series: pd.Series, period: int) -> float | None:
    """计算移动平均。"""
    ma = series.rolling(period).mean()
    clean = ma.dropna()
    if len(clean) == 0:
        return None
    return round(float(clean.iloc[-1]), 2)


def _calculate_rsi(prices: pd.Series, period: int = 14) -> float | None:
    """RSI 计算。"""
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


# ============================================================================
# 4. 基本面深度分析
# ============================================================================

def _analyze_fundamentals_deep(data: StockData, signal, verbose: bool = False) -> FundamentalsDeep:
    result = FundamentalsDeep()
    info = data.info
    qf = data.quarterly_financials
    qbs = data.quarterly_balance_sheet
    qc = data.quarterly_cashflow

    # 估值全景（板块感知阈值 + 同行中位数）
    sector = info.get("sector", "")
    industry = info.get("industry", "")

    # 获取同行数据作为行业中位数
    peer_medians = {}
    try:
        peer_tickers = _select_peers(data.ticker, sector, industry, market_cap=info.get("marketCap"))
        peer_vals: dict[str, list[float]] = {}
        for pt in peer_tickers:
            try:
                pi = yf.Ticker(pt).info
                for key in ["trailingPE", "priceToSalesTrailing12Months", "priceToBook", "enterpriseToEbitda"]:
                    v = pi.get(key)
                    if v and v > 0:
                        peer_vals.setdefault(key, []).append(v)
            except Exception:
                continue
        for key, vals in peer_vals.items():
            if vals:
                vals.sort()
                peer_medians[key] = round(vals[len(vals) // 2], 2)
    except Exception:
        pass

    metrics = []
    for name, key in [
        ("P/E", "trailingPE"), ("PEG", "pegRatio"),
        ("P/S", "priceToSalesTrailing12Months"), ("P/B", "priceToBook"),
        ("EV/EBITDA", "enterpriseToEbitda"),
    ]:
        val = info.get(key)
        if val:
            verdict = _judge_valuation(name, val, sector)
            ind_val = peer_medians.get(key)
            metrics.append({"metric": name, "current": round(val, 2), "industry": ind_val, "hist_5y": None, "verdict": verdict})
    result.valuation_metrics = metrics if metrics else None

    # 利润率趋势
    if qf is not None and not qf.empty:
        rev = _get_row(qf, ["Total Revenue", "Revenue"])
        gp = _get_row(qf, ["Gross Profit"])
        oi = _get_row(qf, ["Operating Income", "EBIT"])
        ni = _get_row(qf, ["Net Income", "Net Income Common Stockholders"])

        if rev is not None:
            margin_data = []
            for dt in rev.dropna().sort_index().index:
                entry = {"quarter": f"{dt.year}Q{(dt.month - 1) // 3 + 1}"}
                rv = float(rev[dt]) if pd.notna(rev[dt]) else 0
                if rv > 0:
                    if gp is not None and dt in gp.index and pd.notna(gp[dt]):
                        entry["gross"] = round(float(gp[dt]) / rv * 100, 1)
                    if oi is not None and dt in oi.index and pd.notna(oi[dt]):
                        entry["operating"] = round(float(oi[dt]) / rv * 100, 1)
                    if ni is not None and dt in ni.index and pd.notna(ni[dt]):
                        entry["net"] = round(float(ni[dt]) / rv * 100, 1)
                margin_data.append(entry)
            result.margin_trend = margin_data[-8:]

    # 资本回报
    return_data = []
    roe_val = info.get("returnOnEquity")
    roa_val = info.get("returnOnAssets")
    if roe_val or roa_val:
        return_data.append({
            "quarter": "TTM",
            "roe": round(roe_val * 100, 1) if roe_val else None,
            "roa": round(roa_val * 100, 1) if roa_val else None,
            "roic": None,
        })
    result.return_metrics = return_data if return_data else None

    # 杜邦分解
    nm = info.get("profitMargins")
    rev_ps = info.get("revenuePerShare")
    book_val = info.get("bookValue")
    if nm and roe_val:
        result.dupont = {
            "net_margin": round(nm * 100, 1),
            "roe": round(roe_val * 100, 1),
            "driver": "利润率驱动" if nm > 0.15 else "杠杆驱动",
        }

    # 资产负债表趋势
    if qbs is not None and not qbs.empty:
        balance_data = []
        ca = _get_row(qbs, ["Current Assets", "Total Current Assets"])
        cl = _get_row(qbs, ["Current Liabilities", "Total Current Liabilities"])
        td = _get_row(qbs, ["Total Debt", "Long Term Debt"])
        te = _get_row(qbs, ["Total Stockholders Equity", "Stockholders Equity", "Total Equity Gross Minority Interest"])
        cash = _get_row(qbs, ["Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments"])

        dates = qbs.columns[:8]
        for dt in sorted(dates):
            entry = {"quarter": f"{dt.year}Q{(dt.month - 1) // 3 + 1}"}
            if ca is not None and cl is not None and dt in ca.index and dt in cl.index:
                ca_val = float(ca[dt]) if pd.notna(ca[dt]) else 0
                cl_val = float(cl[dt]) if pd.notna(cl[dt]) else 1
                if cl_val > 0:
                    entry["current_ratio"] = round(ca_val / cl_val, 2)
            if td is not None and te is not None and dt in td.index and dt in te.index:
                td_val = float(td[dt]) if pd.notna(td[dt]) else 0
                te_val = float(te[dt]) if pd.notna(te[dt]) else 1
                if te_val > 0:
                    entry["de_ratio"] = round(td_val / te_val, 2)
            balance_data.append(entry)
        result.balance_trend = balance_data[-8:]

    # 现金流趋势
    if qc is not None and not qc.empty:
        cf_data = []
        ocf = _get_row(qc, ["Operating Cash Flow", "Total Cash From Operating Activities"])
        ni_row = _get_row(qf, ["Net Income", "Net Income Common Stockholders"]) if qf is not None else None
        fcf_row = _get_row(qc, ["Free Cash Flow"])

        if ocf is not None:
            for dt in ocf.dropna().sort_index().index:
                entry = {"quarter": f"{dt.year}Q{(dt.month - 1) // 3 + 1}"}
                ocf_val = float(ocf[dt])
                entry["ocf"] = round(ocf_val)
                if ni_row is not None and dt in ni_row.index and pd.notna(ni_row[dt]):
                    ni_val = float(ni_row[dt])
                    entry["ni"] = round(ni_val)
                    entry["ocf_ni_ratio"] = round(ocf_val / ni_val, 2) if ni_val != 0 else None
                if fcf_row is not None and dt in fcf_row.index and pd.notna(fcf_row[dt]):
                    entry["fcf"] = round(float(fcf_row[dt]))
                cf_data.append(entry)
            result.cashflow_trend = cf_data[-8:]

    # 综合评级
    score = 0
    if roe_val and roe_val > 0.15:
        score += 2
    if nm and nm > 0.1:
        score += 1
    cr = info.get("currentRatio")
    if cr and cr > 1.5:
        score += 1
    de = info.get("debtToEquity")
    if de and de < 100:
        score += 1

    result.health_rating = "A" if score >= 4 else ("B" if score >= 3 else ("C" if score >= 2 else "D"))

    return result


def _judge_valuation(metric: str, val: float, sector: str = "") -> str:
    """估值判定（板块感知阈值，与综合报告统一）。"""
    from .constants import get_valuation_thresholds
    t = get_valuation_thresholds(sector)
    metric_map = {"P/E": "pe", "PEG": "peg", "P/S": "ps", "P/B": "pb", "EV/EBITDA": "ev_ebitda"}
    key = metric_map.get(metric)
    if key and key in t:
        low, high = t[key]
    else:
        low, high = (10, 20)
    if val < low:
        return "便宜"
    if val > high:
        return "偏高"
    return "合理"


# ============================================================================
# 5. 同行对比深度分析
# ============================================================================

def _analyze_peers_deep(data: StockData, signal, verbose: bool = False) -> PeersDeep:
    result = PeersDeep()
    result.target_ticker = data.ticker
    info = data.info
    sector = info.get("sector", "")
    industry = info.get("industry", "")

    # 选取同行
    peer_tickers = _select_peers(data.ticker, sector, industry, market_cap=info.get("marketCap"))
    if not peer_tickers:
        return result

    # 获取同行数据
    all_data = [{"ticker": data.ticker, "info": info, "is_target": True}]
    for pt in peer_tickers:
        try:
            pi = yf.Ticker(pt).info
            if pi and "regularMarketPrice" in pi:
                all_data.append({"ticker": pt, "info": pi, "is_target": False})
                if verbose:
                    print(f"  Fetched peer: {pt}", file=sys.stderr)
        except Exception:
            continue

    if len(all_data) < 2:
        return result

    # 基本信息
    result.peers = []
    for d in all_data:
        if not d["is_target"]:
            result.peers.append({
                "ticker": d["ticker"],
                "name": d["info"].get("longName") or d["info"].get("shortName") or d["ticker"],
                "market_cap": d["info"].get("marketCap"),
                "sector": d["info"].get("sector", ""),
            })

    # 估值矩阵
    val_matrix = []
    for d in all_data:
        i = d["info"]
        val_matrix.append({
            "company": d["ticker"],
            "pe": _round_or_none(i.get("trailingPE")),
            "ps": _round_or_none(i.get("priceToSalesTrailing12Months")),
            "pb": _round_or_none(i.get("priceToBook")),
            "ev_ebitda": _round_or_none(i.get("enterpriseToEbitda")),
            "peg": _round_or_none(i.get("pegRatio")),
        })
    result.valuation_matrix = val_matrix

    # 盈利能力矩阵
    prof_matrix = []
    for d in all_data:
        i = d["info"]
        prof_matrix.append({
            "company": d["ticker"],
            "gross_margin": _pct_or_none(i.get("grossMargins")),
            "net_margin": _pct_or_none(i.get("profitMargins")),
            "roe": _pct_or_none(i.get("returnOnEquity")),
            "roa": _pct_or_none(i.get("returnOnAssets")),
        })
    result.profitability_matrix = prof_matrix

    # 增长矩阵
    growth_matrix = []
    for d in all_data:
        i = d["info"]
        growth_matrix.append({
            "company": d["ticker"],
            "rev_growth": _pct_or_none(i.get("revenueGrowth")),
            "eps_growth": _pct_or_none(i.get("earningsGrowth")),
            "fwd_growth": _pct_or_none(i.get("earningsQuarterlyGrowth")),
        })
    result.growth_matrix = growth_matrix

    # 财务健康矩阵
    health_matrix = []
    for d in all_data:
        i = d["info"]
        # target 用 _get_best_fcf 获取更准确的 FCF，同行用 info 字段
        fcf = _get_best_fcf(data, i)[0] if d["is_target"] else i.get("freeCashflow")
        health_matrix.append({
            "company": d["ticker"],
            "current_ratio": _round_or_none(i.get("currentRatio")),
            "de_ratio": _round_or_none(i.get("debtToEquity"), div=100),
            "fcf": fcf,
        })
    result.health_matrix = health_matrix

    # 排名计算
    rankings = []
    target = data.ticker
    peer_only = [d for d in all_data if not d["is_target"]]

    for dim, key, higher_better in [
        ("估值", "trailingPE", False),
        ("盈利能力", "profitMargins", True),
        ("增长速度", "revenueGrowth", True),
    ]:
        target_val = info.get(key)
        peer_vals = [d["info"].get(key) for d in peer_only if d["info"].get(key) is not None]
        if target_val is not None and peer_vals:
            avg = sum(peer_vals) / len(peer_vals)
            if higher_better:
                vs = "高于" if target_val > avg else ("低于" if target_val < avg else "持平")
            else:
                vs = "低于" if target_val < avg else ("高于" if target_val > avg else "持平")

            all_vals = sorted([target_val] + peer_vals, reverse=higher_better)
            rank = all_vals.index(target_val) + 1
            rankings.append({
                "dimension": dim,
                "vs_peers": vs,
                "rank": f"#{rank}/{len(all_vals)}",
                "assessment": "领先" if rank <= 2 else ("中游" if rank <= 3 else "落后"),
            })
    result.rankings = rankings

    # 综合
    if rankings:
        lead_count = sum(1 for r in rankings if r["assessment"] == "领先")
        if lead_count >= 2:
            result.competitive_position = "领先"
        elif lead_count >= 1:
            result.competitive_position = "中上"
        else:
            result.competitive_position = "中游"

    # 优劣势（扩展检测维度）
    strengths = []
    weaknesses = []
    gm = info.get("grossMargins")
    if gm and gm > 0.4:
        strengths.append(f"高毛利率 {gm*100:.1f}%")
    elif gm and gm < 0.2:
        weaknesses.append(f"低毛利率 {gm*100:.1f}%")
    rg = info.get("revenueGrowth")
    if rg and rg > 0.15:
        strengths.append(f"强劲营收增长 {rg*100:.1f}%")
    elif rg is not None and rg < 0:
        weaknesses.append(f"营收下滑 {rg*100:.1f}%")
    pe = info.get("trailingPE")
    if pe and pe > 40:
        weaknesses.append(f"估值偏高 P/E {pe:.1f}x")
    de = info.get("debtToEquity")
    if de and de > 150:
        weaknesses.append(f"杠杆较高 D/E {de/100:.1f}x")
    cr = info.get("currentRatio")
    if cr and cr < 1.0:
        weaknesses.append(f"流动性偏紧 流动比率 {cr:.2f}")
    elif cr and cr > 2.0:
        strengths.append(f"流动性充裕 流动比率 {cr:.2f}")
    nm = info.get("profitMargins")
    if nm and nm > 0.2:
        strengths.append(f"高净利率 {nm*100:.1f}%")
    elif nm is not None and nm < 0:
        weaknesses.append(f"净利润为负 {nm*100:.1f}%")
    fcf = info.get("freeCashflow")
    if fcf and fcf < 0:
        weaknesses.append("自由现金流为负")
    roe = info.get("returnOnEquity")
    if roe and roe > 0.25:
        strengths.append(f"高 ROE {roe*100:.1f}%")
    elif roe is not None and roe < 0:
        weaknesses.append(f"ROE 为负 {roe*100:.1f}%")

    result.strengths = strengths[:3] if strengths else ["数据不足"]
    result.weaknesses = weaknesses[:3] if weaknesses else ["无明显劣势"]

    return result


def _select_peers(ticker: str, sector: str, industry: str, market_cap: float | None = None) -> list[str]:
    """选取同行（委托 sentiment 模块，带市值过滤）。"""
    from .sentiment import _select_peers as _sp
    return _sp(ticker, sector, industry, market_cap=market_cap)[:5]


def _round_or_none(val, digits: int = 2, div: float = 1) -> float | None:
    if val is None:
        return None
    return round(val / div, digits)


def _pct_or_none(val) -> float | None:
    if val is None:
        return None
    return round(val * 100, 1)


# ============================================================================
# 6. 股息深度分析
# ============================================================================

def _analyze_dividends_deep(data: StockData, signal, verbose: bool = False) -> DividendsDeep:
    result = DividendsDeep()
    info = data.info

    result.current_price = info.get("regularMarketPrice") or info.get("currentPrice")
    result.annual_dividend = info.get("dividendRate")

    # 股息收益率：自行计算优先（yfinance 的 dividendYield 返回值不稳定）
    if result.annual_dividend and result.current_price and result.current_price > 0:
        result.dividend_yield = round(result.annual_dividend / result.current_price * 100, 2)
    else:
        div_yield = info.get("dividendYield")
        if div_yield:
            # yfinance 返回小数（0.0038 = 0.38%），若 >1 说明已是百分比形式
            result.dividend_yield = round(div_yield, 2) if div_yield > 1 else round(div_yield * 100, 2)
        else:
            result.dividend_yield = None

    # 无股息
    if not result.annual_dividend or result.annual_dividend == 0:
        result.income_rating = "NO_DIVIDEND"
        result.summary = f"{data.ticker} 不支付股息。"
        result.safety_score = 0
        return result

    # 派息比率
    trailing_eps = info.get("trailingEps")
    if trailing_eps and trailing_eps > 0:
        result.payout_ratio = round((result.annual_dividend / trailing_eps) * 100, 1)
        if result.payout_ratio < 40:
            result.payout_status = "安全"
        elif result.payout_ratio < 60:
            result.payout_status = "适中"
        elif result.payout_ratio < 80:
            result.payout_status = "偏高"
        else:
            result.payout_status = "危险"

    # FCF 覆盖
    fcf = info.get("freeCashflow")
    shares = info.get("sharesOutstanding")
    if fcf and shares and result.annual_dividend:
        total_div = result.annual_dividend * shares
        if total_div > 0:
            result.fcf_coverage = round(fcf / total_div, 2)
            result.fcf_coverage_status = "安全" if result.fcf_coverage > 2 else ("适中" if result.fcf_coverage > 1 else "危险")

    # 股息历史
    dividends = data.dividends
    if dividends is not None and len(dividends) > 0:
        div_df = dividends.reset_index()
        div_df["Year"] = pd.to_datetime(div_df["Date"]).dt.year
        yearly = div_df.groupby("Year")["Dividends"].sum().sort_index(ascending=False)

        # 逐年历史
        yearly_data = []
        prev_val = None
        for year in yearly.head(6).index:
            val = float(yearly[year])
            yoy = None
            if prev_val and prev_val > 0:
                yoy = round((val - prev_val) / prev_val * 100, 1)
            yearly_data.append({"year": int(year), "amount": round(val, 4), "yoy_growth": yoy})
            prev_val = val
        result.yearly_dividends = yearly_data

        # CAGR
        if len(yearly) >= 6:
            result.cagr_5y = _cagr(float(yearly.iloc[5]), float(yearly.iloc[0]), 5)
        if len(yearly) >= 4:
            result.cagr_3y = _cagr(float(yearly.iloc[3]), float(yearly.iloc[0]), 3)

        # 最近加息
        if len(yearly) >= 2:
            recent = float(yearly.iloc[0])
            prev = float(yearly.iloc[1])
            if prev > 0:
                result.last_raise_pct = round((recent - prev) / prev * 100, 1)

        # 连续加息
        consecutive = 0
        prev_d = None
        for d in yearly.values:
            if prev_d is not None:
                if d >= prev_d:
                    consecutive += 1
                else:
                    break
            prev_d = d
        result.consecutive_years = consecutive
        result.is_aristocrat = consecutive >= 25

        # 派息频率
        idx_tz = dividends.index.tz
        one_year_ago = pd.Timestamp.now(tz=idx_tz) - pd.DateOffset(years=1)
        recent_divs = dividends[dividends.index > one_year_ago]
        count = len(recent_divs)
        if count >= 10:
            result.payment_frequency = "月度"
        elif count >= 3:
            result.payment_frequency = "季度"
        elif count >= 1:
            result.payment_frequency = "年度"

    # 除息日
    ex_date = info.get("exDividendDate")
    if ex_date:
        result.ex_dividend_date = datetime.fromtimestamp(ex_date).strftime("%Y-%m-%d")

    # 安全评分
    score = 50
    factors = []

    if result.payout_ratio:
        if result.payout_ratio < 40:
            score += 20
            factors.append({"factor": "派息比率", "contribution": "+20", "description": f"Low payout ({result.payout_ratio:.0f}%)"})
        elif result.payout_ratio < 60:
            score += 10
            factors.append({"factor": "派息比率", "contribution": "+10", "description": f"Moderate payout ({result.payout_ratio:.0f}%)"})
        elif result.payout_ratio < 80:
            score -= 10
            factors.append({"factor": "派息比率", "contribution": "-10", "description": f"High payout ({result.payout_ratio:.0f}%)"})
        else:
            score -= 20
            factors.append({"factor": "派息比率", "contribution": "-20", "description": f"Unsustainable ({result.payout_ratio:.0f}%)"})

    if result.cagr_5y:
        if result.cagr_5y > 10:
            score += 15
            factors.append({"factor": "股息增长", "contribution": "+15", "description": f"Strong growth ({result.cagr_5y:.1f}% CAGR)"})
        elif result.cagr_5y > 5:
            score += 10
            factors.append({"factor": "股息增长", "contribution": "+10", "description": f"Good growth ({result.cagr_5y:.1f}% CAGR)"})
        elif result.cagr_5y > 0:
            score += 5
            factors.append({"factor": "股息增长", "contribution": "+5", "description": f"Positive growth ({result.cagr_5y:.1f}% CAGR)"})
        else:
            score -= 15
            factors.append({"factor": "股息增长", "contribution": "-15", "description": f"Declining ({result.cagr_5y:.1f}% CAGR)"})

    if result.consecutive_years:
        if result.consecutive_years >= 25:
            score += 15
            factors.append({"factor": "连续加息", "contribution": "+15", "description": f"Dividend Aristocrat ({result.consecutive_years}+ years)"})
        elif result.consecutive_years >= 10:
            score += 10
            factors.append({"factor": "连续加息", "contribution": "+10", "description": f"Long history ({result.consecutive_years} years)"})
        elif result.consecutive_years >= 5:
            score += 5
            factors.append({"factor": "连续加息", "contribution": "+5", "description": f"Consistent ({result.consecutive_years} years)"})

    if result.dividend_yield and result.dividend_yield > 8:
        score -= 10
        factors.append({"factor": "收益率风险", "contribution": "-10", "description": f"Very high yield ({result.dividend_yield:.1f}%)"})

    result.safety_score = max(0, min(100, score))
    result.safety_factors = factors

    # 评级
    if result.safety_score >= 80:
        result.income_rating = "EXCELLENT"
    elif result.safety_score >= 60:
        result.income_rating = "GOOD"
    elif result.safety_score >= 40:
        result.income_rating = "MODERATE"
    else:
        result.income_rating = "POOR"

    # 摘要
    parts = []
    if result.dividend_yield:
        parts.append(f"{result.dividend_yield:.2f}% 收益率")
    if result.payout_ratio:
        parts.append(f"{result.payout_ratio:.0f}% 派息率")
    if result.cagr_5y:
        parts.append(f"{result.cagr_5y:+.1f}% 5 年增长")
    result.summary = f"{'、'.join(parts)}。评级：{result.income_rating}"

    return result
