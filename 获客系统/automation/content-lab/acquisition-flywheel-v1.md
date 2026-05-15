# Sentinel AI 获客飞轮 v1

> 目标：把用户的市场焦虑转化为 email lead，并最终转化为付费用户。
> 范围：第一阶段社交媒体获客，覆盖 X、Reddit、YouTube Shorts、TikTok。

## 市场依据

- FINRA 2025 年社交媒体投资报告显示：45% 投资者从互联网获得金融建议，24% 从社交媒体获得金融建议；30 岁以下投资者对社交媒体的依赖明显高于年长投资者。来源：<https://www.finra.org/rules-guidance/key-topics/fintech/report/social-media-influenced-investing>
- Pew 2024 年社交媒体报告显示：YouTube 是美国成年人覆盖面最广的平台之一，TikTok 相比 2021 年显著增长。来源：<https://www.pewresearch.org/internet/2024/01/31/americans-social-media-use/>
- YouTube 官方称 Shorts 日均观看量超过 700 亿。来源：<https://blog.youtube/inside-youtube/shorts-revenue-sharing-update/>
- TikTok 创意指南强调：开头必须快速抓住注意力，并且要有清晰 CTA。来源：<https://ads.tiktok.com/help/article/creative-best-practices>

## 用户心理

目标用户不是在找另一个财经博主。他们真正想快速解决 5 类焦虑：

| 用户焦虑 | 用户心里想什么 | Sentinel 内容承诺 |
| --- | --- | --- |
| 错过信号 | “我是不是漏掉了什么？” | 告诉他今天发生了什么变化。 |
| 叙事风险 | “大家都这么乐观，会不会有坑？” | 告诉他二阶风险是什么。 |
| 财报恐惧 | “财报前我该检查什么？” | 给出事件前的三个检查点。 |
| 时间不足 | “我没时间读财报、新闻和帖子。” | 让 Sentinel 帮他扫上下文。 |
| 自选股漂移 | “我不在线的时候，自选股发生了什么？” | 告诉他 watchlist overnight 变化。 |

内容永远不要回答：

```text
Should I buy?
```

内容只回答：

```text
在我相信市场叙事之前，我应该先验证什么？
```

## 核心信息

Sentinel AI 不是荐股工具，而是 context scanner：

```text
懂市场 -> 记住用户自选股 -> 主动标记变化
```

所有内容优先使用这类表达：

- `Run a free context scan.`
- `See what Sentinel flags before earnings.`
- `Check your watchlist state.`
- `Context, not financial advice.`

禁止使用：

- `buy / sell / hold`
- `price target`
- `AI predicts`
- `this stock will explode`
- `top stocks to buy`

## 四个飞轮

### 飞轮 1：信号 -> 内容

```text
market signal -> 用户焦虑角度 -> 平台草稿 -> 审核 -> 发布
```

输入来源：

- FMP quote / mover 数据
- SEC filing / EDGAR 上下文
- X SERP / X API 热度
- YouTube benchmark signals
- 用户 watchlist 里的 ticker seed

每个 opportunity 输出：

- X post
- Reddit discussion draft
- YouTube Shorts script / video
- TikTok script / video

决策规则：

```text
只有当 opportunity 能对应明确用户焦虑时，才生成内容。
没有焦虑 = 不发内容。
```

### 飞轮 2：内容 -> 线索

```text
social post -> UTM CTA -> /stocks/[ticker] -> email capture -> free scan
```

CTA 模式：

- `Run a free $TICKER context scan.`
- `Preview what changed in $TICKER.`
- `Check the current Sentinel state.`
- `See the three risk flags before earnings.`

不要使用：

- `Learn more`
- `Visit our site`
- `Follow for more`

优化指标：

```text
click_to_email_rate = EmailLead / VisitEvent
```

### 飞轮 3：线索 -> 习惯

```text
email capture -> seed tickers -> daily radar -> watchlist memory -> repeat visits
```

第一封邮件不应该是 newsletter，而应该是一份有用的 scan：

- 当前状态
- 发生了什么变化
- 三个 risk flags
- 下一个需要关注的事件

最强习惯触发语：

```text
Your watchlist changed overnight.
```

这比下面这句强：

```text
Here is today's market news.
```

### 飞轮 4：KPI -> 创意学习

```text
content_id -> visits -> emails -> signups -> paid -> template weights
```

每条内容必须记录：

- `content_id`
- platform
- ticker
- state
- angle
- hook
- CTA
- publish time

复盘节奏：

- T+24h：views / clicks / email captures
- T+72h：signups / paid
- 每周：winning hooks 和 losing formats

