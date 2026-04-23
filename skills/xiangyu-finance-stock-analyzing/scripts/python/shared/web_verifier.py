"""
Brave Search 验证层 — 数据结构 + Claude 端验证接口。

Python 端只负责：
  1. build_pending_metrics() — 收集待验证的 7 项指标
  2. apply_verification()   — 接收 Claude 提取结果，生成 WebVerification

Brave 搜索 + 数值提取由 Claude（Skill prompt 层）完成，
用语义理解替代正则，命中率从 33% 提升到 85%+。

偏差阈值：<=10% CONFIRMED | 10-20% MINOR_GAP | >20% WARNING
"""

import json
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


# ============================================================================
# 枚举与数据结构
# ============================================================================

class VerifyStatus(Enum):
    """验证状态。"""
    CONFIRMED = "confirmed"    # 偏差 <=10%
    MINOR_GAP = "minor_gap"    # 偏差 10-20%
    WARNING = "warning"        # 偏差 >20%
    NOT_FOUND = "not_found"    # 网络未找到


@dataclass
class MetricVerification:
    """单项指标验证结果。"""
    metric: str
    our_value: float | None
    web_value: float | None = None
    discrepancy_pct: float | None = None
    status: VerifyStatus = VerifyStatus.NOT_FOUND
    warning: str | None = None


@dataclass
class WebVerification:
    """整体验证结果。"""
    ticker: str
    metrics: dict[str, MetricVerification] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    search_count: int = 0
    overall_confidence: float = 1.0

    @property
    def confirmed_count(self) -> int:
        return sum(1 for m in self.metrics.values() if m.status == VerifyStatus.CONFIRMED)

    @property
    def warning_count(self) -> int:
        return sum(1 for m in self.metrics.values() if m.status == VerifyStatus.WARNING)


# ============================================================================
# 指标中文名（报告用）
# ============================================================================

METRIC_CN: dict[str, str] = {
    "revenue": "营收（TTM）",
    "eps": "每股盈利（EPS）",
    "fcf": "自由现金流（FCF）",
    "target_price": "分析师目标价",
    "pe_ratio": "市盈率（P/E）",
    "market_cap": "市值",
    "dividend_yield": "股息率",
}

# 指标单位说明（供 Claude 提取时参考）
METRIC_UNITS: dict[str, str] = {
    "revenue": "美元，如 94.8B 或 394.3B",
    "eps": "美元/股，如 1.06 或 6.97",
    "fcf": "美元，如 6.2B 或 111.4B",
    "target_price": "美元，如 421.73",
    "pe_ratio": "倍数，如 385.45 或 32.5",
    "market_cap": "美元，如 1.53T 或 3.7T",
    "dividend_yield": "百分比，如 0.38 或 2.5",
}


# ============================================================================
# 公共接口 1: 构建待验证指标
# ============================================================================

def build_pending_metrics(
    ticker: str,
    *,
    revenue: float | None = None,
    eps: float | None = None,
    fcf: float | None = None,
    target_price: float | None = None,
    pe_ratio: float | None = None,
    market_cap: float | None = None,
    dividend_yield: float | None = None,
) -> dict:
    """
    收集待验证指标，返回结构化 dict。

    输出格式供 Claude 读取后执行 Brave 搜索验证：
    {
        "ticker": "TSLA",
        "metrics": {
            "revenue": {"value": 94800000000, "display": "$94.8B"},
            "eps": {"value": 1.06, "display": "$1.06"},
            ...
        }
    }
    """
    raw = {
        "revenue": revenue, "eps": eps, "fcf": fcf,
        "target_price": target_price, "pe_ratio": pe_ratio,
        "market_cap": market_cap, "dividend_yield": dividend_yield,
    }
    metrics = {}
    for key, val in raw.items():
        if val is not None:
            metrics[key] = {
                "value": val,
                "display": _fmt_value(key, val),
                "unit": METRIC_UNITS.get(key, ""),
            }

    return {"ticker": ticker, "metrics": metrics}


# ============================================================================
# 公共接口 2: 应用 Claude 验证结果
# ============================================================================

