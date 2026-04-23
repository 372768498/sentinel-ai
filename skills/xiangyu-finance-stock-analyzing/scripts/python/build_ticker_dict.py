#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "pandas>=2.0.0",
#     "lxml>=5.0.0",
# ]
# ///
"""
build_ticker_dict — 从 Wikipedia 自动构建 S&P 500 Ticker 别名字典。

拉取 S&P 500 成分股列表，生成英文别名 + 合并中文名映射，
输出 ticker-aliases.json 供 ticker_resolver 运行时加载。

Usage:
    uv run build_ticker_dict.py
"""

import json
import re
import urllib.request
from io import StringIO
from pathlib import Path

import pandas as pd

# ============================================================================
# 路径
# ============================================================================

_SCRIPT_DIR = Path(__file__).resolve().parent
_SKILL_ROOT = _SCRIPT_DIR.parents[1]  # python/ → scripts/ → skill_root/
_DEFINITIONS_DIR = _SKILL_ROOT / "reference" / "definitions"
_CHINESE_NAMES_FILE = _DEFINITIONS_DIR / "chinese-names.json"
_OUTPUT_FILE = _DEFINITIONS_DIR / "ticker-aliases.json"

# ============================================================================
# 常量
# ============================================================================

WIKIPEDIA_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"

# 公司名后缀，用于生成精简别名
STRIP_SUFFIXES = [
    " incorporated",
    " corporation",
    " enterprises",
    " international",
    " holdings",
    " companies",
    " company",
    " group",
    " corp.",
    " corp",
    " inc.",
    " inc",
    " ltd.",
    " ltd",
    " plc",
    " co.",
    " & co.",
    " & co",
    " llc",
    " lp",
    " n.v.",
    " s.a.",
    " se",
]

# 太短或太常见的词，不作为独立别名
SKIP_SHORT_ALIASES = {
    "the", "us", "new", "one", "old", "all", "fox", "air",
    "bio", "gen", "key", "ice", "las", "nor", "cme",
}


# ============================================================================
# 核心逻辑
# ============================================================================

def fetch_sp500() -> pd.DataFrame:
    """从 Wikipedia 拉取 S&P 500 成分股表格。"""
    req = urllib.request.Request(
        WIKIPEDIA_URL,
        headers={"User-Agent": "Mozilla/5.0 (stock-skill-builder/1.0)"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        html = resp.read().decode("utf-8")
    tables = pd.read_html(StringIO(html))
    # 第一个表格是当前成分股
    df = tables[0]
    # 标准化列名
    df.columns = [c.strip() for c in df.columns]
    return df[["Symbol", "Security"]].copy()


def normalize_symbol(symbol: str) -> str:
    """规范化 ticker（如 BRK.B → BRK-B）。"""
    return symbol.strip().replace(".", "-")


def strip_suffix(name: str) -> str:
    """去掉公司名常见后缀。"""
    result = name
    for suffix in STRIP_SUFFIXES:
        if result.endswith(suffix):
            result = result[: -len(suffix)].rstrip(" ,")
    return result.strip()


def generate_aliases(symbol: str, security: str) -> list[tuple[str, str]]:
    """
    为一个公司生成 (别名, ticker) 列表。

    策略：
    1. 全名小写 → ticker
    2. 去后缀名 → ticker（如果与全名不同）
    3. 首词（≥4 字母）→ ticker（有冲突风险，后续去重）
    """
    ticker = normalize_symbol(symbol)
    full_name = security.strip().lower()
    # 清理括号内容（如 "Alphabet Inc. (Class A)"）
    full_name = re.sub(r"\s*\(.*?\)\s*", " ", full_name).strip()

    aliases: list[tuple[str, str]] = []

    # 1. 全名
    if full_name:
        aliases.append((full_name, ticker))

    # 2. 去后缀
    short_name = strip_suffix(full_name)
    if short_name and short_name != full_name:
        aliases.append((short_name, ticker))

    # 3. 首词（≥4 字母，排除常见词）
    first_word = short_name.split()[0] if short_name else ""
    if (
        len(first_word) >= 4
        and first_word != short_name
        and first_word not in SKIP_SHORT_ALIASES
        and first_word.isalpha()
    ):
        aliases.append((first_word, ticker))

    # 4. ticker 本身小写
    aliases.append((ticker.lower(), ticker))

    return aliases


def load_chinese_names() -> dict[str, str]:
    """加载手动维护的中文名映射。"""
    if _CHINESE_NAMES_FILE.exists():
        with open(_CHINESE_NAMES_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def build_alias_dict() -> dict[str, str]:
    """构建完整的别名字典。"""
    print("正在从 Wikipedia 拉取 S&P 500 成分股列表...")
    df = fetch_sp500()
    print(f"  获取到 {len(df)} 条记录")

    # 生成英文别名
    alias_map: dict[str, str] = {}
    conflicts: dict[str, list[str]] = {}  # 别名 → [ticker1, ticker2, ...]

    for _, row in df.iterrows():
        for alias, ticker in generate_aliases(row["Symbol"], row["Security"]):
            if alias in alias_map and alias_map[alias] != ticker:
                # 冲突：跳过此别名
                conflicts.setdefault(alias, [alias_map[alias]]).append(ticker)
                del alias_map[alias]
            elif alias not in conflicts:
                alias_map[alias] = ticker

    if conflicts:
        print(f"  跳过 {len(conflicts)} 个冲突别名：")
        for alias, tickers in sorted(conflicts.items())[:10]:
            print(f"    「{alias}」 → {tickers}")
        if len(conflicts) > 10:
            print(f"    ...（共 {len(conflicts)} 个）")

    # 合并中文名
    chinese = load_chinese_names()
    for name, ticker in chinese.items():
        key = name.lower()
        alias_map[key] = ticker
    print(f"  合并 {len(chinese)} 条中文名")

    # 统计
    tickers = set(alias_map.values())
    print(f"\n构建完成：{len(alias_map)} 条别名，覆盖 {len(tickers)} 个 ticker")

    return dict(sorted(alias_map.items()))


def main():
    alias_dict = build_alias_dict()

    # 确保输出目录存在
    _OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    with open(_OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(alias_dict, f, ensure_ascii=False, indent=2)
    print(f"\n已写入 {_OUTPUT_FILE}")
    print(f"文件大小：{_OUTPUT_FILE.stat().st_size / 1024:.1f} KB")


if __name__ == "__main__":
    main()
