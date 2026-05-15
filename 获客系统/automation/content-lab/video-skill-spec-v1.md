# Sentinel AI 短视频 Skill 规范 v1

> 目标：把短视频从“能生成一个视频文件”升级为“能稳定产出获客素材包”。第一版只打磨一个主模板：`Ticker State / Risk Stack`。

## 用户视角

目标用户不是来学剪辑，也不是来听财经播客。他在刷短视频时只有 2 秒耐心。

他愿意停下来的原因通常是：

- 他持有或关注这个 ticker。
- 他担心自己错过了风险。
- 他看到大家都在讨论，想知道有没有反面信息。
- 他想用更少时间理解今天发生了什么。

所以短视频不是讲完整研究报告，而是交付一个明确感受：

```text
Sentinel AI 比我更早、更稳定地发现市场状态变化。
```

## 栏目定位

栏目名建议：

```text
Sentinel Market State
```

每条视频只回答一个问题：

```text
这个 ticker 今天的状态发生了什么值得验证的变化？
```

不要回答：

- 该不该买。
- 会涨还是会跌。
- 目标价多少。
- 哪只股票最好。

## 主模板：Ticker State / Risk Stack

时长：18-28 秒。

画幅：1080x1920。

节奏：

| 时间 | 内容 | 目标 |
| --- | --- | --- |
| 0-2 秒 | ticker + state + 强 hook | 让用户停下 |
| 2-7 秒 | 信号 1 | 解释为什么值得看 |
| 7-12 秒 | 信号 2 | 增加可信度 |
| 12-17 秒 | 信号 3 或反常点 | 建立“风险叠加”感 |
| 17-23 秒 | Sentinel summary | 把复杂信息压缩成状态 |
| 23-28 秒 | CTA + disclaimer | 引导 context scan |

## 脚本结构

每条视频脚本固定 6 段：

```text
Hook:
$TICKER moved today, but the move is not the story.

Signal 1:
Volume expanded while the headline stayed simple.

Signal 2:
Retail attention rose faster than price.

Signal 3:
Earnings risk is now closer than most posts mention.

Sentinel State:
Sentinel marks this as a Risk Stack, not a buy signal.

CTA:
Run the free context scan. Context, not financial advice.
```

## 画面结构

每屏最多 12 个英文词或 18 个中文字符。

推荐画面：

1. Ticker 状态卡。
2. 三个 signal chips。
3. 简单折线或柱状图。
4. Sentinel state 总结。
5. CTA 安全区。

不做：

- 满屏财经截图。
- 太多小字。
- 股票 K 线堆满画面。
- AI 头像播报。
- 夸张红绿涨跌大字。

## 视觉风格

关键词：

- 清楚。
- 专业。
- 像产品界面，不像营销海报。
- 有金融工具感，但不要像交易软件。

建议元素：

- 深色背景 + 高对比白字。
- Sentinel 绿色只用于关键状态。
- 黄色用于注意事项。
- 红色只用于风险，不用于制造恐慌。
- 图表只展示趋势，不承诺方向。

## 必须产出的素材包

短视频 Skill 每次必须生成完整目录：

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

### `creative_brief.md`

包含：

- ticker。
- angle。
- 用户焦虑。
- 三个证据信号。
- 禁用词检查。
- CTA。

### `script.md`

包含：

- 完整旁白。
- 屏幕文字。
- 每段时间。
- disclaimer。

### `shot_plan.json`

机器可读，用于 renderer：

- scene id。
- duration。
- text layers。
- chart data。
- safe area。
- animation type。

### `captions.srt`

字幕必须和旁白一致。

### `cover.png`

封面必须在 1 秒内讲清：

```text
$TICKER Risk Stack
3 signals to verify
```

### `platform_copy.md`

分别输出：

- YouTube Shorts title。
- YouTube description。
- TikTok caption。
- pinned comment。
- hashtags。

### `qa_report.json`

记录：

- 分辨率是否 1080x1920。
- 时长是否 15-45 秒。
- 前 2 秒是否出现 ticker。
- 字幕是否在安全区。
- 是否出现禁用词。
- 是否包含 disclaimer。
- CTA 是否具体。

## 质量门槛

低于这些标准不允许发布：

| 检查项 | 标准 |
| --- | --- |
| 分辨率 | 1080x1920 |
| 时长 | 15-45 秒 |
| 前 2 秒 | 必须出现 ticker 和 state |
| 每屏文字 | 最多 12 个英文词或 18 个中文字符 |
| 字幕 | 必须在平台安全区 |
| CTA | 必须是具体动作 |
| 合规 | 必须有 disclaimer |
| 禁用词 | 不得出现 buy / sell / hold / price target / AI predicts |

## 第一版不要做什么

不要一开始做 10 个模板。

不要做复杂 3D。

不要做口播虚拟人。

不要自动追热点硬发。

不要把视频做成“财经知识课”。

第一版只把 `Ticker State / Risk Stack` 做到稳定、清楚、像 Sentinel AI 的产品能力展示。

## 成功标准

7 天内只看这几个指标：

- 平均观看完成率。
- profile click。
- CTA click。
- click-to-email rate。
- 评论里是否出现真实 ticker / watchlist 需求。

如果短视频只有播放，没有点击和 email，不算成功。

## 下一步实现反推

现有 renderer 可以保留 pipeline 概念，但需要升级：

- scene-based motion templates。
- safe-area-aware captions。
- cover image generation。
- SRT export。
- per-platform copy。
- video QA screenshots。

实现顺序：

1. 先实现 `creative_brief.md` 和 `script.md`。
2. 再实现 `shot_plan.json`。
3. 再实现 `cover.png`。
4. 最后生成 `video.mp4` 和 `qa_report.json`。
