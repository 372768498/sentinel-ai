---
name: xiangyu-finance-stock-analyzing
description: |
  美股分析工具 v12，单股分析 + 深度报告体系。10 维度综合评分（百分制 + 5 级评级）、
  6 个深度分析领域（估值/成长性/技术面/基本面/同行对比/股息）、新手友好中文报告。
  当用户说「股票分析」「分析股票」「stock」「美股」「股息」时触发。
---

# 股票分析工具 v12

单股分析 + 深度报告体系。综合报告（10 维度评分） + 深度报告（6 领域可选）。

---

## 触发条件

| 关键词 | 动作 |
|--------|------|
| 「股票分析」「分析股票」「stock AAPL」 | 引导式分析 |
| 「股息」「dividend」 | 引导式分析（推荐股息深度） |

---

## 引导流程

### 开场

Claude 输出开场白（不含版本号）：

```
翔宇股票分析系统

支持 7 种分析模式：
0. 快速分析 — 10 维度综合评分
1. 估值深度 — DCF 内在价值、历史估值、行业对比
2. 成长性深度 — 营收/EPS 趋势、PEG、增长质量
3. 技术面深度 — 多时间框架、支撑阻力、买卖信号
4. 基本面深度 — 利润率趋势、杜邦分解、现金流
5. 同行对比深度 — 估值/盈利/增长矩阵、竞争排名
6. 股息深度 — 安全评分、派息覆盖、增长 CAGR
```

### 第 1 轮：确认标的

```
AskUserQuestion:
  question: "请输入股票代码或公司名称？"
  header: "股票"
  options:
    - label: "AAPL（苹果）"
      description: "消费电子与服务龙头"
    - label: "NVDA（英伟达）"
      description: "AI 芯片领导者"
    - label: "TSLA（特斯拉）"
      description: "电动汽车龙头"
    - label: "MSFT（微软）"
      description: "云计算与 AI 平台"
  multiSelect: false
```

Claude 侧逻辑：
- 输入公司名 → 代码自动解析（「特斯拉」→ TSLA）
- 输入 ticker 代码 → 自动验证有效性
- 输入拼写不精确 → Yahoo Finance 搜索匹配

### 第 2 轮：选择分析模式

```
AskUserQuestion:
  question: "选择分析模式（或输入编号 0-6）？"
  header: "模式"
  options:
    - label: "0 快速分析（推荐）"
      description: "10 维度综合评分，2-3 秒出结果"
    - label: "1 估值深度"
      description: "DCF 内在价值、历史估值范围、行业对比"
    - label: "3 技术面深度"
      description: "多时间框架趋势、支撑阻力、买卖信号汇总"
    - label: "6 股息深度"
      description: "收益率、安全评分、增长 CAGR、连续加息年数"
  multiSelect: false
```

编号映射（选选项或 Other 输入数字均可）：
- 0 / 快速分析 → `--fast`
- 1 / 估值 → `--deep valuation`
- 2 / 成长性 → `--deep growth`
- 3 / 技术面 → `--deep technical`
- 4 / 基本面 → `--deep fundamentals`
- 5 / 同行对比 → `--deep peers`
- 6 / 股息 → `--deep dividends`

### 运行目录

报告自动保存到 `{skill_dir}/runs/{keyword}-{YYYYMMDD-HHMMSS}/output/`。

keyword 规则：ticker 小写（如 `tsla`）

目录结构：
```
runs/
└── tsla-20260219-201900/
    └── output/
        ├── TSLA-综合报告-2026-02-19.md
        └── TSLA-估值-深度报告-2026-02-19.md    # 仅深度模式
```

### 参数组装

工作目录：`{skill_dir}/scripts/python/`（所有命令必须在此目录下执行）

```bash
cd {skill_dir}/scripts/python
```

| 用户选择 | CLI 命令 |
|----------|---------|
| 快速分析 | `uv run analyze_stock.py TSLA --fast --output-dir {run}/output/` |
| 估值深度 | `uv run analyze_stock.py TSLA --deep valuation --output-dir {run}/output/` |
| 成长性深度 | `uv run analyze_stock.py TSLA --deep growth --output-dir {run}/output/` |
| 技术面深度 | `uv run analyze_stock.py TSLA --deep technical --output-dir {run}/output/` |
| 基本面深度 | `uv run analyze_stock.py TSLA --deep fundamentals --output-dir {run}/output/` |
| 同行对比深度 | `uv run analyze_stock.py TSLA --deep peers --output-dir {run}/output/` |
| 股息深度 | `uv run analyze_stock.py TSLA --deep dividends --output-dir {run}/output/` |

### Brave 验证（两阶段流程）

Python 脚本执行后，Claude 自行完成数据交叉验证。**严格按以下步骤执行**：

**阶段 1：脚本执行**

脚本 stderr 末尾输出 `<!-- VERIFY_REQUEST: {...} -->`，包含 7 项待验证指标及报告值。
Claude 解析此 JSON 获取 ticker 和各指标的 `display` 值。

**阶段 2：Claude 搜索验证**

