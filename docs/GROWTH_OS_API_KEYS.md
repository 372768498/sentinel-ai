# Growth OS API Key Checklist / API Key 清单

这是 Sentinel AI 第一阶段自动化获客需要补齐的 Key 清单。
不要提交真实值；本地放 `.env.local`，线上放 Railway / Vercel / 平台 Secret Store。

## P0 - 第一条稳定闭环必须有

| 模块 | Env vars | 用途 |
| --- | --- | --- |
| 产品链接 | `GROWTH_OS_PUBLIC_URL` | 给每条社媒草稿生成 UTM CTA 链接。 |
| 内容生成 | `ANTHROPIC_API_KEY` | 生成 X / Reddit / Shorts / TikTok 草稿包。 |
| 数据库 | `DATABASE_URL` | 归因 VisitEvent / EmailLead / SubscriptionStatus，用于复盘。 |
| 飞书应用 | `FEISHU_APP_ID`, `FEISHU_APP_SECRET` | 访问飞书多维表格和审核群。 |
| 飞书审核 | `FEISHU_REVIEW_CHAT_ID`, `FEISHU_BITABLE_APP_TOKEN`, `FEISHU_CONTENT_QUEUE_TABLE_ID`, `FEISHU_PERFORMANCE_TABLE_ID` | 内容队列、审核流转、KPI 摘要。 |
| X 官方读取 | `X_BEARER_TOKEN` | 官方 X search/signal adapter。没有也能跑，会自动走 SERP/FMP fallback。 |
| X 发布 | `X_API_KEY`, `X_API_SECRET`, `X_ACCESS_TOKEN`, `X_ACCESS_TOKEN_SECRET` | 审核通过后的 X 发帖。只有 `MARKETING_PUBLISH_DRY_RUN=false` 且 `X_DRY_RUN=false` 才会 live。 |
| 市场数据 | `FMP_API_KEY`, `SEC_USER_AGENT` | 行情异动 + SEC 证据兜底；官方 X 不可用时尤其重要。 |
| X SERP fallback | `DATAFORSEO_LOGIN`, `DATAFORSEO_PASSWORD` | 官方 X 受限时，用 Google/X SERP 找社媒讨论。 |
| Web enrichment fallback | `TAVILY_API_KEY` | DataForSEO 不可用时的二级搜索/富化路径。 |
| YouTube 研究 | `YOUTUBE_DATA_API_KEY` | Shorts/topic benchmark discovery。 |

## P1 - 第一条闭环跑通后再补

| 模块 | Env vars | 用途 |
| --- | --- | --- |
| Telegram channel | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHANNEL_ID_PUBLIC`, `TELEGRAM_CHANNEL_HANDLE` | Public distribution channel and smoke tests. |
| Resend | `RESEND_API_KEY`, `RESEND_FROM_EMAIL` | Email daily radar and magic links. |
| SEC provider | `SEC_API_KEY` | Optional hosted SEC API path. |
| Media assets | `PEXELS_API_KEY` | Future Shorts/TikTok media asset sourcing. |
| Crawling/rerank | `JINA_API_KEY`, `FIRECRAWL_API_KEY`, `APIFY_API_TOKEN` | Future enrichment/scraping fallbacks. |
| TikTok intelligence | `TIKHUB_API_KEY` | Future TikTok trend adapter. |

## 第一阶段运行开关

发布保持 dry-run，直到飞书审核、内容质量、归因都端到端验证通过。

```dotenv
MARKETING_DAILY_DRAFT_ENABLED=true
MARKETING_ALWAYS_ON_DRAFT_ENABLED=true
MARKETING_ALWAYS_ON_DRAFT_INTERVAL_MINUTES=180
MARKETING_ACQUISITION_OPERATOR_ENABLED=true
MARKETING_ACQUISITION_OPERATOR_HOUR_ET=9
MARKETING_QUEUE_POLL_ENABLED=true
MARKETING_QUEUE_POLL_INTERVAL_SECONDS=300
MARKETING_DAILY_DIGEST_ENABLED=true

MARKETING_PUBLISH_DRY_RUN=true
X_DRY_RUN=true
```

X live cutover 前，先确认飞书里一条“已通过”内容能 dry-run 成功变成“已发布”。确认后再翻：

```dotenv
MARKETING_PUBLISH_DRY_RUN=false
X_DRY_RUN=false
```

## 本地验证

填好 `.env.local` 后先跑预检：

```powershell
worker/.venv/Scripts/python.exe scripts/marketing_deploy_preflight.py
```

然后跑一次本地不写飞书的 Operator：

```powershell
worker/.venv/Scripts/python.exe scripts/run_acquisition_operator.py --local-only --no-kpi --content-date local-check
```

确认内容质量后，跑真实飞书提交：

```powershell
worker/.venv/Scripts/python.exe scripts/run_acquisition_operator.py --content-date 202605170930
```

预检报告只显示 `present` / `missing`，不会打印 secret values。
