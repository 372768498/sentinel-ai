# Sentinel AI 内容角度库 v1

> 用途：给自动化获客系统提供可复用的内容角度。每个角度都必须绑定用户焦虑、hook 公式、证据类型和 CTA。

## 使用原则

内容角度不是“选题标题”。它是一个可重复的获客假设：

```text
当某类市场信号出现时，某类用户会因为某个焦虑点击 Sentinel 的 context scan。
```

每条内容必须从下表选择一个 angle。没有 angle 的内容不发布。

## 第一优先级角度

| Angle | 用户焦虑 | 适合信号 | Hook 公式 | CTA |
| --- | --- | --- | --- | --- |
| Earnings Watch | 财报前不知道该检查什么 | earnings date、guidance、recent move | `$TICKER before earnings: 3 risk flags to verify.` | `Run the pre-earnings context scan.` |
| Crowded Trade | 大家都太乐观，怕自己追高 | social heat、retail attention spike | `$TICKER is getting crowded again. Here is what changed.` | `Check the current Sentinel state.` |
| Watchlist Memory | 不在线时自选股发生变化 | overnight move、filing、news | `Your watchlist changed overnight. Sentinel caught this.` | `Add your tickers.` |
| Sudden Move | 股票突然动了但不知道原因 | price move、volume spike | `$TICKER moved. The move is not the story.` | `Preview what changed.` |
| Risk Stack | 多个风险叠在一起但用户没整合 | news + valuation + sentiment | `$TICKER has three risk flags stacked today.` | `Run the full scan.` |

## 第二优先级角度

| Angle | 用户焦虑 | 适合信号 | Hook 公式 | CTA |
| --- | --- | --- | --- | --- |
| Filing Alert | filing 太长，看不出重点 | 8-K、10-Q、insider filing | `$TICKER filed. Here is the part worth verifying.` | `Read the simplified context.` |
| Sentiment Divergence | 价格和情绪不一致 | price flat + social heat up | `$TICKER price is calm, but attention is heating up.` | `Check the signal mix.` |
| Retail Misread | 只看到 headline，忽略二阶风险 | viral headline、oversimplified narrative | `Retail is watching the headline. Sentinel flags the second-order risk.` | `See the context scan.` |
| Valuation Pressure | 好公司但估值叙事可能变 | valuation multiple、rate sensitivity | `$TICKER looks calm, but valuation pressure is building.` | `Check the risk flags.` |
| Competitor Alternative | 研究流程太碎，想找替代工具 | social complaint、tool comparison | `Still using screenshots and tabs for stock research?` | `Try a context scan.` |

## 可测试扩展角度

| Angle | 用户焦虑 | 内容形态 | 风险 |
| --- | --- | --- | --- |
| Before You Buy | 买前想快速排雷 | checklist | 容易像投资建议，必须避免 buy/sell 语气 |
| After The Headline | 新闻出来后不知道真正影响 | headline breakdown | 需要证据强，不能空泛 |
| Calm Before Event | 事件前价格平静但风险累积 | event radar | hook 不能夸张 |
| Insider Signal | 内部人交易或管理层动作 | filing explainer | 合规表达要保守 |
| Guidance Gap | 市场预期和公司指引不一致 | earnings prep | 需要准确 source |
| Narrative Shift | 市场叙事开始变化 | social + news synthesis | 容易主观，要给证据 |
| Watchlist Drift | 自选股从原本投资理由偏离 | email / app retention | 更适合已留资用户 |
| Compare The Context | 两只同类股票风险状态不同 | carousel / thread | 需要避免推荐哪只更好 |
| What Changed Today | 今天发生了什么 | daily digest | 容易泛化，要绑定 ticker |
| Risk Before Reward | 先看风险再看机会 | video / X | 容易负面过强，要平衡 |

## 平台适配

| 平台 | 最适合角度 | 不适合角度 |
| --- | --- | --- |
| X | Sudden Move、Crowded Trade、Risk Stack | 太长的 filing 解释 |
| Reddit | Filing Alert、Retail Misread、Competitor Alternative | 过硬 CTA、夸张 hook |
| YouTube Shorts | Earnings Watch、Sudden Move、Risk Stack | 证据链太复杂的长分析 |
| TikTok | Crowded Trade、Watchlist Memory、Risk Before Reward | 太专业的估值拆解 |
| Email | Watchlist Memory、What Changed Today、Calm Before Event | 泛社媒热帖 |

## Hook 写法规则

优先使用：

- `$TICKER moved, but the move is not the story.`
- `$TICKER before earnings: 3 things to verify.`
- `Your watchlist changed overnight.`
- `The headline is not the whole risk.`
- `Sentinel flagged a context shift in $TICKER.`

禁止使用：

- `Buy this before it explodes.`
- `AI predicts $TICKER will rally.`
- `This stock is guaranteed to move.`
- `Top stocks to buy now.`
- `Price target revealed.`

## CTA 写法规则

好的 CTA 必须是具体动作：

- `Run a free context scan.`
- `Check the current Sentinel state.`
- `See what changed before earnings.`
- `Add your tickers.`
- `Preview the risk flags.`

不要使用：

- `Learn more.`
- `Visit our website.`
- `Follow for more.`
- `Click here.`

## 复盘字段

每个 angle 每周记录：

- 发布数量。
- 平均 click rate。
- 平均 click-to-email rate。
- email-to-first-analysis rate。
- free-to-paid rate。
- redline 高风险比例。
- 最好 hook。
- 最差 hook。
- 下周动作：keep / edit / pause / scale。

## 第一周推荐组合

第一周只跑这 3 个：

1. Earnings Watch
2. Crowded Trade
3. Watchlist Memory

原因：

- 都能快速解释用户焦虑。
- 都适合短视频和图文。
- 都能自然引导到 `/stocks/[ticker]` 或 watchlist。
- 都不依赖复杂研究报告。
