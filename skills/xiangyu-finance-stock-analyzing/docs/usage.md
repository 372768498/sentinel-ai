# Usage Guide

Stock Analysis v11.0 使用指南。

## Table of Contents

1. [快速分析](#快速分析)
2. [深度分析](#深度分析)
3. [性能提示](#性能提示)
4. [解读报告](#解读报告)

---

## 快速分析

### 综合报告（2-3 秒）

```bash
uv run scripts/python/analyze_stock.py AAPL --fast
```

### 带输出目录

```bash
uv run scripts/python/analyze_stock.py AAPL --fast --output-dir ~/Desktop/
```

### JSON 输出

```bash
uv run scripts/python/analyze_stock.py AAPL --output json | jq '.score_100, .rating'
```

### Verbose 模式

```bash
uv run scripts/python/analyze_stock.py AAPL --verbose
```

---

## 深度分析

每个深度模式输出 2 份报告：综合报告 + 对应领域深度报告。

### 估值深度

```bash
uv run scripts/python/analyze_stock.py AAPL --deep valuation --output-dir ~/Desktop/
```

输出：
- `AAPL-综合报告-2026-02-19.md`
- `AAPL-估值-深度报告-2026-02-19.md`

### 成长性深度

```bash
uv run scripts/python/analyze_stock.py NVDA --deep growth --output-dir ~/Desktop/
```

### 技术面深度

```bash
uv run scripts/python/analyze_stock.py TSLA --deep technical --output-dir ~/Desktop/
```

### 基本面深度

```bash
uv run scripts/python/analyze_stock.py MSFT --deep fundamentals --output-dir ~/Desktop/
```

### 同行对比深度

```bash
uv run scripts/python/analyze_stock.py AAPL --deep peers --output-dir ~/Desktop/
```

### 股息深度

```bash
uv run scripts/python/analyze_stock.py JNJ --deep dividends --output-dir ~/Desktop/
```

---

## 性能提示

| Mode | Time | What's Included |
|------|------|-----------------|
| `--fast` | 2-3s | 综合报告（跳过内幕+新闻） |
| Default | 5-10s | 综合报告（完整） |
| `--deep X` | 8-12s | 综合报告 + 深度报告 |

---

## 解读报告

### 评分体系

| Score | Rating | Meaning |
|:-----:|--------|---------|
| 80-100 | Strong Buy | 强烈买入 |
| 65-79 | Buy | 买入 |
| 50-64 | Hold | 持有 |
| 35-49 | Reduce | 减持 |
| 0-34 | Sell | 卖出 |

### 深度报告特色

| 领域 | 核心价值 |
|------|---------|
| 估值 | DCF 内在价值估算，判断是否被低估 |
| 成长性 | 营收 EPS 增长趋势，判断增长是否可持续 |
| 技术面 | 多指标买卖信号汇总，短期交易参考 |
| 基本面 | 利润率和现金流趋势，长期持有参考 |
| 同行对比 | 竞争位置和估值溢价合理性 |
| 股息 | 派息安全性和增长潜力，收入投资参考 |
