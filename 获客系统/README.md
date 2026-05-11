# 获客系统 · Growth OS

Sentinel AI 获客系统总归档目录。

## 三块职责

| 目录 | 职责 |
|------|------|
| `landing/` | Landing 页面素材、原型、文案、参考笔记 |
| `automation/` | 自动化系统设计文档、Feishu 表结构、publisher 规格、content factory 模板 |
| `archive/` | 历史文件、废弃草稿、旧方案 |

## 代码位置原则

**文档 / 素材 / 原型 → 本目录**

**运行代码 → 框架正确位置**：

```
app/stocks/[ticker]/page.tsx
app/analysis/[shareId]/page.tsx
app/api/leads/capture/route.ts
app/api/auth/magic-link/route.ts
app/api/auth/verify/route.ts
app/api/track/visit/route.ts
lib/utm.ts
lib/rating.ts
worker/app/marketing/*
```

## Week 1 目标（Conversion Foundation）

```
/stocks/NVDA → 用户留 email → magic link → UTM 归因
```

## 参考文档

- 决策蓝图：`D:/code2026/jojo的AI服务toC知识库/业务/sentinel-ai/决策/获客系统/获客系统开发0511-codex.md`
- ENV 矩阵：`D:/code2026/sentinel-ai/docs/ENV_MATRIX.md`