北极星指标：

```text
qualified_email_leads_per_day
```

辅助指标：

- click-to-email rate
- email-to-first-analysis rate
- free-to-paid rate
- lead per content item
- lead per platform

## 内容角度

| 角度 | 用户焦虑 | Hook 公式 | CTA |
| --- | --- | --- | --- |
| Earnings Watch | “财报前可能出什么问题？” | `$TICKER before earnings: 3 risk flags to verify.` | `Run the pre-earnings context scan.` |
| Crowded Trade | “大家是不是太乐观了？” | `$TICKER is getting crowded again. Here is what changed.` | `Check the current Sentinel state.` |
| Retail Misread | “我是不是只看到了表面 headline？” | `Retail is watching the headline. Sentinel flags the second-order risk.` | `See the context scan.` |
| Sudden Move | “为什么突然动了？” | `$TICKER moved. The move is not the story.` | `Preview what changed.` |
| Valuation Pressure | “什么会打破当前叙事？” | `$TICKER looks calm, but valuation pressure is building.` | `Check the risk flags.` |
| Watchlist Memory | “我不在线时发生了什么？” | `Your watchlist changed overnight. Sentinel caught this.` | `Add your tickers.` |
| Competitor Alternative | “有没有更好的美股研究工作流？” | `Still using screenshots and tabs for stock research?` | `Try a context scan.` |
| Filing Alert | “这份 filing 到底改变了什么？” | `$TICKER filed. Here is the part worth verifying.` | `Read the simplified context.` |
| Sentiment Divergence | “为什么价格和热度不一致？” | `$TICKER price is calm, but attention is heating up.` | `Check the signal mix.` |
| Risk Stack | “是不是多个风险叠在一起了？” | `$TICKER has three risk flags stacked today.` | `Run the full scan.` |

## 平台分工

| 平台 | 角色 | 第一阶段动作 |
| --- | --- | --- |
| X | 快速信号和日常 hook | Feishu 审核通过后，等 live credentials 准备好再自动发布。 |
| Reddit | 建立信任的讨论场 | 生成草稿，由人手动发到选定社区。 |
| YouTube Shorts | 大规模发现入口 | 生成 video pack，publisher 完成前手动上传。 |
| TikTok | 测 hook 和年轻用户 | 生成 video pack，publisher 完成前手动上传。 |
| Email | 习惯和留存 | 发送有用 scan，不做泛市场新闻。 |

## 7 天实验

每日输出：

- 3 条 X posts
- 1 条 Reddit draft
- 2 个 Shorts/TikTok video packs
- 1 封给已捕获 lead 的 email scan

第一周只测三个角度：

1. Earnings Watch
2. Crowded Trade
3. Watchlist Memory

每日复盘：

- click-to-email 最好的 hook
- bounce / no capture 最差的 hook
- lead count 最好的 ticker
- lead efficiency 最高的平台

暂停规则：

```text
某个角度发布 10 条后仍然 0 email capture，就暂停。
```

加码规则：

```text
某个角度两次超过 8% click-to-email rate，第二天生产 3 个变体。
```

## 30 天里程碑

第 1 周：

- 验证 CTA 和 capture path。
- 必要时手动发布。
- 不上 AdsPower。

第 2 周：

- 增加 video pack renderer 质量门槛。
- 开始 weekly creative retro。
- 平台数量保持少。

第 3 周：

- 把 winning hooks 固化成模板。
- 增加 YouTube / TikTok 上传 checklist。
- 按 ticker / state 分组 leads。

第 4 周：

- 决定 X live posting 是否持续打开。
- 决定 Shorts / TikTok 是否值得自动化。
- 定义 AdsPower readiness criteria，但不启动矩阵。

## Video Skill 要求

未来的视频 skill 不能只是 renderer。它必须生成完整获客素材包：

```text
creative_brief.md
script.md
shot_plan.json
captions.srt
cover.png
video.mp4
platform_copy.md
qa_report.json
```

最低 QA：

- 1080x1920
- 15-45 秒
- 前 2 秒必须出现 ticker 和 state
- 每屏最多 12 个词
- 字幕必须在平台安全区
- CTA 必须是具体动作
- 必须有 disclaimer
- 不得出现投资建议禁词

## 实现反推

当前 renderer 质量不够。可以保留 pipeline 概念，但要替换视觉系统：

- scene-based motion templates
- safe-area-aware captions
- cover image generation
- SRT export
- per-platform copy
- video QA screenshots

不要先做 10 个模板。先做一个足够好的 `Ticker State / Risk Stack` 模板，再用 KPI 决定第二个模板。
