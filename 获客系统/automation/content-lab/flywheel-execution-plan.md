# Sentinel AI 获客飞轮执行计划 v1

> 目标：把 `acquisition-flywheel-v1.md` 从策略文档拆成每天能执行、每周能复盘、每阶段能判断是否加码的工作清单。

## 这套飞轮先证明什么

第一阶段只证明一件事：

```text
Sentinel AI 能不能用“市场异常信号 + 用户焦虑解释”稳定获得合格 email lead。
```

不要在第一阶段同时证明账号矩阵、全自动发布、复杂视频模板、跨平台增长、付费广告。它们会稀释判断。

## 角色分工

| 角色 | 负责什么 | 第一阶段形态 |
| --- | --- | --- |
| Signal Scanner | 找到值得讲的 ticker / market state | 自动扫描，人工可补充 |
| Content Composer | 生成 X、Reddit、Shorts、TikTok 草稿 | 自动生成 |
| Compliance Redline | 检查投资建议红线和夸张表述 | 自动扫描 |
| Human Editor | 判断内容是否像真实用户会点 | 人工审核 |
| Publisher | 发布或导出内容包 | 半自动 |
| KPI Loop | 回收点击、email、注册、付费数据 | 自动聚合，人工复盘 |

## 每日执行节奏

### 09:00 ET 前：生成机会池

输入：

- 默认 watchlist。
- 当日 movers。
- 财报日历。
- SEC filing。
- X / Reddit 讨论热度。

输出：

- 5 个以内高优先级 opportunity。
- 每个 opportunity 必须有一个明确用户焦虑。

不满足条件就不生成内容：

```text
没有用户焦虑 = 没有内容。
```

### 09:00-10:00 ET：生成内容包

每个 opportunity 输出：

- 1 条 X post。
- 1 条 Reddit discussion draft。
- 1 条 Shorts/TikTok 脚本。
- 1 个 CTA URL。

内容包必须记录：

- `content_id`
- `campaign_id`
- platform
- ticker
- angle
- hook
- CTA
- source URLs
- redline result

### 10:00-11:00 ET：人工审核

审核只看四个问题：

1. 这个内容是否命中真实用户焦虑？
2. 开头 2 秒或第一句话是否足够明确？
3. 有没有投资建议、预测、夸张收益暗示？
4. CTA 是否把用户带到最相关的 Sentinel 页面？

审核结论：

| 结论 | 动作 |
| --- | --- |
| Approved | 进入发布 |
| Needs Edit | 修改 hook / evidence / CTA |
| Rejected | 丢弃，不补发 |

### 当日发布

第一阶段建议节奏：

| 平台 | 每日数量 | 发布方式 |
| --- | --- | --- |
| X | 3 条 | 审核通过后自动或半自动发布 |
| Reddit | 1 条 | 人工发布，避免账号风险 |
| Shorts/TikTok | 1 条成片或 2 条脚本 | 先人工上传 |
| Email | 对已留资用户发 scan | 自动发送 |

## 每日复盘

每天记录这 6 个数字：

- views
- clicks
- email captures
- signups
- first analysis
- paid conversions

每天只做一个判断：

```text
今天哪个 angle 最像可重复的获客资产？
```

不要因为单条爆了就立刻扩矩阵。先看它是否能重复。

## 每周复盘

每周一做 30 分钟复盘：

| 问题 | 判断标准 |
| --- | --- |
| 哪个 angle 带来最多合格 email？ | `qualified_email_leads` |
| 哪个 hook 点击高但留资低？ | click 高、email 低，说明承诺和落地页不匹配 |
| 哪个平台最值得继续？ | `lead_per_content_item` |
| 哪类 ticker 更容易转化？ | ticker / state 分组 |
| 哪些内容踩红线风险高？ | redline 高风险占比 |

输出：

- 下周保留 3 个 winning hooks。
- 停掉 3 个 losing formats。
- 给一个 angle 加码 3 个变体。

## 7 天实验

第一周只测试 3 个角度：

1. Earnings Watch
2. Crowded Trade
3. Watchlist Memory

每日最低产出：

- 3 条 X。
- 1 条 Reddit。
- 1 条短视频成片或完整 video pack。
- 1 封 email scan。

暂停规则：

```text
某个 angle 发满 10 条后仍然 0 email capture，暂停。
```

加码规则：

```text
某个 angle 连续两次 click-to-email rate 超过 8%，次日生成 3 个变体。
```

## 30 天阶段目标

### 第 1 周：证明链路

目标：

- CTA 能正确追踪。
- `/stocks/[ticker]` 能承接流量。
- email capture 能入库。
- 每条内容有 `content_id`。

不要做：

- AdsPower。
- 大量账号。
- 多模板视频系统。

### 第 2 周：提高内容质量

目标：

- 短视频 Skill 只打磨 1 个主模板。
- 建立内容评分。
- 建立每日复盘表。

### 第 3 周：固化有效角度

目标：

- 把 winning hooks 写进内容角度库。
- 对表现最好的 angle 做 5 个变体。
- 开始按 ticker state 分组分析。

### 第 4 周：决定是否进入第二阶段

进入第二阶段的条件：

- 连续 7 天都有 email lead。
- 至少 1 个 angle 可以重复获得点击和留资。
- landing capture path 没有明显漏斗断点。
- redline 高风险内容低于 5%。
- 短视频模板能稳定产出及格成片。

不满足就继续打磨第一阶段，不扩平台。

## Agent 能直接做的工作

- 维护内容角度库。
- 生成每日内容包。
- 检查红线。
- 生成 video pack。
- 生成 T+24h / T+72h 复盘草稿。
- 根据 KPI 更新下一天的内容权重。

## 用户必须提供或拍板的工作

- 平台 API Key 和账号权限。
- Reddit 目标社区名单。
- Shorts / TikTok 最终账号定位。
- 是否允许 live posting。
- 是否进入 AdsPower 矩阵阶段。

## 当前优先级

下一步只做三件事：

1. 把 20 个内容角度放进可复用库。
2. 重做短视频 Skill，让它稳定产出像样的财经信号栏目。
3. 打通 `content_id -> UTM -> email lead` 的数据闭环。
