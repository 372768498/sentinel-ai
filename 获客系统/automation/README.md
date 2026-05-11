# automation/

自动化获客系统设计文档总目录。

| 子目录 | 内容 |
|--------|------|
| `feishu/` | 飞书多维表格结构说明、字段定义、状态机文档 |
| `content-factory/` | 多平台内容模板（X thread / Telegram / Shorts / Email） |
| `publishers/` | 各平台发布器规格（X / Telegram / YouTube / TikTok） |
| `specs/` | 系统接口规格、UTM 标准、Growth OS 架构图 |

> 运行代码在 `worker/app/marketing/`，本目录只放文档和规格。

## 四层架构

```
Layer 1 · Signal     → X / Reddit / Google Trends / OpenClaw adapter
Layer 2 · Content    → Composer + Redline + ContentItem
Layer 3 · Review     → Feishu Bitable + Bot + 人工审核
Layer 4 · Distribute → X / Telegram / TikTok / YouTube / Email + EmailLead
```

## 飞书表结构

见 `feishu/` 子目录（待 Week 2 补充）。
