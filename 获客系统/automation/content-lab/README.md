# Sentinel AI 内容实验室

> 本目录只放设计文档和执行规范，不放生产代码。
>
> 目标：让 Sentinel AI 的内容获客从“人工灵感”变成可持续迭代的系统：每天发现机会、生成内容、审核发布、记录转化、反哺下一轮创意。

## 文档入口

| 文档 | 用途 |
| --- | --- |
| `acquisition-flywheel-v1.md` | 获客飞轮总纲：用户心理、平台分工、7 天实验、30 天里程碑 |
| `flywheel-execution-plan.md` | 执行清单：每天、每周、每阶段具体做什么 |
| `content-angle-library.md` | 内容角度库：可复用 hook、用户焦虑、CTA、适配平台 |
| `video-skill-spec-v1.md` | 短视频 Skill 规范：脚本结构、画面结构、质量门槛、交付物 |
| `rubric.md` | 内容评分规则：未来用于自动打分和复盘权重更新 |

## 为什么要单独有 Content Lab

获客系统里有两件事容易混在一起：

| 模块 | 负责什么 | 回答的问题 |
| --- | --- | --- |
| Market Intelligence | 扫描市场、ticker、社媒热度、事件和机会 | 今天市场发生了什么，为什么是这个标的 |
| Content Lab | 把机会包装成用户愿意点击和留资的内容 | 这个机会应该怎么讲，用户为什么会行动 |

Market Intelligence 解决“有什么可讲”。Content Lab 解决“怎么讲才会转化”。

如果没有 Content Lab，系统会自然滑向“多扫 ticker、多发内容”。但 Sentinel AI 真正要优化的是：

```text
注意力 -> 点击 -> email lead -> 首次分析 -> 付费
```

所以每条内容都必须带着假设发布：

```text
我认为这个 hook 会提高 click-to-email，因为它命中了某个明确的用户焦虑。
```

发布后再用真实数据修正判断。

## 标准工作流

```text
市场机会
  -> 用户焦虑归因
  -> 选择内容角度
  -> 生成 X / Reddit / Shorts / TikTok 草稿
  -> 红线扫描
  -> 内容评分
  -> 人工审核
  -> 发布
  -> T+24h 复盘点击和 email
  -> T+72h 复盘注册和付费
  -> 更新内容角度权重
```

## 北极星指标

不要把 views 当成北极星。Sentinel AI 是 B2C SaaS，内容的任务不是“热闹”，而是把明确焦虑的用户带进产品。

北极星指标：

```text
qualified_email_leads_per_day
```

核心转化指标：

- `click_to_email_rate`
- `email_to_first_analysis_rate`
- `free_to_paid_rate`
- `lead_per_content_item`
- `lead_per_platform`

## 第一阶段边界

第一阶段只做四个平台：

- X：快速信号和日常 hook。
- Reddit：建立信任和讨论，不做硬广。
- YouTube Shorts：规模化发现入口。
- TikTok：测试年轻用户和高强度 hook。

AdsPower 矩阵获客放到第三阶段。矩阵只放大已经成立的内容和转化路径，不负责证明内容本身成立。

## 当前状态

| 项目 | 状态 |
| --- | --- |
| 获客飞轮总纲 | 已有 v1 |
| 执行计划 | 已有 v1 |
| 内容角度库 | 已有 v1 |
| 短视频 Skill 规范 | 已有 v1 |
| 自动评分实现 | 待实现 |
| 内容复盘入库 | 待实现 |
| 平台自动发布 | 分阶段实现 |
