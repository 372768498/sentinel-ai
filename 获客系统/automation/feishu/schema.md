# Feishu Bitable Schema · Sentinel AI Growth OS

> Provisioned by `scripts/feishu/setup_bitable.py`.
> App location: bot's personal folder (folder_token 留空).

## Bitable App

| Field | Value |
|-------|-------|
| Name | Sentinel AI Growth OS |
| Env var | `FEISHU_BITABLE_APP_TOKEN` |
| Owner | Self-built app `sentinelai` (cli_aa8bfc65417c1bdd) |

## Table 1 · Campaigns

> 每日审核会话容器，按 session 聚合多条 content。

| Field | Type | Notes |
|-------|------|-------|
| `campaign_id` | Text (primary) | `CMP-YYYYMMDD-NN` |
| `date` | DateTime | 活动日期 |
| `session` | SingleSelect | Pre-market / Midday / Post-close / Breaking |
| `main_ticker` | Text | 主 ticker |
| `status` | SingleSelect | Draft / Review / Approved / Published / Rejected |
| `owner` | Text | 审核人（先用 Text，未来转 User type） |
| `notes` | Text | 备注 |

Env: `FEISHU_CAMPAIGNS_TABLE_ID`

## Table 2 · Content Queue

> 每条 platform-specific 草稿一行，redline + 人工审核状态机。

| Field | Type | Notes |
|-------|------|-------|
| `content_id` | Text (primary) | `CT-YYYYMMDD-TICKER-platform` |
| `campaign_id` | Text | 关联 Campaigns |
| `platform` | SingleSelect | X / Telegram / TikTok / YouTube Shorts / YouTube Long / Email |
| `ticker` | Text | |
| `hook` | Text | 开头钩子 |
| `body` | Text | 正文 |
| `cta_url` | URL | 落地页（含 UTM） |
| `risk_level` | SingleSelect | Low / Medium / High |
| `redline_result` | SingleSelect | Pass / Needs Edit / Blocked |
| `redline_hits` | Text | 命中词或缺失项 |
| `review_status` | SingleSelect | Pending / Approved / Rejected / Published / Failed |
| `reviewer_comment` | Text | 人工意见 |
| `publish_time` | DateTime | 计划/实际发布时间 |
| `published_url` | URL | 发布后 URL |

Env: `FEISHU_CONTENT_QUEUE_TABLE_ID`

## Table 3 · Performance

> KPI 回流，按 `content_id` 主键。

| Field | Type | Notes |
|-------|------|-------|
| `content_id` | Text (primary) | 与 Content Queue 对齐 |
| `views` | Number | |
| `clicks` | Number | |
| `emails_captured` | Number | |
| `signups` | Number | |
| `paid_users` | Number | |
| `click_to_email_rate` | Number (0.00%) | |
| `free_to_paid_rate` | Number (0.00%) | |
| `cac_estimate` | Number (0.00) | |
| `notes` | Text | |

Env: `FEISHU_PERFORMANCE_TABLE_ID`

## 状态机

```
Draft → Pending → Approved → Published
                 ↘ Rejected
                  
Approved → Failed → Pending（重试）
```

只有 `review_status = Approved` 进入发布队列。

## 字段类型映射（Feishu Bitable Field Type）

| Type | Code |
|------|------|
| Text | 1 |
| Number | 2 |
| SingleSelect | 3 |
| DateTime | 5 |
| URL | 15 |
