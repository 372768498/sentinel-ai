# 环境初始化

遇报错时参照本文档配置环境。使用说明见 `guide.md`。

---

## 安装位置

| 级别 | 路径 | 优先级 |
|------|------|--------|
| 项目级 | `.claude/skills/xiangyu-finance-stock-analyzing/` | 中 |
| 用户级 | `~/.claude/skills/xiangyu-finance-stock-analyzing/` | 最低 |

---

## 运行时环境

| 要求 | 值 |
|------|-----|
| 运行时 | Python |
| 版本 | >= 3.10 |
| 包管理 | uv |
| 虚拟环境 | 自动管理（uv inline metadata） |
| 脚本目录 | `scripts/python/` |

---

## 依赖安装

```bash
# 安装 uv（如未安装）
curl -LsSf https://astral.sh/uv/install.sh | sh

# 进入脚本目录
cd ~/.claude/skills/xiangyu-finance-stock-analyzing/scripts/python

# 测试运行（uv 自动解析 inline metadata 安装依赖）
uv run analyze_stock.py AAPL --fast
```

依赖列表（由 `analyze_stock.py` 头部 inline metadata 声明）：

| 包名 | 版本 | 用途 |
|------|------|------|
| yfinance | >= 0.2.40 | Yahoo Finance 数据获取 |
| pandas | >= 2.0.0 | 数据处理 |
| fear-and-greed | >= 0.4 | CNN 恐惧贪婪指数 |
| edgartools | >= 2.0.0 | SEC EDGAR 内幕交易 |
| feedparser | >= 6.0.0 | RSS 新闻解析 |

---

## 凭证配置

**无需凭证**。所有数据源均为免费公开 API：

| 数据源 | 认证方式 | 说明 |
|--------|---------|------|
| Yahoo Finance | 无需 | yfinance 库直连 |
| CNN Fear & Greed | 无需 | 公开 API |
| SEC EDGAR | 无需 | 公开数据 |

---

## 快速检查

按顺序执行，首个失败项即为问题所在：

```bash
# 1. Python 版本检查（需 >= 3.10）
python3 --version

# 2. uv 是否安装
uv --version

# 3. 依赖完整性检查
cd ~/.claude/skills/xiangyu-finance-stock-analyzing/scripts/python
uv run python -c "import yfinance; print('yfinance OK')"

# 4. 网络连通性检查
curl -s -o /dev/null -w "%{http_code}" https://query1.finance.yahoo.com/v8/finance/chart/AAPL
```

---

## 错误排查

| 分类 | 错误现象 | 可能原因 | 修复方法 | 验证方式 |
|------|---------|---------|---------|---------|
| 运行时层 | `Python >= 3.10 required` | Python 版本过低 | `brew install python@3.12` | `python3 --version` |
| 依赖层 | `ModuleNotFoundError: yfinance` | 依赖未安装 | `cd scripts/python && uv run analyze_stock.py AAPL --fast` | uv 自动安装 |
| 依赖层 | `uv: command not found` | uv 未安装 | `curl -LsSf https://astral.sh/uv/install.sh \| sh` | `uv --version` |
| 网络层 | `HTTPError 429` | Yahoo Finance 限流 | 等待 60 秒后重试 | 重新运行命令 |
| 网络层 | `ConnectionError` | 网络不通 | 检查网络连接和代理设置 | `curl https://finance.yahoo.com` |
| 网络层 | `No data found for ticker` | Ticker 无效或退市 | 确认 ticker 在 Yahoo Finance 有效 | 浏览器访问 `finance.yahoo.com/quote/TICKER` |
| 进度层 | `FileNotFoundError: output dir` | 输出目录不存在 | 脚本会自动创建，检查父目录权限 | `ls -la {run_dir}` |
