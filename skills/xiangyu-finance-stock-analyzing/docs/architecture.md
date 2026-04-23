# Technical Architecture

How Stock Analysis v11.0 works under the hood.

## System Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                      Stock Analysis v11.0                        │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │                   CLI Interface                            │  │
│  │                  analyze_stock.py                           │  │
│  │        --fast (综合报告) | --deep X (综合+深度)             │  │
│  └───────────────────────┬────────────────────────────────────┘  │
│                          │                                       │
│  ┌───────────────────────▼────────────────────────────────────┐  │
│  │               shared/ Analysis Engine                      │  │
│  │                                                            │  │
│  │  analyzers.py (7 dimensions)                               │  │
│  │  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐             │  │
│  │  │Earnings│ │Fundmtls│ │Analysts│ │Histrcl │             │  │
│  │  └────┬───┘ └────┬───┘ └────┬───┘ └────┬───┘             │  │
│  │  ┌────┴───┐ ┌────┴───┐ ┌────┴───┐                        │  │
│  │  │Market  │ │ Sector │ │Technl  │                        │  │
│  │  └────┬───┘ └────┬───┘ └────┬───┘                        │  │
│  │       │          │          │                              │  │
│  │  sentiment.py (3 dimensions + risk)                        │  │
│  │  ┌────────┐ ┌────────┐ ┌────────┐                        │  │
│  │  │Sentmnt │ │ Peers  │ │Earning │                        │  │
│  │  │(5async)│ │Compare │ │Timing  │                        │  │
│  │  └────┬───┘ └────┬───┘ └────┬───┘                        │  │
│  │       └──────────┴──────────┘                              │  │
│  │                  │                                         │  │
│  │         synthesizer.py                                     │  │
│  │      [Weighted → 0-100 → 5-Level Rating]                  │  │
│  │                  │                                         │  │
│  │  deep_analyzers.py (6 domains)                             │  │
│  │  ┌─────────┐ ┌────────┐ ┌─────────┐                      │  │
│  │  │Valuation│ │ Growth │ │Technical│                      │  │
│  │  └─────────┘ └────────┘ └─────────┘                      │  │
│  │  ┌──────────┐ ┌──────┐ ┌──────────┐                      │  │
│  │  │Fundmntls │ │Peers │ │Dividends │                      │  │
│  │  └──────────┘ └──────┘ └──────────┘                      │  │
│  │                  │                                         │  │
│  │  deep_report_formatter.py                                  │  │
│  │      [6 Chinese Markdown Templates]                        │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │                  Data Sources                              │  │
│  │  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐             │  │
│  │  │ Yahoo  │ │  CNN   │ │  SEC   │ │ Google │             │  │
│  │  │Finance │ │Fear/Grd│ │ EDGAR  │ │  News  │             │  │
│  │  └────────┘ └────────┘ └────────┘ └────────┘             │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

---

## File Structure

```
xiangyu-finance-stock-analyzing/
├── SKILL.md                                # Skill 定义
├── config/default.json                     # 默认配置
├── reference/definitions/
│   ├── scoring-weights.json                # 评分权重
│   ├── risk-thresholds.json                # 风险阈值
│   └── peer-groups.json                    # 同行对比映射
├── scripts/python/
│   ├── analyze_stock.py                    # CLI 入口 — 单股 + --deep
│   └── shared/                             # 共享模块包
│       ├── __init__.py                     # 公共接口导出
│       ├── constants.py                    # 权重/阈值/映射表
│       ├── data_fetcher.py                 # 数据获取 + 缓存 + fetch_deep_data
│       ├── analyzers.py                    # 7 维度分析
│       ├── sentiment.py                    # 情绪 + 同行 + 时间 + 新闻
│       ├── synthesizer.py                  # 信号合成 + 综合报告
│       ├── report_formatter.py             # 综合报告 Markdown 模板
│       ├── ticker_resolver.py              # Ticker 智能解析
│       ├── deep_analyzers.py               # 6 领域深度分析函数
│       └── deep_report_formatter.py        # 6 领域深度报告模板
└── docs/
    ├── architecture.md                     # 本文件
    ├── usage.md                            # 使用指南
    └── changelog.md                        # 版本历史
```

---

## Core Components

### 1. Data Fetching (`shared/data_fetcher.py`)

**StockData** 容器：
- `info`: Company fundamentals
- `earnings_history`: Past earnings
- `analyst_info`: Ratings and targets
- `price_history`: 1-year OHLCV
- `quarterly_financials`: 季度利润表（深度分析扩展）
- `quarterly_balance_sheet`: 季度资产负债表（深度分析扩展）
- `quarterly_cashflow`: 季度现金流表（深度分析扩展）
- `dividends`: 股息历史（深度分析扩展）
- `price_history_2y`: 2 年价格历史（深度分析扩展）

`fetch_deep_data()` 按需填充上述扩展字段。

### 2. Analyzers (`shared/analyzers.py`)

7 core dimensions (same as v9.0).

### 3. Deep Analyzers (`shared/deep_analyzers.py`)

6 deep analysis domains:

| Domain | Dataclass | Key Feature |
|--------|-----------|-------------|
| `valuation` | `ValuationDeep` | DCF 三情景估值 |
| `growth` | `GrowthDeep` | 营收/EPS CAGR + PEG |
| `technical` | `TechnicalDeep` | MA200 + MACD 背离 + 信号汇总 |
| `fundamentals` | `FundamentalsDeep` | 利润率趋势 + 杜邦分解 |
| `peers` | `PeersDeep` | 完整对比矩阵 + 排名 |
| `dividends` | `DividendsDeep` | 安全评分 + CAGR + 贵族 |

### 4. Deep Report Formatter (`shared/deep_report_formatter.py`)

6 Chinese Markdown templates matching each deep analysis domain.

---

## Performance

| Operation | Time |
|-----------|------|
| yfinance fetch | ~2s |
| Market context | ~1s (cached after) |
| Insider trading | ~3-5s (slowest!) |
| Deep data fetch | ~2-3s (quarterly + 2y history) |
| Deep analysis | ~1s |
| **Fast mode** | **2-3s** |
| **Deep mode** | **8-12s** |

---

## Dependencies

```python
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "yfinance>=0.2.40",
#     "pandas>=2.0.0",
#     "fear-and-greed>=0.4",
#     "edgartools>=2.0.0",
#     "feedparser>=6.0.0",
# ]
# ///
```
