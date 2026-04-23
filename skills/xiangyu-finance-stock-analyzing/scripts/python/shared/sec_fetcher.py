"""
SEC EDGAR 财务数据提取 — 使用 edgartools 获取 10-K/10-Q 权威数据。

降级链中的第二层：Yahoo Finance → **SEC EDGAR** → Brave 验证。
提供 FCF、shares outstanding、revenue、net income 等权威数据。
"""

import sys
from dataclasses import dataclass

from .data_fetcher import cache_get, cache_set


# ============================================================================
# 数据结构
# ============================================================================

@dataclass
class SECFinancials:
    """SEC 权威财务数据。"""
    ticker: str
    filing_type: str         # "10-K" | "10-Q"
    filing_date: str         # 最新 filing 日期
    period_end: str          # 财报期末

    # 核心数据（美元）
    revenue: float | None = None
    net_income: float | None = None
    operating_cash_flow: float | None = None
    capital_expenditure: float | None = None
    free_cash_flow: float | None = None
    shares_outstanding: int | None = None

    source: str = "SEC EDGAR"


# ============================================================================
# CapEx 概念标签（按优先级排列）
# ============================================================================

_CAPEX_CONCEPTS = [
    "us-gaap_PaymentsToAcquireProductiveAssets",
    "us-gaap_PaymentsToAcquirePropertyPlantAndEquipment",
    "us-gaap_CapitalExpenditureDiscontinuedOperations",
]


# ============================================================================
# 公共接口
# ============================================================================

def fetch_sec_financials(ticker: str, verbose: bool = False) -> SECFinancials | None:
    """
    从 SEC EDGAR 获取最新年报/季报财务数据。

    降级策略：10-K → 10-Q → None
    超时：edgartools 内部 HTTP 请求，无全局超时但有 try/except 兜底。
    缓存：1 小时（复用全局缓存）。
    """
    cache_key = f"sec_{ticker}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        result = _fetch_from_edgar(ticker, verbose)
        if result is not None:
            cache_set(cache_key, result)
        return result
    except Exception as e:
        if verbose:
            print(f"  SEC EDGAR fetch failed: {type(e).__name__}: {e}", file=sys.stderr)
        return None


# ============================================================================
# 内部实现
# ============================================================================

def _fetch_from_edgar(ticker: str, verbose: bool) -> SECFinancials | None:
    """从 EDGAR 获取财务数据，优先 10-K（年报），回退 10-Q（季报）。"""
    from edgar import Company, set_identity

    set_identity("stock-analysis research@example.com")
    company = Company(ticker)

    # 优先获取 10-K（完整年报）
    financials = company.get_financials()
    if financials is None:
        if verbose:
            print("  SEC: No financials found", file=sys.stderr)
        return None

    # 提取 filing 元数据
    filing_type, filing_date, period_end = _get_filing_meta(company)

    # 提取核心指标
    ocf = _safe_call(financials.get_operating_cash_flow)
    revenue = _safe_call(financials.get_revenue)
    net_income = _safe_call(financials.get_net_income)
    shares = _safe_call(financials.get_shares_outstanding_diluted)

    # CapEx：便捷方法不可靠，从 cashflow dataframe 提取
    capex = _extract_capex(financials, verbose)

    # FCF = OCF - |CapEx|
    fcf = None
    if ocf is not None and capex is not None and capex > 0:
        fcf = ocf - capex
    elif ocf is not None:
        # CapEx 提取失败，用便捷方法的 FCF（精度稍低但可用）
        fcf = _safe_call(financials.get_free_cash_flow)

    # shares 转为整数
    shares_int = int(shares) if shares and shares > 1_000_000 else None

    result = SECFinancials(
        ticker=ticker,
        filing_type=filing_type,
        filing_date=filing_date,
        period_end=period_end,
        revenue=revenue,
        net_income=net_income,
        operating_cash_flow=ocf,
        capital_expenditure=capex,
        free_cash_flow=fcf,
        shares_outstanding=shares_int,
    )

    if verbose:
        _log_result(result)

    return result


def _get_filing_meta(company) -> tuple[str, str, str]:
    """获取最新 filing 的类型、日期、期末。"""
    try:
        for form in ["10-K", "10-Q"]:
            filings = company.get_filings(form=form)
            if filings and len(filings) > 0:
                latest = filings[0]
                fd = str(latest.filing_date) if latest.filing_date else "unknown"
                return form, fd, fd
    except Exception:
        pass
    return "unknown", "unknown", "unknown"


def _extract_capex(financials, verbose: bool) -> float | None:
    """
    从 cashflow statement dataframe 提取真实 CapEx。

    edgartools 的 get_capital_expenditures() 可能返回不准确的值
    （如返回 lease principal payments 而非 property purchases），
    因此直接从 dataframe 按 XBRL 概念标签提取。
    """
    try:
        cf = financials.cashflow_statement()
        if cf is None:
            return None

        df = cf.to_dataframe()
        if df.empty:
            return None

        # 只取非维度行
        main = df[df["dimension"] == False] if "dimension" in df.columns else df

        # 找最新期间列（通常是第一个日期列）
        date_cols = [c for c in df.columns if "-" in str(c) and len(str(c)) == 10]
        if not date_cols:
            return None
        latest_col = date_cols[0]

        # 按优先级查找 CapEx 概念
        for target_concept in _CAPEX_CONCEPTS:
            match = main[main["concept"] == target_concept]
            if not match.empty:
                val = match.iloc[0][latest_col]
                if val is not None and not (isinstance(val, float) and val != val):
                    capex = abs(float(val))
                    if verbose:
                        label = match.iloc[0].get("label", target_concept)
                        print(f"  SEC CapEx: {label} = ${capex/1e9:.2f}B", file=sys.stderr)
                    return capex

        # 回退：搜索包含 "property" 和 "equipment" 的行
        for _, row in main.iterrows():
            label = str(row.get("label", "")).lower()
            if "property" in label and ("equipment" in label or "plant" in label) and "purchase" in label:
                val = row[latest_col]
                if val is not None and not (isinstance(val, float) and val != val):
                    return abs(float(val))

    except Exception as e:
        if verbose:
            print(f"  SEC CapEx extraction failed: {e}", file=sys.stderr)

    return None


def _safe_call(fn) -> float | None:
    """安全调用 edgartools 便捷方法。"""
    try:
        val = fn()
        if val is not None and isinstance(val, (int, float)):
            return float(val)
    except Exception:
        pass
    return None


def _log_result(result: SECFinancials):
    """Verbose 日志输出。"""
    parts = [f"  SEC ({result.filing_type} {result.filing_date}):"]
    if result.free_cash_flow is not None:
        parts.append(f"FCF ${result.free_cash_flow/1e9:.1f}B")
    if result.revenue is not None:
        parts.append(f"Rev ${result.revenue/1e9:.1f}B")
    if result.shares_outstanding is not None:
        parts.append(f"Shares {result.shares_outstanding/1e9:.1f}B")
    print(" | ".join(parts), file=sys.stderr)