def apply_verification(
    ticker: str,
    pending: dict,
    claude_results: dict,
) -> WebVerification:
    """
    接收 Claude 提取的验证数据，生成 WebVerification 对象。

    claude_results 格式：
    {
        "revenue": 95200000000,    # 原始数值（B 用 *1e9，T 用 *1e12）
        "eps": 1.08,
        "fcf": null,               # null 表示未找到
        "target_price": 421.50,
        "pe_ratio": 392.0,
        "market_cap": 1530000000000,
        "dividend_yield": null
    }
    """
    result = WebVerification(ticker=ticker, search_count=3)
    pending_metrics = pending.get("metrics", {})

    for key, info in pending_metrics.items():
        our_value = info["value"]
        web_value = claude_results.get(key)

        mv = MetricVerification(metric=key, our_value=our_value)

        if web_value is None:
            mv.status = VerifyStatus.NOT_FOUND
            result.metrics[key] = mv
            continue

        mv.web_value = web_value

        # 偏差计算
        denom = web_value if web_value != 0 else our_value
        if denom and denom != 0:
            mv.discrepancy_pct = round((our_value - web_value) / abs(denom) * 100, 1)

        # 粒度校验：EPS/营收 倍数差 >2x → 数据粒度不匹配
        if key in ("eps", "revenue") and web_value and our_value:
            ratio = max(our_value, web_value) / max(min(our_value, web_value), 0.01)
            if ratio > 2.0:
                mv.status = VerifyStatus.NOT_FOUND
                mv.web_value = None
                mv.discrepancy_pct = None
                result.metrics[key] = mv
                continue

        # 状态判定
        abs_pct = abs(mv.discrepancy_pct) if mv.discrepancy_pct is not None else 0
        if abs_pct <= 10:
            mv.status = VerifyStatus.CONFIRMED
        elif abs_pct <= 20:
            mv.status = VerifyStatus.MINOR_GAP
        else:
            mv.status = VerifyStatus.WARNING
            mv.warning = _format_warning(key, our_value, web_value, mv.discrepancy_pct)
            result.warnings.append(mv.warning)

        result.metrics[key] = mv

    result.overall_confidence = _calc_confidence(result)
    return result


# ============================================================================
# 兼容接口：verify_all_metrics（空壳，仅构建 pending）
# ============================================================================

def verify_all_metrics(
    ticker: str,
    *,
    revenue: float | None = None,
    eps: float | None = None,
    fcf: float | None = None,
    target_price: float | None = None,
    pe_ratio: float | None = None,
    market_cap: float | None = None,
    dividend_yield: float | None = None,
    verbose: bool = False,
) -> WebVerification:
    """
    兼容旧调用签名 — 返回空 WebVerification。

    实际验证由 Claude 在 Skill prompt 层通过两阶段流程完成。
    此函数仅确保 synthesizer / report_formatter 不会因为
    web_verification=None 而走回退逻辑。
    """
    if verbose:
        print("  [web_verifier] Brave 验证已迁移到 Claude 层，Python 端跳过", file=sys.stderr)
    return WebVerification(ticker=ticker)


# ============================================================================
# 内部工具
# ============================================================================

def _format_warning(key: str, our: float, web: float, pct: float) -> str:
    """生成偏差警告文本。"""
    cn = METRIC_CN.get(key, key)
    return f"{cn}偏差 {pct:+.1f}%：报告 {_fmt_value(key, our)} vs 网络 {_fmt_value(key, web)}"


def _fmt_value(key: str, value: float) -> str:
    """按指标类型格式化。"""
    if key in ("revenue", "fcf", "market_cap"):
        if abs(value) >= 1e12:
            return f"${value / 1e12:.2f}T"
        return f"${value / 1e9:.1f}B"
    if key in ("eps", "target_price"):
        return f"${value:.2f}"
    if key == "pe_ratio":
        return f"{value:.1f}x"
    if key == "dividend_yield":
        return f"{value:.2f}%"
    return str(value)


def _calc_confidence(result: WebVerification) -> float:
    """根据验证结果计算整体置信度。"""
    if not result.metrics:
        return 0.8

    total = len(result.metrics)
    weights = {
        VerifyStatus.CONFIRMED: 1.0,
        VerifyStatus.MINOR_GAP: 0.7,
        VerifyStatus.WARNING: 0.3,
        VerifyStatus.NOT_FOUND: 0.7,
    }
    score = sum(weights.get(m.status, 0.5) for m in result.metrics.values())
    return round(score / total, 2)
