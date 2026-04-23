"""
ticker_resolver — 三层 Ticker 智能解析器。

Layer 1: 本地别名字典（O(1)，覆盖 S&P 500 英文名 + 中文名）
Layer 2: 直接验证（看起来像 ticker → yf.Ticker 检查）
Layer 3: yf.Search 模糊搜索兜底
"""

import json
from pathlib import Path

import yfinance as yf

# ============================================================================
# 本地别名字典（从 ticker-aliases.json 加载，全小写键 → ticker）
# ============================================================================

_SKILL_ROOT = Path(__file__).resolve().parents[3]  # shared/ → python/ → scripts/ → skill_root/
_ALIASES_FILE = _SKILL_ROOT / "reference" / "definitions" / "ticker-aliases.json"


def _load_aliases() -> dict[str, str]:
    """加载别名字典，文件不存在时返回空字典。"""
    if _ALIASES_FILE.exists():
        with open(_ALIASES_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}


ALIAS_MAP: dict[str, str] = _load_aliases()


# ============================================================================
# 公共接口
# ============================================================================

def resolve_ticker(user_input: str) -> tuple[str, str]:
    """
    三层解析：别名字典 -> yf.Ticker 验证 -> yf.Search 模糊搜索。

    Returns:
        (ticker, match_source)  如 ("TSLA", "alias") / ("AAPL", "direct") / ("PLTR", "search")

    Raises:
        ValueError: 无法解析时，附带提示信息
    """
    cleaned = user_input.strip()
    if not cleaned:
        raise ValueError("输入为空，请输入美股代码（如 AAPL）或公司名称")

    # Layer 1: 本地字典（O(1)）
    key = cleaned.lower()
    if key in ALIAS_MAP:
        return ALIAS_MAP[key], "alias"

    # Layer 2: 看起来像 ticker（全字母，1-5 字符）→ 直接验证
    upper = cleaned.upper()
    if upper.replace("-", "").isalpha() and 1 <= len(upper) <= 5:
        if _validate_ticker(upper):
            return upper, "direct"

    # Layer 3: yf.Search 模糊搜索
    candidates = _search_yahoo(cleaned)
    if candidates:
        return candidates[0]["symbol"], "search"

    raise ValueError(
        f"无法识别「{user_input}」，请输入正确的美股代码（如 AAPL）或公司名称"
    )


def resolve_tickers(inputs: list[str]) -> list[tuple[str, str]]:
    """批量解析，返回 [(ticker, source), ...]。"""
    return [resolve_ticker(inp) for inp in inputs]


# ============================================================================
# 内部函数
# ============================================================================

def _validate_ticker(ticker: str) -> bool:
    """通过 yfinance 验证 ticker 是否有效。"""
    try:
        info = yf.Ticker(ticker).info
        return bool(info and info.get("regularMarketPrice"))
    except Exception:
        return False


def _search_yahoo(query: str, max_results: int = 5) -> list[dict]:
    """调用 yf.Search，返回 EQUITY 类型的候选列表。"""
    try:
        results = yf.Search(query, max_results=max_results)
        return [
            q for q in (results.quotes or [])
            if q.get("quoteType") == "EQUITY"
        ]
    except Exception:
        return []