1. 用 `brave_web_search` 串行搜索 3 次（间隔 ≥2 秒）：
   - Q1: `{TICKER} stock TTM revenue annual EPS 2024 2025`
   - Q2: `{TICKER} stock PE ratio market cap free cash flow`
   - Q3: `{TICKER} stock analyst price target consensus dividend yield`
2. 阅读搜索结果，提取 7 项指标数值（营收/EPS/FCF/目标价/P-E/市值/股息率）
3. 将提取结果写入 JSON 文件 `{run}/output/verification.json`，格式：
   ```json
   {
     "revenue": 94800000000,
     "eps": 1.06,
     "fcf": 6200000000,
     "target_price": 421.73,
     "pe_ratio": 392.0,
     "market_cap": 1530000000000,
     "dividend_yield": null
   }
   ```
   - 金额单位：原始数值（B 乘 1e9，T 乘 1e12）
   - 未找到的指标填 `null`
4. 重新执行脚本，追加 `--apply-verification {run}/output/verification.json`

**阶段 2 命令示例**：
```bash
cd {skill_dir}/scripts/python
uv run analyze_stock.py TSLA --deep valuation --output-dir {run}/output/ --apply-verification {run}/output/verification.json
```

> 阶段 2 会覆盖阶段 1 的综合报告文件，深度报告不受影响（无需重复生成）。
> 最终报告的「数据验证状态」章节将包含完整的交叉验证表格。

---

## 股票分析（10 维度）

| 维度 | 权重 | 数据源 | 说明 |
|------|:---:|--------|------|
| 盈利惊喜 | 15% | Yahoo Finance | EPS 超预期/不及预期 |
| 基本面 | 20% | Yahoo Finance | 12 指标估值（板块感知阈值） |
| 分析师情绪 | 12% | Yahoo Finance | 评级、目标价 |
| 历史表现 | 5% | Yahoo Finance | 过往财报反应 |
| 市场环境 | 8% | Yahoo Finance | VIX、SPY/QQQ 趋势、安全港 |
| 板块强度 | 8% | Yahoo Finance | 相对强度 |
| 技术分析 | 12% | Yahoo Finance | MA/MACD/BB/RSI/成交量 |
| 情绪 | 10% | CNN/SEC/Yahoo | 恐惧贪婪、空头、内幕、Put/Call |
| 同行对比 | 10% | Yahoo Finance | 相对估值（含 P/S、P/B 评分） |
| 财报时间 | 修正器 | Yahoo Finance | 距财报 < 14 天 → BUY → HOLD |

> 权重合计精确 100%（15+20+12+5+8+8+12+10+10=100）

### 板块感知阈值

估值指标（P/E、P/S、P/B、EV/EBITDA）使用板块感知阈值，基于 Damodaran 行业数据：

| 板块组 | 适用板块 | P/E 阈值 | P/S 阈值 |
|--------|---------|---------|---------|
| 成长型 | Technology, Healthcare, Communication Services | 25-45x | 5-15x |
| 价值型 | Utilities, Energy, Financial Services | 12-20x | 1-3x |
| 工业型 | Industrials, Basic Materials | 15-25x | 1.5-5x |

---

## 深度报告（6 领域）

| 领域 | --deep 参数 | 核心内容 |
|------|-----------|---------|
| 估值 | valuation | DCF 三情景、历史 P/E 范围、行业相对估值 |
| 成长性 | growth | 营收 CAGR、EPS 趋势、PEG、增长质量 |
| 技术面 | technical | 多时间框架、MACD 背离、买卖信号汇总 |
| 基本面 | fundamentals | 利润率趋势、杜邦分解、现金流质量 |
| 同行对比 | peers | 估值/盈利/增长矩阵、竞争排名 |
| 股息 | dividends | 安全评分、派息覆盖、增长 CAGR |

---

## 评分体系

| 评分范围 | 评级 | 含义 |
|:--------:|------|------|
| 80-100 | Strong Buy | 强烈买入 |
| 65-79 | Buy | 买入 |
| 50-64 | Hold | 持有 |
| 35-49 | Reduce | 减持 |
| 0-34 | Sell | 卖出 |

---

## 风险检测

| 风险类型 | 检测条件 | 影响 |
|----------|---------|------|
| 财报前期 | 距财报 < 14 天 | BUY → HOLD |
| 暴涨后期 | 5 天涨幅 > 15% | 降低置信度 |
| 超买 | RSI > 70 + 接近 52 周高点 | 警告提示 |
| 避险情绪 | GLD/TLT/UUP 同涨 | 整体降级 |
| 地缘政治 | 台湾/中国/俄罗斯关键词 | 板块惩罚 |

---

## 限制说明

| 限制 | 说明 |
|------|------|
| 数据延迟 | Yahoo Finance 延迟 15-20 分钟 |
| 地区限制 | 仅支持美股 |
| 空头数据 | FINRA 延迟约 2 周 |

---

## 免责声明

**非投资建议**。仅供信息参考。投资决策前请咨询持牌财务顾问。

---

## 参考资料

| 文件 | 路径 | 用途 |
|------|------|------|
| 架构文档 | `docs/architecture.md` | 系统设计 |
| 使用指南 | `docs/usage.md` | 实用示例 |
| 版本历史 | `docs/changelog.md` | 更新记录 |
