"""
数据获取：Yahoo Finance 数据拉取、缓存、StockData 容器。
"""

import sys
import time
from dataclasses import dataclass, field

import pandas as pd
import yfinance as yf


# ============================================================================
# 缓存
# ============================================================================

_CACHE: dict[str, tuple] = {}
_CACHE_TTL = 3600  # 1 小时


def cache_get(key: str):
    """获取缓存（TTL 内有效）。"""
    if key in _CACHE:
        value, ts = _CACHE[key]
        if time.time() - ts < _CACHE_TTL:
            return value
    return None


def cache_set(key: str, value):
    """写入缓存。"""
    _CACHE[key] = (value, time.time())


# ============================================================================
# 数据容器
# ============================================================================

@dataclass
class StockData:
    """Yahoo Finance 原始数据容器。"""
    ticker: str
    ticker_symbol: str          # 用于二次获取（期权链等）
    info: dict
    earnings_history: pd.DataFrame | None
    analyst_info: dict | None
    price_history: pd.DataFrame | None

    # 深度分析扩展字段（按需获取）
    quarterly_financials: pd.DataFrame | None = None
    quarterly_balance_sheet: pd.DataFrame | None = None
    quarterly_cashflow: pd.DataFrame | None = None
    dividends: pd.Series | None = None
    price_history_2y: pd.DataFrame | None = None

    # 验证数据（始终获取）
    sec_data: object = None          # SECFinancials | None
    web_verification: object = None  # WebVerification | None
    pending_verification: dict | None = None  # Claude 端验证用的待验证指标


# ============================================================================
# 数据获取
# ============================================================================

def fetch_stock_data(ticker: str, verbose: bool = False) -> StockData | None:
    """从 Yahoo Finance 获取数据，含重试。"""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            if verbose:
                print(f"Fetching data for {ticker}... (attempt {attempt + 1}/{max_retries})", file=sys.stderr)

            stock = yf.Ticker(ticker)
            info = stock.info

            if not info or "regularMarketPrice" not in info:
                return None

            try:
                earnings_history = stock.earnings_dates
            except Exception:
                earnings_history = None

            try:
                analyst_info = {
                    "recommendations": stock.recommendations,
                    "analyst_price_targets": stock.analyst_price_targets,
                }
            except Exception:
                analyst_info = None

            try:
                price_history = stock.history(period="1y")
            except Exception:
                price_history = None

            return StockData(
                ticker=ticker,
                ticker_symbol=ticker,
                info=info,
                earnings_history=earnings_history,
                analyst_info=analyst_info,
                price_history=price_history,
            )

        except Exception as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                if verbose:
                    print(f"Error fetching {ticker}: {e}. Retrying in {wait_time}s...", file=sys.stderr)
                time.sleep(wait_time)
            else:
                if verbose:
                    print(f"Failed to fetch {ticker} after {max_retries} attempts", file=sys.stderr)
                return None

    return None


def fetch_deep_data(data: StockData, verbose: bool = False) -> StockData:
    """按需获取深度分析所需的额外数据，就地填充 StockData。"""
    stock = yf.Ticker(data.ticker_symbol)

    # 季度财报
    if data.quarterly_financials is None:
        try:
            data.quarterly_financials = stock.quarterly_financials
            if verbose:
                print("  Fetched quarterly financials", file=sys.stderr)
        except Exception:
            data.quarterly_financials = None

    # 季度资产负债表
    if data.quarterly_balance_sheet is None:
        try:
            data.quarterly_balance_sheet = stock.quarterly_balance_sheet
            if verbose:
                print("  Fetched quarterly balance sheet", file=sys.stderr)
        except Exception:
            data.quarterly_balance_sheet = None

    # 季度现金流
    if data.quarterly_cashflow is None:
        try:
            data.quarterly_cashflow = stock.quarterly_cashflow
            if verbose:
                print("  Fetched quarterly cashflow", file=sys.stderr)
        except Exception:
            data.quarterly_cashflow = None

    # 股息历史
    if data.dividends is None:
        try:
            data.dividends = stock.dividends
            if verbose:
                print("  Fetched dividend history", file=sys.stderr)
        except Exception:
            data.dividends = None

    # 2 年价格历史（技术深度需要）
    if data.price_history_2y is None:
        try:
            data.price_history_2y = stock.history(period="2y")
            if verbose:
                print("  Fetched 2-year price history", file=sys.stderr)
        except Exception:
            data.price_history_2y = None

    return data


# ============================================================================
# 验证数据获取（EDGAR + Brave）
# ============================================================================

def fetch_verified_data(data: StockData, verbose: bool = False) -> StockData:
    """获取 SEC EDGAR 权威数据 + Brave 全量验证（始终执行）。"""
    if verbose:
        print("Fetching verified data (SEC + Brave)...", file=sys.stderr)

    # 1. SEC EDGAR 数据
    if data.sec_data is None:
        try:
            from .sec_fetcher import fetch_sec_financials
            data.sec_data = fetch_sec_financials(data.ticker, verbose=verbose)
        except Exception as e:
            if verbose:
                print(f"  SEC fetch error: {e}", file=sys.stderr)

    # 2. 构建待验证指标（供 Claude 层执行 Brave 搜索）
    if data.pending_verification is None:
        try:
            from .web_verifier import build_pending_metrics
            data.pending_verification = build_pending_metrics(
                data.ticker,
                revenue=data.info.get("totalRevenue"),
                eps=data.info.get("trailingEps"),
                fcf=_get_yf_fcf(data),
                target_price=data.info.get("targetMeanPrice"),
                pe_ratio=data.info.get("trailingPE"),
                market_cap=data.info.get("marketCap"),
                dividend_yield=_get_dividend_yield(data),
            )
            if verbose:
                n = len(data.pending_verification.get("metrics", {}))
                print(f"  Built {n} pending metrics for Claude verification", file=sys.stderr)
        except Exception as e:
            if verbose:
                print(f"  Pending metrics build error: {e}", file=sys.stderr)

    # 3. 兼容：确保 web_verification 不为 None（空壳，避免下游报错）
    if data.web_verification is None:
        from .web_verifier import WebVerification
        data.web_verification = WebVerification(ticker=data.ticker)

    return data


def _get_yf_fcf(data: StockData) -> float | None:
    """从 yfinance 数据获取 FCF（季度 TTM 或 info 字段）。"""
    qcf = data.quarterly_cashflow
    if qcf is not None and not qcf.empty:
        for label in ["Free Cash Flow", "FreeCashFlow"]:
            if label in qcf.index:
                values = qcf.loc[label].dropna().head(4)
                if len(values) >= 4:
                    return float(values.sum())
    return data.info.get("freeCashflow")


def _get_dividend_yield(data: StockData) -> float | None:
    """从 yfinance 获取股息率（百分比）。Yahoo 返回如 0.38 表示 0.38%。"""
    dy = data.info.get("dividendYield")
    if not dy:
        return None
    # Yahoo 返回的值直接是百分比数字（0.38 = 0.38%）
    return round(dy, 2)
