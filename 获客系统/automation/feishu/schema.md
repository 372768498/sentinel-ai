# 飞书多维表格结构 · Sentinel AI Growth OS

> 目标：让运营侧看到中文字段，worker 代码继续兼容英文旧字段。
>
> 字段中文化脚本：`scripts/feishu/rename_growth_os_bitable_to_chinese.py`

说明：字段名可以通过 OpenAPI 原地中文化；数据表表名在当前飞书 OpenAPI 权限下不能可靠重命名，需要在飞书 UI 手动把 `Campaigns / Content Queue / Performance` 改成 `活动 / 内容队列 / 表现数据`。字段中文化不影响历史数据，`field_id` 不变。

## 总体判断

当前三张表的分工是合理的：

| 表 | 建议中文名 | 职责 | 判断 |
| --- | --- | --- | --- |
| Campaigns | 活动 | 每天/每轮获客运行的容器 | 合理，但第一阶段可以轻量使用 |
| Content Queue | 内容队列 | 每条平台内容的审核、发布和质量控制 | 核心表，结构合理 |
| Performance | 表现数据 | 按 `content_id` 回流 KPI | 核心表，字段已和 KPI 聚合对齐 |

不建议现在增加更多表。第一阶段先把 `content_id -> UTM -> VisitEvent -> EmailLead -> Performance` 跑稳定。

## 表 1：活动 Campaigns

环境变量：`FEISHU_CAMPAIGNS_TABLE_ID`

| 字段名 | 英文兼容名 | 类型 | 用途 |
| --- | --- | --- | --- |
| 活动ID | `campaign_id` | 文本 | `CMP-YYYYMMDD-daily` 或 `CMP-YYYYMMDDHHMM-always-on` |
| 日期 | `date` | 日期时间 | 活动日期 |
| 场次 | `session` | 单选 | Pre-market / Midday / Post-close / Breaking |
| 主股票代码 | `main_ticker` | 文本 | 本轮主 ticker |
| 状态 | `status` | 单选 | Draft / Review / Approved / Published / Rejected |
| 负责人 | `owner` | 文本 | 审核人或操作者 |
| 备注 | `notes` | 文本 | 运行备注 |

## 表 2：内容队列 Content Queue

环境变量：`FEISHU_CONTENT_QUEUE_TABLE_ID`

| 字段名 | 英文兼容名 | 类型 | 用途 |
| --- | --- | --- | --- |
| 内容ID | `content_id` | 文本主键 | `CT-YYYYMMDD-TICKER-platform` |
| 活动ID | `campaign_id` | 文本 | 关联 Campaigns |
| 平台 | `platform` | 单选 | X / Reddit / Telegram / TikTok / YouTube Shorts / YouTube Long / Email |
| 股票代码 | `ticker` | 文本 | NVDA / TSLA 等 |
| 钩子 | `hook` | 文本 | 第一眼内容钩子 |
| 钩子中文 | `hook_zh` | 文本 | 钩子的中文版本，方便中文审核和复用 |
| 正文 | `body` | 文本 | 完整草稿 |
| 正文中文 | `body_zh` | 文本 | 正文的中文版本，方便中文审核和复用 |
| 跳转链接 | `cta_url` | URL | 带 UTM 的落地页 |
| 风险等级 | `risk_level` | 单选 | Low / Medium / High |
| 合规检查 | `redline_result` | 单选 | Pass / Needs Edit / Blocked |
| 违规项 | `redline_hits` | 文本 | 命中的红线词或缺失项 |
| 审核状态 | `review_status` | 单选 | Pending / Approved / Rejected / Published / Failed |
| 审核备注 | `reviewer_comment` | 文本 | 人工审核意见或发布失败原因 |
| 发布时间 | `publish_time` | 日期时间 | 计划或实际发布时间 |
| 已发布链接 | `published_url` | URL | 实际发布 URL 或 dry-run URL |
| 质量评分 | `jojo_quality_score` | 数字 | 1-5 分，Approved 前必须填写 |
| 拒绝原因 | `jojo_kill_reason` | 单选 | wrong_state / bad_copy / wrong_ticker / missing_data / tone_off / other |
| 一句感受 | `jojo_one_word` | 文本 | 审核人的直觉反馈 |

结构判断：

- `质量评分` 是必要字段：它阻止“随手 Approved”的内容进入发布。
- `拒绝原因` 是必要字段：后续可以分析失败模式。
- `一句感受` 可选但有价值：能捕捉调性漂移。
- 当前还不需要单独建 `Video Packs` 表，短视频素材包先落在本地 `docs/growth-runs/{run_id}/video_packs/`。

## 表 3：表现数据 Performance

环境变量：`FEISHU_PERFORMANCE_TABLE_ID`

| 字段名 | 英文兼容名 | 类型 | 用途 |
| --- | --- | --- | --- |
| 内容ID | `content_id` | 文本主键 | 与内容队列对齐 |
| 曝光数 | `views` | 数字 | 未来接平台 API 后回填 |
| 点击数 | `clicks` | 数字 | VisitEvent 数量 |
| 邮件留资数 | `emails_captured` | 数字 | EmailLead 数量 |
| 注册数 | `signups` | 数字 | 已验证 email |
| 付费用户数 | `paid_users` | 数字 | 归因到 PRO 付费 |
| 点击到留资率 | `click_to_email_rate` | 百分比 | `emails_captured / clicks` |
| 免费到付费率 | `free_to_paid_rate` | 百分比 | `paid_users / emails_captured` |
| 预估获客成本 | `cac_estimate` | 数字 | 后续接广告或人工成本 |
| 备注 | `notes` | 文本 | 例如 `as of YYYY-MM-DD ET` |

结构判断：

- 现在最重要的是 `点击数`、`邮件留资数`、`点击到留资率`。
- `曝光数` 暂时可能为空，因为 X/Reddit/Shorts/TikTok 平台曝光 API 还没全部接入。
- `预估获客成本` 保留是合理的，但第一阶段不作为决策依据。

## 状态机

```text
Draft -> Pending -> Approved -> Published
                  -> Rejected

Approved -> Failed -> Pending（人工修复后重试）
Blocked  -> 不发布，只用于失败样本复盘
```

只有 `审核状态 = Approved` 且 `质量评分` 已填写的内容，才允许进入发布队列。

## 中文化操作

只审计，不改表：

```powershell
worker\.venv\Scripts\python.exe scripts\feishu\rename_growth_os_bitable_to_chinese.py --audit-only
```

打印计划，不改字段：

```powershell
worker\.venv\Scripts\python.exe scripts\feishu\rename_growth_os_bitable_to_chinese.py --dry-run
```

执行字段中文化：

```powershell
worker\.venv\Scripts\python.exe scripts\feishu\rename_growth_os_bitable_to_chinese.py
```

表名手动改：

```text
Campaigns -> 活动
Content Queue -> 内容队列
Performance -> 表现数据
```

## 当前建议

字段已经可以全部中文化；表名如果 OpenAPI 不支持，直接在飞书 UI 手动改，不影响 worker 运行。枚举值继续保留英文，代码判断更稳定。
