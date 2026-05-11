"""
新手友好中文报告引擎 v12。

- 术语旁注释（GLOSSARY）
- 评分拆解表（加权过程透明化）
- 每维度详细分析（全部展开）
- 风险修正说明
- 投资建议 + 免责声明
"""

from datetime import datetime

from .constants import STOCK_WEIGHTS, raw_to_percentile, score_to_rating, get_valuation_thresholds


# ============================================================================
# 术语注释字典
# ============================================================================

GLOSSARY: dict[str, str] = {
    "pe_ratio": "市盈率：股价 / 每股盈利，越低越「便宜」",
    "peg_ratio": "市盈增长比：P/E / 盈利增速，<1 被低估",
    "ps_ratio": "市销率：市值 / 营收",
    "pb_ratio": "市净率：市值 / 净资产",
    "ev_ebitda": "企业价值倍数：参考板块阈值判断",
    "gross_margin": "毛利率：扣除直接成本后的利润率",
    "net_margin": "净利率：最终利润占收入比例",
    "roe": "净资产收益率：股东资金赚钱效率，>15% 优秀",
    "roa": "总资产收益率：>10% 优秀",
    "current_ratio": "流动比率：>2 安全，<1 危险",
    "debt_to_equity": "负债权益比：<1 健康，>2 高风险",
    "fcf": "自由现金流：可自由支配的现金",
    "free_cashflow": "自由现金流：可自由支配的现金",
    "rsi": "相对强弱指数：>70 超买，<30 超卖",
    "macd": "平滑异同移动平均线：金叉看多，死叉看空",
    "bollinger": "布林带：价格触及上轨偏贵，触及下轨偏便宜",
    "ma": "移动平均线：N 日收盘价均值，反映趋势",
    "vix": "恐慌指数：>30 恐慌，<20 平静",
    "fear_greed": "恐惧贪婪指数：<25 极度恐惧（反转信号），>75 极度贪婪",
    "short_interest": "空头比例：被做空股票占流通股比例",
    "put_call": "Put/Call 比率：看跌 / 看涨期权成交量",
    "eps": "每股盈利：公司每股赚了多少钱",
    "revenue_growth": "营收增长率：收入的同比变化",
    "market_regime": "市场状态：通过趋势和波动判断的市场阶段",
    "relative_strength": "相对强度：个股表现 vs 板块表现的差值",
}


# ============================================================================
# 维度中文名 + 权重键映射
# ============================================================================

DIMENSION_META = [
    ("earnings_surprise", "盈利惊喜", "earnings_surprise"),
    ("fundamentals", "基本面", "fundamentals"),
    ("analyst_sentiment", "分析师情绪", "analyst_sentiment"),
    ("historical_patterns", "历史表现", "historical_patterns"),
    ("market_context", "市场环境", "market_context"),
    ("sector_performance", "板块强度", "sector_performance"),
    ("technical", "技术分析", "technical"),
    ("sentiment_analysis", "市场情绪", "sentiment"),
    ("peer_comparison", "同行对比", "peer_comparison"),
]


# ============================================================================
# 顶层入口
# ============================================================================

def format_report(
    signal,
    *,
    data_info: dict | None = None,
    technical=None,
    peer=None,
    sentiment=None,
    deep_valuation=None,
    web_verification=None,
) -> str:
    """组装完整中文 Markdown 报告。"""
    info = data_info or {}
    sector = info.get("sector", "")
    parts = [
        _header(signal),
        _quick_overview(signal),
        _market_quote(signal, info),
        _score_summary(signal),
        _score_breakdown(signal),
    ]

    # 各维度章节（全部展开）
    parts.append(_section_earnings(signal.components))
    parts.append(_section_fundamentals(signal.components, info, sector))
    parts.append(_section_analysts(signal.components))
    parts.append(_section_historical(signal.components))
    parts.append(_section_market(signal.components))
    parts.append(_section_sector(signal.components))
    parts.append(_section_technical(signal.components, technical))
    parts.append(_section_sentiment(signal.components, sentiment))
    parts.append(_section_peer(signal.components, peer))

    parts.append(_risk_adjustments(signal.components))
    parts.append(_risk_assessment(signal))
    parts.append(_investment_summary(signal, deep_valuation))
    parts.append(_reading_guide())
    parts.append(_data_verification(signal))
    parts.append(_disclaimer())

    return "\n".join(p for p in parts if p)


# ============================================================================
# 报告段落生成
# ============================================================================

def _header(signal) -> str:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    return (
        f"# {signal.ticker} {signal.company_name} 综合分析报告\n\n"
        f"> 生成时间：{ts} | 数据源：Yahoo Finance（延迟 15-20 分钟）\n"
    )


def _quick_overview(signal) -> str:
    """速览：一句话总结核心结论。"""
    rating_cn = _rating_cn(signal.rating)
    s = signal.score_100
    if s >= 80:
        desc = "多项指标共振看多，信号强烈"
    elif s >= 65:
        desc = "整体偏正面，多数维度支持看好"
    elif s >= 50:
        desc = "多空分歧较大，没有明确方向，建议观望"
    elif s >= 35:
        desc = "多数维度偏负面，下行风险较大"
    else:
        desc = "多项指标发出警告信号，风险显著"
    return (
        "---\n\n"
        "## 速览\n\n"
        f"**{signal.score_100} 分 = {rating_cn}**：{desc}。\n\n"
        "> 本报告包含 9 个评分维度 + 财报时间修正器。如果时间有限，重点看「评分拆解」和「投资建议」两节。\n"
    )


def _market_quote(signal, info: dict) -> str:
    price = info.get("regularMarketPrice") or info.get("currentPrice")
    change = info.get("regularMarketChangePercent")
    volume = info.get("volume")
    avg_volume = info.get("averageVolume")
    market_cap = info.get("marketCap")
    high_52w = info.get("fiftyTwoWeekHigh")
    low_52w = info.get("fiftyTwoWeekLow")

    lines = ["---", "", "## 实时行情", ""]
    if price:
        change_str = f" ({change:+.2f}%)" if change else ""
        lines.append(f"- **价格**：${price:.2f}{change_str}")
    if volume:
        vol_str = f"{volume:,}"
        if avg_volume:
            ratio = volume / avg_volume if avg_volume else 0
            vol_str += f"（均量 {avg_volume:,}，比值 {ratio:.1f}x）"
        lines.append(f"- **成交量**：{vol_str}")
    cap_str = _fmt_cap(market_cap) if market_cap else "N/A"
    lines.append(f"- **市值**：{cap_str}")
    if low_52w and high_52w:
        lines.append(f"- **52 周范围**：${low_52w:.2f} — ${high_52w:.2f}")
    lines.append("")

    # 行情解读
    lines.append("**行情解读**")
    if price and low_52w and high_52w and high_52w > low_52w:
        pct_pos = (price - low_52w) / (high_52w - low_52w) * 100
        if pct_pos > 80:
            lines.append(f"- 当前价格处于 52 周范围的 {pct_pos:.0f}% 高位——接近历史高点，追高需谨慎，建议等待回调。")
        elif pct_pos < 20:
            lines.append(f"- 当前价格处于 52 周范围的 {pct_pos:.0f}% 低位——可能是超卖反弹机会，但也需排查基本面恶化。")
        else:
            lines.append(f"- 当前价格处于 52 周范围的 {pct_pos:.0f}% 位置，估值区间合理。")
    if volume and avg_volume:
        ratio = volume / avg_volume
        if ratio > 1.5:
            lines.append(f"- 成交量放大 {ratio:.1f} 倍——有异常资金活动，需关注是利好驱动还是恐慌抛售。")
        elif ratio < 0.5:
            lines.append(f"- 成交量仅为均量的 {ratio:.1f} 倍——市场观望情绪浓厚，趋势确认度低。")
    if market_cap:
        if market_cap >= 200e9:
            lines.append("- 大型股（市值 >$200B），流动性充足，适合大额交易和机构持仓。")
        elif market_cap >= 10e9:
            lines.append("- 中大型股，流动性良好，兼具稳定性和成长潜力。")
        else:
            lines.append("- 中小型股，波动性可能较大，流动性有限，需控制仓位。")
    lines.append("")
    return "\n".join(lines)


def _score_summary(signal) -> str:
    rating_cn = _rating_cn(signal.rating)
    conf_level = _confidence_cn(signal.confidence)
    conf_explain = _confidence_explain(signal.confidence)
    return (
        "---\n\n"
        f"## 综合评分：{signal.score_100}/100 — {rating_cn}\n\n"
        f"置信度：{conf_level}（{signal.confidence * 100:.0f}%）— {conf_explain}\n"
    )


def _score_breakdown(signal) -> str:
    """评分拆解表 —— 核心新增。"""
    comps = signal.components
    lines = [
        "### 评分拆解", "",
        "| # | 维度 | 原始分 | 权重 | 加权分 | 信号 |",
        "|---|------|--------|------|--------|------|",
    ]
    idx = 1
    total_weighted = 0.0
    total_weight = 0.0

    for comp_key, cn_name, weight_key in DIMENSION_META:
        dim = comps.get(comp_key)
        if not dim:
            continue
        raw = dim.get("score")
        if raw is None:
            continue

        raw_100 = raw_to_percentile(raw)
        weight_pct = STOCK_WEIGHTS.get(weight_key, 0)
        weighted = raw_100 * weight_pct
        total_weighted += weighted
        total_weight += weight_pct
        sig = _signal_text(raw_100)

        lines.append(
            f"| {idx} | {cn_name} | {raw_100} | {weight_pct * 100:.0f}% "
            f"| {weighted:.1f} | {sig} |"
        )
        idx += 1

    # 归一化合计（权重可能不满 100%）
    if total_weight > 0:
        normalized = total_weighted / total_weight
    else:
        normalized = signal.score_100

    rating_cn = _rating_cn(signal.rating)
    lines.append(
        f"| — | **合计** | — | 100% | **{signal.score_100}** | **{rating_cn}** |"
    )
    lines.append("")
    lines.append("> **评分逻辑**：每个维度独立打分（0-100），按权重加权平均得出综合评分。基本面（20%）权重最高，盈利惊喜（15%）和技术/分析师（各 12%）次之。")
    lines.append("")
    # 强弱信号可视化
    strong_bull = [cn for _, cn, _ in DIMENSION_META if raw_to_percentile(comps.get(_, {}).get("score", 0)) >= 75]
    strong_bear = [cn for _, cn, _ in DIMENSION_META if raw_to_percentile(comps.get(_, {}).get("score", 0)) < 30]
    if strong_bull:
        lines.append(f"> **最强看多维度**：{', '.join(strong_bull)}——这些领域给出了最积极的信号。")
    if strong_bear:
        lines.append(f"> **最强看空维度**：{', '.join(strong_bear)}——这些领域的警告信号不容忽视。")
    if not strong_bull and not strong_bear:
        lines.append("> 各维度评分集中在中间区域，没有特别突出的强信号——市场对该股的看法较为分散。")
    lines.append("\n")
    return "\n".join(lines)


# ============================================================================
# 各维度章节
# ============================================================================

def _section_earnings(comps: dict) -> str:
    dim = comps.get("earnings_surprise")
    if not dim:
        return ""

    raw_100 = raw_to_percentile(dim.get("score", 0))
    sig = _signal_text(raw_100)
    header = f"## 一、盈利惊喜（Earnings Surprise）\n\n得分：{raw_100}/100 | 权重：15% | 信号：{sig}\n"

    lines = [header, "**数据**"]
    actual = dim.get("actual_eps")
    expected = dim.get("expected_eps")
    surprise = dim.get("surprise_pct")

    if actual is not None:
        lines.append(f"- 实际 {_annotate('eps')}：${actual:.2f}")
    if expected is not None:
        lines.append(f"- 预期 EPS：${expected:.2f}")
    if surprise is not None:
        lines.append(f"- 惊喜幅度：{surprise:+.1f}%")

    lines.append("")
    lines.append("**解读**")
    if surprise and surprise > 0:
        grade = "大幅" if surprise > 10 else ("显著" if surprise > 5 else "小幅")
        lines.append(
            f"EPS 超预期 {surprise:.1f}%（{grade}超预期），说明盈利能力超出分析师集体预判，"
            "通常意味着业务基本面强劲。"
        )
        if surprise > 10:
            lines.append("超预期幅度 >10% 属于罕见的大幅超预期，历史上此类事件后股价短期上涨概率较高。")
        lines.append("持续超预期的公司通常拥有保守的管理层指引——这本身就是正面信号。")
    elif surprise and surprise < 0:
        grade = "大幅" if abs(surprise) > 10 else ("显著" if abs(surprise) > 5 else "小幅")
        lines.append(
            f"EPS 不及预期 {abs(surprise):.1f}%（{grade}不及预期），表明盈利低于市场预期，"
            "可能反映需求放缓或成本压力。"
        )
        if abs(surprise) > 10:
            lines.append("大幅不及预期通常引发股价剧烈反应，市场可能重新评估公司的增长逻辑。")
    else:
        lines.append("EPS 与预期基本持平，短期缺乏催化剂。")
    lines.append("")
    return "\n".join(lines)


def _section_fundamentals(comps: dict, info: dict, sector: str = "") -> str:
    dim = comps.get("fundamentals")
    if not dim:
        return ""

    raw_100 = raw_to_percentile(dim.get("score", 0))
    sig = _signal_text(raw_100)
    header = f"## 二、基本面（Fundamentals）\n\n得分：{raw_100}/100 | 权重：20% | 信号：{sig}\n"

    lines = [header]

    # 子评分分拆（估值面 vs 质量面）
    val_sub = dim.get("_valuation_sub_score")
    qual_sub = dim.get("_quality_sub_score")
    if val_sub is not None or qual_sub is not None:
        lines.append("### 子评分分拆")
        lines.append("")
        lines.append("| 类别 | 子评分 | 说明 |")
        lines.append("|------|--------|------|")
        if val_sub is not None:
            val_100 = raw_to_percentile(val_sub)
            lines.append(f"| 估值面 | {val_100}/100 | P/E、P/S、P/B、EV/EBITDA |")
        if qual_sub is not None:
            qual_100 = raw_to_percentile(qual_sub)
            lines.append(f"| 质量面 | {qual_100}/100 | ROE、利润率、FCF、偿债 |")
        lines.append(f"| **综合** | **{raw_100}/100** | 加权平均 |")
        lines.append("")

    # 估值指标表
    valuation = [
        ("P/E", "pe_ratio", None, "x"),
        ("PEG", "peg_ratio", None, ""),
        ("P/S", "ps_ratio", None, "x"),
        ("P/B", "pb_ratio", None, "x"),
        ("EV/EBITDA", "ev_ebitda", None, "x"),
    ]
    lines.extend(_metric_table("估值指标", valuation, dim, sector))

    # 盈利能力表
    profitability = [
        ("毛利率（TTM）", "gross_margin", "%", "%"),
        ("净利率（TTM）", "net_margin", "%", "%"),
        ("ROE", "roe", "%", "%"),
        ("ROA", "roa", "%", "%"),
    ]
    lines.extend(_metric_table("盈利能力", profitability, dim, sector))

    # 财务健康表
    health = [
        ("流动比率", "current_ratio", None, ""),
        ("负债权益比", "debt_to_equity", None, "x"),
        ("自由现金流", "free_cashflow", "$", ""),
    ]
    lines.extend(_metric_table("财务健康", health, dim, sector))

    lines.append("**评分理由**")
    if val_sub is not None and qual_sub is not None:
        v100 = raw_to_percentile(val_sub)
        q100 = raw_to_percentile(qual_sub)
        if v100 >= 60 and q100 >= 60:
            lines.append("估值合理 + 质量优秀——理想的投资候选，兼具价值和品质。")
        elif v100 < 50 and q100 >= 55:
            lines.append("好公司但估值偏贵——可等待回调后再布局。")
        elif v100 >= 50 and q100 < 50:
            lines.append("估值便宜但质量堪忧——可能是价值陷阱，需深入调查。")
        else:
            lines.append("以上指标加权平均后得出基本面综合评分。")
    else:
        lines.append("以上指标加权平均后得出基本面综合评分，估值偏高或盈利能力弱会压低得分。")
    lines.append("")
    # 关键指标深度解读
    roe = dim.get("roe")
    cr = dim.get("current_ratio")
    gm = dim.get("gross_margin")
    if roe and roe > 20:
        lines.append(f"ROE {roe:.0f}% 远超行业平均——股东资金使用效率极高，但需关注是否由高杠杆驱动。")
    if cr is not None and cr < 1:
        lines.append(f"流动比率 {cr:.2f} < 1——流动资产不足以覆盖短期负债，存在流动性风险。对于科技巨头而言，充裕的现金流可一定程度上弥补。")
    if gm and gm > 40:
        lines.append(f"毛利率 {gm:.1f}% 体现了很强的定价权，说明产品或服务具有显著的竞争壁垒。")
    lines.append("")
    return "\n".join(lines)


def _section_analysts(comps: dict) -> str:
    dim = comps.get("analyst_sentiment")
    if not dim:
        return ""

    score = dim.get("score")
    raw_100 = raw_to_percentile(score) if score is not None else 50
    sig = _signal_text(raw_100)
    header = f"## 三、分析师情绪（Analyst Sentiment）\n\n得分：{raw_100}/100 | 权重：12% | 信号：{sig}\n"

    lines = [header, "**数据**"]
    consensus = dim.get("consensus_rating")
    target = dim.get("price_target")
    current = dim.get("current_price")
    upside = dim.get("upside_pct")
    num = dim.get("num_analysts")

    if consensus:
        lines.append(f"- 共识评级：{consensus}")
    if target:
        lines.append(f"- 目标价：${target:.2f}")
    if current:
        lines.append(f"- 当前价：${current:.2f}")
    if upside is not None:
        lines.append(f"- 潜在涨幅：{upside:+.1f}%")
    if num:
        lines.append(f"- 分析师数量：{num}")

    lines.append("")
    lines.append("**解读**")
    if upside and upside > 20:
        lines.append("分析师集体看好，目标价显著高于现价，暗示较大上涨空间。")
        lines.append("但需注意分析师目标价通常存在 10-20% 的乐观偏差——实际涨幅可能低于预期。")
    elif upside and upside < -10:
        lines.append("分析师目标价低于现价，意味着市场可能高估了当前价格。")
        lines.append("当多数分析师看衰时，要么市场已过热，要么存在尚未反映的利空信息。")
    else:
        lines.append("分析师预期温和，股价接近集体估值中枢。")
    if num:
        if num >= 30:
            lines.append(f"共 {num} 位分析师覆盖——研究覆盖充分，共识评级可参考性强。")
        elif num >= 10:
            lines.append(f"共 {num} 位分析师覆盖——覆盖适中，评级具有一定参考价值。")
        else:
            lines.append(f"仅 {num} 位分析师覆盖——覆盖不足，评级代表性有限，需谨慎参考。")
    if consensus:
        if consensus.lower() in ("strong buy", "buy") and upside and upside < 5:
            lines.append("注意：虽然外部共识偏积极但潜在涨幅有限——可能意味着上行空间已基本兑现。")
    lines.append("")
    return "\n".join(lines)


def _section_historical(comps: dict) -> str:
    dim = comps.get("historical_patterns")
    if not dim:
        return ""

    raw_100 = raw_to_percentile(dim.get("score", 0))
    sig = _signal_text(raw_100)
    header = f"## 四、历史表现（Historical Patterns）\n\n得分：{raw_100}/100 | 权重：5% | 信号：{sig}\n"

    lines = [header, "**数据**"]
    beats = dim.get("beats_last_4q")
    avg_react = dim.get("avg_reaction_pct")
    if beats is not None:
        total_q = comps.get("historical_patterns", {}).get("total_quarters") or 4
        lines.append(f"- 过去 {total_q} 季度超预期次数：{beats}/{total_q}")
    if avg_react is not None:
        lines.append(f"- 平均财报后反应：{avg_react:+.1f}%")
    lines.append("")
    lines.append("**解读**")
    if beats is not None and beats >= 3:
        lines.append("连续超预期说明管理层指引可信度高，盈利能力稳定。")
        lines.append("持续超预期的公司往往形成「指引保守→超预期→预期上调」的正循环，长期看是积极信号。")
    elif beats is not None and beats <= 1:
        lines.append("历史超预期率低，需审慎对待当前预期，警惕业绩不达预期。")
        lines.append("低超预期率可能意味着管理层对业务节奏的把控力不足，或行业波动性较大。")
    else:
        lines.append("历史表现中规中矩，财报反应需结合当时市场环境判断。")
    if avg_react is not None:
        if avg_react > 3:
            lines.append(f"财报后平均涨 {avg_react:.1f}%——市场对该公司财报反应积极。")
        elif avg_react < -3:
            lines.append(f"财报后平均跌 {avg_react:.1f}%——即使超预期也可能下跌，需关注预期提前兑现。")
    lines.append("")
    return "\n".join(lines)


def _section_market(comps: dict) -> str:
    dim = comps.get("market_context")
    if not dim:
        return ""

    raw_100 = raw_to_percentile(dim.get("score", 0))
    sig = _signal_text(raw_100)
    header = f"## 五、市场环境（Market Context）\n\n得分：{raw_100}/100 | 权重：8% | 信号：{sig}\n"

    lines = [header, "**数据**"]
    vix = dim.get("vix_level")
    vix_status = dim.get("vix_status")
    spy = dim.get("spy_trend_10d")
    qqq = dim.get("qqq_trend_10d")
    regime = dim.get("market_regime")
    risk_off = dim.get("risk_off_detected")

    if vix is not None:
        lines.append(f"- {_annotate('vix')}：{vix:.1f}（{vix_status}）")
    if spy is not None:
        lines.append(f"- SPY 10 日趋势：{spy:+.1f}%")
    if qqq is not None:
        lines.append(f"- QQQ 10 日趋势：{qqq:+.1f}%")
    if regime:
        lines.append(f"- 市场状态：{regime}")
    if risk_off:
        lines.append("- **避险模式已触发**")
    lines.append("")
    lines.append("**解读**")
    if vix is not None and vix > 30:
        lines.append("市场恐慌期间，个股分析需打折扣——系统性风险压制所有标的。")
        lines.append("VIX > 30 通常意味着市场处于危机模式，此时相关性飙升，所有股票同涨同跌。建议等待 VIX 回落至 25 以下后再做个股决策。")
    elif risk_off:
        lines.append("避险模式触发（GLD/TLT/UUP 同涨），风险资产整体承压。")
        lines.append("资金正从股票市场流向避险资产——此时应降低整体仓位、减少进攻性配置。")
    elif vix is not None and vix < 20 and spy is not None and spy > 0:
        lines.append("市场环境有利——低波动 + 指数上行，个股表现更容易兑现。")
        lines.append("低 VIX 环境下，基本面优秀的个股更容易获得市场关注和资金流入。")
    else:
        lines.append("市场环境中性，个股走势更多由自身基本面驱动。")
    if regime:
        regime_desc = {
            "trending": "趋势行情——顺趋势操作胜率更高，避免逆势抄底",
            "choppy": "震荡行情——适合区间操作，不宜重仓追涨或追跌",
            "crisis": "危机行情——以保全本金为第一优先，减少交易频率",
        }
        desc = regime_desc.get(regime)
        if desc:
            lines.append(f"当前市场状态为 {regime}：{desc}。")
    lines.append("")
    return "\n".join(lines)


def _section_sector(comps: dict) -> str:
    dim = comps.get("sector_performance")
    if not dim:
        return ""

    raw_100 = raw_to_percentile(dim.get("score", 0))
    sig = _signal_text(raw_100)
    header = f"## 六、板块强度（Sector Performance）\n\n得分：{raw_100}/100 | 权重：8% | 信号：{sig}\n"

    lines = [header, "**数据**"]
    sector = dim.get("sector_name")
    stock_ret = dim.get("stock_return_1m")
    sector_ret = dim.get("sector_return_1m")
    rel = dim.get("relative_strength")

    if sector:
        lines.append(f"- 所属板块：{sector}")
    if stock_ret is not None:
        lines.append(f"- 个股 1 月回报：{stock_ret:+.1f}%")
    if sector_ret is not None:
        lines.append(f"- 板块 1 月回报：{sector_ret:+.1f}%")
    if rel is not None:
        lines.append(f"- 相对强度：{rel:+.1f}pp")
    lines.append("")
    lines.append("**解读**")
    diff = (stock_ret or 0) - (sector_ret or 0)
    if diff > 5:
        lines.append(f"个股跑赢板块 {diff:.1f}pp，展现独立于板块的强势——Alpha 能力突出。")
        lines.append("这种超额表现通常由公司特有的积极因素驱动（财报超预期、新产品发布等）。")
    elif diff < -5:
        lines.append(f"个股跑输板块 {abs(diff):.1f}pp，需排查公司层面的负面因素。")
        lines.append("板块涨而个股跌，意味着问题出在公司自身而非行业。建议检查是否有未披露的利空消息。")
    else:
        lines.append("个股与板块走势基本同步，表现由板块 Beta 驱动。")
    if sector_ret is not None:
        if sector_ret > 5:
            lines.append(f"板块整体走强（月涨 {sector_ret:.1f}%），板块轮动处于有利位置。")
        elif sector_ret < -5:
            lines.append(f"板块整体走弱（月跌 {abs(sector_ret):.1f}%），即使个股优秀也可能受到板块拖累。")
    lines.append("")
    return "\n".join(lines)


def _section_technical(comps: dict, technical) -> str:
    dim = comps.get("technical")
    if not dim:
        return ""

    raw_100 = raw_to_percentile(dim.get("score", 0))
    sig = _signal_text(raw_100)
    header = f"## 七、技术分析（Technical Analysis）\n\n得分：{raw_100}/100 | 权重：12% | 信号：{sig}\n"

    lines = [header]

    # 趋势与动量
    lines.append("### 趋势与动量")
    trend = dim.get("trend", "")
    ma_align = dim.get("ma_alignment", "")
    macd_trend = dim.get("macd_trend", "")
    rsi = dim.get("rsi_14d")
    rsi_status = dim.get("rsi_status", "")

    lines.append(f"- 短期趋势：**{trend}**")
    lines.append(f"- {_annotate('ma')} 排列：{ma_align}")
    lines.append(f"- {_annotate('macd')}：{macd_trend}")
    if rsi is not None:
        lines.append(f"- {_annotate('rsi')}(14)：{rsi:.0f} — {rsi_status}")
    lines.append("")

    # 关键价位
    lines.append("### 关键价位")
    support = dim.get("support")
    resistance = dim.get("resistance")
    bb = dim.get("bb_position", "")
    vol_ratio = dim.get("volume_ratio")

    if support:
        lines.append(f"- 支撑位：${support}")
    if resistance:
        lines.append(f"- 阻力位：${resistance}")
    lines.append(f"- {_annotate('bollinger')}位置：{bb}")
    if vol_ratio is not None:
        lines.append(f"- 成交量比值：{vol_ratio:.1f}x")
    lines.append("")

    # 技术面综合解读
    lines.append("**解读**")
    # 趋势综合判断
    trend_signals = []
    if "up" in trend.lower() or "上升" in trend:
        trend_signals.append("短期趋势向上")
    elif "down" in trend.lower() or "下降" in trend:
        trend_signals.append("短期趋势向下")
    if "bullish" in ma_align.lower() or "多头" in ma_align:
        trend_signals.append("均线多头排列")
    elif "bearish" in ma_align.lower() or "空头" in ma_align:
        trend_signals.append("均线空头排列")
    if "bullish" in macd_trend.lower() or "多" in macd_trend:
        trend_signals.append("MACD 看多")
    elif "bearish" in macd_trend.lower() or "空" in macd_trend:
        trend_signals.append("MACD 看空")
    if trend_signals:
        lines.append(f"趋势信号：{'、'.join(trend_signals)}。")

    # RSI 操作建议
    if rsi is not None:
        if rsi > 70:
            lines.append(f"RSI {rsi:.0f} 处于超买区域——短期追高风险大，可等待回调到 60 附近再考虑加仓。")
        elif rsi < 30:
            lines.append(f"RSI {rsi:.0f} 处于超卖区域——可能存在技术性反弹机会，但需确认下跌动能减弱后再入场。")
        elif rsi >= 50:
            lines.append(f"RSI {rsi:.0f} 处于多方区间，动能健康。")
        else:
            lines.append(f"RSI {rsi:.0f} 偏弱，动能不足，反弹力度可能受限。")

    # 支撑阻力操作参考
    price = comps.get("analyst_sentiment", {}).get("current_price")
    if support and resistance and price:
        try:
            s, r_val = float(support), float(resistance)
            dist_sup = (price - s) / price * 100
            dist_res = (r_val - price) / price * 100
            lines.append(f"距支撑位 {dist_sup:.1f}%，距阻力位 {dist_res:.1f}%——{'接近支撑，注意止损' if dist_sup < 3 else ('接近阻力，突破确认前谨慎' if dist_res < 3 else '处于支撑阻力之间，空间充足')}。")
        except (TypeError, ValueError, ZeroDivisionError):
            pass

    # 成交量确认
    if vol_ratio is not None:
        if vol_ratio > 1.5:
            lines.append("成交量放大——当前走势得到资金面确认，趋势可信度高。")
        elif vol_ratio < 0.7:
            lines.append("成交量萎缩——市场参与度低，趋势持续性存疑。")
    lines.append("")
    return "\n".join(lines)


def _section_sentiment(comps: dict, sentiment) -> str:
    dim = comps.get("sentiment_analysis")
    if not dim:
        return ""

    raw_100 = raw_to_percentile(dim.get("score", 0))
    sig = _signal_text(raw_100)
    header = f"## 八、市场情绪（Sentiment Analysis）\n\n得分：{raw_100}/100 | 权重：10% | 信号：{sig}\n"

    lines = [header, "**数据**"]
    fg_val = dim.get("fear_greed_value")
    fg_status = dim.get("fear_greed_status")
    si = dim.get("short_interest_pct")
    pc = dim.get("put_call_ratio")
    vix_struct = dim.get("vix_structure")

    if fg_val is not None:
        lines.append(f"- {_annotate('fear_greed')}：{fg_val:.0f}（{fg_status}）")
    if si is not None:
        lines.append(f"- {_annotate('short_interest')}：{si:.1f}%")
    if pc is not None:
        lines.append(f"- {_annotate('put_call')}：{pc:.2f}")
    if vix_struct:
        lines.append(f"- VIX 期限结构：{vix_struct}")

    lines.append("")
    lines.append("**解读**")
    if fg_val is not None and float(fg_val) < 25:
        lines.append("极度恐惧区间，历史上常出现反转窗口。")
        lines.append("但极度恐惧期间市场可能继续下跌，需控制单次决策暴露。")
    elif fg_val is not None and float(fg_val) > 75:
        lines.append("极度贪婪区间，市场过热，追高风险加大。")
        lines.append("此时市场定价通常隐含了过于乐观的预期，任何利空都可能引发较大回调。")
    elif fg_val is not None and float(fg_val) < 45:
        lines.append("情绪偏向恐惧，市场谨慎，但尚未到极端水平。")
    else:
        lines.append("情绪处于中性区间，未出现极端信号。")
    if si is not None:
        if si > 10:
            lines.append(f"空头比例 {si:.1f}% 较高——一旦出现利好，可能触发「轧空」行情（空头被迫平仓推高股价）。")
        elif si > 5:
            lines.append(f"空头比例 {si:.1f}% 适中，存在一定做空力量，但尚不构成轧空条件。")
    if pc is not None:
        if pc > 1.2:
            lines.append(f"Put/Call {pc:.2f}——看跌期权交易活跃，市场对冲需求增加，暗示防御心态。")
        elif pc < 0.7:
            lines.append(f"Put/Call {pc:.2f}——看涨期权占主导，市场情绪偏乐观。")
    if vix_struct:
        if "backwardation" in vix_struct.lower():
            lines.append("VIX 期限结构倒挂（近月高于远月），市场预期短期波动加剧——避险信号。")
        elif "contango" in vix_struct.lower():
            lines.append("VIX 期限结构正常（远月高于近月），市场未预期近期有重大风险事件。")
    lines.append("")
    return "\n".join(lines)


def _section_peer(comps: dict, peer) -> str:
    dim = comps.get("peer_comparison")
    if not dim:
        return ""

    raw_100 = raw_to_percentile(dim.get("score", 0))
    sig = _signal_text(raw_100)
    header = f"## 九、同行对比（Peer Comparison）\n\n得分：{raw_100}/100 | 权重：10% | 信号：{sig}\n"

    lines = [header]
    peers = dim.get("peer_tickers", [])
    comparisons = dim.get("comparisons", {})

    if peers:
        lines.append(f"同行：{', '.join(peers)}")
        lines.append("")

    if comparisons:
        lines.append("| 指标 | 本股 | 同行中位数 | 溢价/折价 | 含义 |")
        lines.append("|------|------|---------|----------|------|")
        for name, comp in comparisons.items():
            display = name.upper().replace("_", " ")
            gloss = GLOSSARY.get(name, "")
            short_gloss = gloss.split("：")[0] if gloss else display
            premium = comp.get("premium_pct", 0)
            judge = _judge_premium(premium)
            lines.append(
                f"| {display}（{short_gloss}） | {comp.get('stock', 'N/A')} "
                f"| {comp.get('peer_avg', 'N/A')} | {premium:+.1f}% | {judge} |"
            )
        lines.append("")
    # 同行对比解读
    if comparisons:
        premiums = [c.get("premium_pct", 0) for c in comparisons.values() if c.get("premium_pct") is not None]
        avg_prem = sum(premiums) / len(premiums) if premiums else 0
        lines.append("**解读**")
        if avg_prem > 50:
            lines.append("估值显著高于同行——市场认可其竞争优势，但需有持续增长支撑溢价。")
            lines.append("高溢价公司一旦增速放缓至行业平均水平，估值向同行靠拢可能意味着较大的下跌空间。")
        elif avg_prem < -20:
            lines.append("估值低于同行——可能是被低估的机会，也可能反映了基本面劣势。")
            lines.append("建议结合盈利能力和增长指标判断：如果基本面优于同行而估值更低，则是积极信号。")
        else:
            lines.append("估值与同行接近，市场定价相对公平。")
        # 各指标分解
        high_prem = [n for n, c in comparisons.items() if c.get("premium_pct", 0) > 50]
        low_prem = [n for n, c in comparisons.items() if c.get("premium_pct", 0) < -30]
        if high_prem:
            lines.append(f"溢价最高的指标：{', '.join(n.upper() for n in high_prem[:3])}——这些维度定价最为激进。")
        if low_prem:
            lines.append(f"折价最大的指标：{', '.join(n.upper() for n in low_prem[:3])}——可能存在被低估的维度。")
        lines.append("")
    return "\n".join(lines)


# ============================================================================
# 风险修正 + 投资建议 + 免责
# ============================================================================

def _risk_adjustments(comps: dict) -> str:
    timing = comps.get("earnings_timing")
    if not timing:
        return ""

    flag = timing.get("timing_flag", "")
    adj = timing.get("confidence_adjustment", 0)
    days = timing.get("days_until_earnings")

    if flag == "normal" and adj == 0:
        return ""

    lines = [
        "---", "",
        "## 风险修正", "",
        "| 类型 | 触发条件 | 动作 | 影响 |",
        "|------|---------|------|------|",
    ]
    if flag == "pre_earnings" and days is not None:
        lines.append(
            f"| 财报前期 | 距财报 {days} 天 | Constructive → Neutral | 状态降级 |"
        )
    if flag == "post_earnings":
        lines.append(
            f"| 财报后期 | 财报发布后 | 置信度 {adj:+.0%} | 置信度调整 |"
        )
    if adj < 0 and flag != "post_earnings":
        lines.append(
            f"| 时机修正 | 置信度调整 {adj:+.0%} | — | 降低确定性 |"
        )
    lines.append("")
    return "\n".join(lines)


def _investment_summary(signal, deep_valuation=None) -> str:
    bulls = [p for p in signal.supporting_points if p]
    bears = signal.caveats

    # 分离风险因素和数据局限
    data_kw = ["不足", "有限", "缺少", "缺乏", "变化", "维度", "lag", "old", "limited", "insufficient", "data"]
    risk_factors = [c for c in bears if not any(k in c for k in data_kw)]
    data_limits = [c for c in bears if any(k in c for k in data_kw)]

    lines = ["---", ""]

    # === 信号强度评估 ===
    weights = STOCK_WEIGHTS
    bullish, bearish, neutral = [], [], []
    for dim_key, dim_cn, w_key in DIMENSION_META:
        dim = signal.components.get(dim_key, {})
        raw = dim.get("score", 0)
        pct = raw_to_percentile(raw)
        if pct >= 65:
            bullish.append(dim_cn)
        elif pct < 35:
            bearish.append(dim_cn)
        else:
            neutral.append(dim_cn)
    total = len(bullish) + len(bearish) + len(neutral)
    bull_ratio = len(bullish) / total if total else 0

    lines.append("## 信号强度评估")
    lines.append("")
    lines.append(f"- 看多维度（{len(bullish)}/{total}）：{', '.join(bullish) if bullish else '无'}")
    lines.append(f"- 看空维度（{len(bearish)}/{total}）：{', '.join(bearish) if bearish else '无'}")
    lines.append(f"- 中性维度（{len(neutral)}/{total}）：{', '.join(neutral) if neutral else '无'}")
    if bull_ratio > 0.6:
        lines.append("- 信号强度：**强**——多数维度指向同一方向，信号一致性高")
    elif bull_ratio < 0.3:
        lines.append("- 信号强度：**偏空**——看空维度占多数，需警惕下行风险")
    else:
        lines.append("- 信号强度：**中性**——多空分歧较大，信号缺乏一致性")
    lines.append("")

    # === 操作策略建议 ===
    score = signal.score_100
    conf = signal.confidence
    rating = signal.rating

    lines.append("## 操作策略建议")
    lines.append("")
    if conf > 0.6:
        if score >= 65:
            lines.append("- **操作时机**：信号明确偏多，可分批建仓或加仓")
            lines.append("- **仓位管理**：高确信度 → 标准仓位（个人风险承受范围内的正常配置）")
        elif score < 35:
            lines.append("- **操作时机**：信号明确偏空，建议减仓或观望")
            lines.append("- **仓位管理**：高确信度看空 → 轻仓或清仓，等待趋势反转信号")
        else:
            lines.append("- **操作时机**：评分中性但确信度尚可，可小仓位试探")
            lines.append("- **仓位管理**：中等确信度 → 半仓位，预留加仓空间")
    elif conf > 0.3:
        lines.append("- **操作时机**：信号存在分歧，建议等待更多确认信号后再行动")
        lines.append("- **仓位管理**：中低确信度 → 减半仓位，严格设置止损")
    else:
        lines.append("- **操作时机**：信号严重冲突，不建议此时入场，建议观望")
        lines.append("- **仓位管理**：低确信度 → 暂不建仓，等待信号收敛后再评估")
    lines.append("- **风险控制**：无论任何评级，单一个股仓位建议不超过总投资组合的 10-15%")
    lines.append("")

    # === 投资建议（原有） ===
    lines.extend(["## 投资建议", ""])
    if bulls:
        lines.append("**看多因素**：")
        for i, p in enumerate(bulls, 1):
            lines.append(f"{i}. {p}")
        lines.append("")

    if risk_factors:
        lines.append("**风险因素**：")
        for i, c in enumerate(risk_factors, 1):
            lines.append(f"{i}. {c}")
        lines.append("")

    if data_limits:
        lines.append("**数据局限**：")
        for i, c in enumerate(data_limits, 1):
            lines.append(f"{i}. {c}")
        lines.append("")

    # 多空对照表
    if bulls or risk_factors:
        lines.append("**多空对照**：")
        lines.append("")
        lines.append("| 方向 | 关键论据 |")
        lines.append("|------|---------|")
        if bulls:
            lines.append(f"| 看多 | {bulls[0][:80]} |")
        if risk_factors:
            lines.append(f"| 风险 | {risk_factors[0][:80]} |")
        lines.append("")

    # 估值交叉校验（仅深度估值模式）
    if deep_valuation:
        dcf = getattr(deep_valuation, "dcf_value", None)
        analyst_data = signal.components.get("analyst_sentiment", {})
        analyst_target = analyst_data.get("price_target")
        if dcf and analyst_target:
            gap_pct = abs(analyst_target - dcf) / dcf * 100
            lines.append("**估值交叉校验**：")
            lines.append(f"- DCF 内在价值：${dcf:.2f}")
            lines.append(f"- 分析师目标价：${analyst_target:.2f}")
            lines.append(f"- 两者偏差：{gap_pct:.0f}%")
            if gap_pct > 30:
                lines.append("- 偏差较大，分析师目标价通常存在乐观偏差（历史平均高估 10-20%）")
            lines.append("")

    return "\n".join(lines)


def _risk_assessment(signal) -> str:
    """综合风险评估。"""
    lines = ["---", "", "## 综合风险评估", ""]
    risks = []

    # 从各维度收集风险信号
    comps = signal.components
    fund = comps.get("fundamentals", {})
    cr = fund.get("current_ratio")
    if cr is not None and cr < 1:
        risks.append(f"流动比率 {cr:.2f} < 1——短期偿债能力不足，若遇到现金流中断可能无法及时偿还债务")
    tech = comps.get("technical", {})
    rsi = tech.get("rsi_14d")
    if rsi and rsi > 70:
        risks.append(f"RSI {rsi:.0f} > 70——技术面超买，短期回调概率较大")
    sent = comps.get("sentiment_analysis", {})
    fg = sent.get("fear_greed")
    if fg and fg > 75:
        risks.append("恐惧贪婪指数 > 75——市场过度贪婪，系统性回调风险上升")
    sector = comps.get("sector_performance", {})
    rel = sector.get("relative_strength")
    if rel is not None and rel < -5:
        risks.append(f"相对板块强度 {rel:+.1f}pp——板块拖累明显，个股独立走强难度大")
    peer = comps.get("peer_comparison", {})
    comparisons = peer.get("comparisons", {})
    high_pe = comparisons.get("pe", {}).get("premium_pct", 0)
    if high_pe > 100:
        risks.append(f"P/E 溢价 {high_pe:.0f}%——估值显著高于同行，增速放缓时面临估值收缩风险")

    # 风险等级判定
    risk_count = len(risks)
    if risk_count >= 3:
        level = "高"
        desc = "多个维度同时发出风险信号，建议高度谨慎，轻仓或观望"
    elif risk_count >= 1:
        level = "中"
        desc = "存在局部风险，建议控制仓位，设置止损"
    else:
        level = "低"
        desc = "暂未发现明显风险信号，但市场环境随时可能变化"

    lines.append(f"**风险等级：{level}**——{desc}")
    lines.append("")
    if risks:
        lines.append("**风险清单**：")
        for i, r in enumerate(risks, 1):
            lines.append(f"{i}. {r}")
        lines.append("")
    else:
        lines.append("当前各维度未检测到显著风险信号。")
        lines.append("")
    return "\n".join(lines)


def _reading_guide() -> str:
    """读懂本报告指南（内容在 deep_report_guides 中维护）。"""
    from .deep_report_guides import reading_guide_comprehensive
    return reading_guide_comprehensive()


def _data_verification(signal) -> str:
    """动态数据验证状态章节。"""
    lines = ["---", "", "## 数据验证状态", ""]

    if not signal.verified_metrics:
        # 无验证数据时回退到静态说明
        lines.append("本报告数据来自 Yahoo Finance，不同指标的数据新鲜度不同：")
        lines.append("")
        lines.append("| 类别 | 指标示例 | 新鲜度 | 说明 |")
        lines.append("|------|---------|--------|------|")
        lines.append("| 实时 | 股价、成交量、VIX | 延迟 15-20 分钟 | 盘中实时更新 |")
        lines.append("| 延迟 | P/E、P/S、ROE、分析师评级 | 1-30 天 | 日末或财报发布后更新 |")
        lines.append("| 滞后 | FCF、空头比例、内幕交易 | 2-8 周 | 受 SEC/FINRA 报告周期限制 |")
        lines.append("")
        return "\n".join(lines)

    metrics = signal.verified_metrics
    total = len(metrics)
    confirmed = sum(1 for m in metrics.values() if m["status"] == "confirmed")
    minor = sum(1 for m in metrics.values() if m["status"] == "minor_gap")
    warning = sum(1 for m in metrics.values() if m["status"] == "warning")
    not_found = sum(1 for m in metrics.values() if m["status"] == "not_found")

    conf_pct = signal.verification_confidence * 100
    lines.append(
        f"**数据置信度：{conf_pct:.0f}%** — "
        f"已验证 {total} 项指标（{confirmed} 确认 / {minor} 轻度偏差 / {warning} 警告 / {not_found} 未找到）"
    )
    lines.append("")

    _METRIC_CN = {
        "revenue": "营收（TTM）", "eps": "每股盈利（EPS）",
        "fcf": "自由现金流（FCF）", "target_price": "分析师目标价",
        "pe_ratio": "市盈率（P/E）", "market_cap": "市值",
        "dividend_yield": "股息率",
    }
    _STATUS_CN = {
        "confirmed": "✅ 确认", "minor_gap": "🔶 轻度偏差",
        "warning": "⚠️ 警告", "not_found": "— 未找到",
    }

    lines.append("| 指标 | 本报告值 | 网络验证值 | 偏差 | 状态 |")
    lines.append("|------|---------|----------|------|------|")

    for key in ["revenue", "eps", "fcf", "target_price", "pe_ratio", "market_cap", "dividend_yield"]:
        m = metrics.get(key)
        if m is None:
            continue
        cn = _METRIC_CN.get(key, key)
        our = _fmt_verify_val(key, m.get("our_value"))
        web = _fmt_verify_val(key, m.get("web_value"))
        disc = f"{m['discrepancy_pct']:+.1f}%" if m.get("discrepancy_pct") is not None else "—"
        status = _STATUS_CN.get(m["status"], m["status"])
        lines.append(f"| {cn} | {our} | {web} | {disc} | {status} |")

    lines.append("")

    if signal.verification_warnings:
        lines.append("**验证警告**：")
        for w in signal.verification_warnings:
            lines.append(f"- {w}")
        lines.append("")

    lines.append(
        "> 验证来源：Brave Search 摘要提取。不同金融数据源天然存在 2-5% 差异，"
        "偏差 ≤10% 视为正常，10-20% 轻度偏差，>20% 触发警告。"
    )
    lines.append("")
    return "\n".join(lines)


def _fmt_verify_val(key: str, value) -> str:
    """格式化验证值。"""
    if value is None:
        return "—"
    if key in ("revenue", "fcf", "market_cap"):
        if abs(value) >= 1e12:
            return f"${value / 1e12:.2f}T"
        return f"${value / 1e9:.1f}B"
    if key in ("eps", "target_price"):
        return f"${value:.2f}"
    if key == "pe_ratio":
        return f"{value:.1f}x"
    if key == "dividend_yield":
        return f"{value:.2f}%"
    return str(value)


def _disclaimer() -> str:
    return (
        "---\n\n"
        "*免责声明：非投资建议，仅供参考。投资决策前请咨询持牌财务顾问。*\n"
        "*数据源：Yahoo Finance + Brave Search 交叉验证 | 版本：v13.0*\n"
    )


# ============================================================================
# 工具函数
# ============================================================================

def _annotate(key: str) -> str:
    """术语旁注式标注：名称（注释）。"""
    gloss = GLOSSARY.get(key)
    if not gloss:
        return key.upper()
    name = gloss.split("：")[0]
    desc = gloss[len(name) + 1:] if "：" in gloss else ""
    return f"{name}（{desc}）" if desc else name


def _signal_text(score_100: int) -> str:
    """百分制 → 中文信号词。"""
    if score_100 >= 80:
        return "强烈看多"
    if score_100 >= 65:
        return "看多"
    if score_100 >= 50:
        return "中性偏多"
    if score_100 >= 35:
        return "中性偏空"
    return "看空"


def _rating_cn(rating: str) -> str:
    """英文评级 → 中文。"""
    return {
        "Strong": "强势",
        "Constructive": "建设性",
        "Neutral": "中性",
        "Fragile": "脆弱",
        "High Risk": "高风险",
        "Strong Buy": "强势",
        "Buy": "建设性",
        "Hold": "中性",
        "Reduce": "脆弱",
        "Sell": "高风险",
    }.get(rating, rating)


def _confidence_cn(confidence: float) -> str:
    if confidence > 0.6:
        return "High"
    if confidence > 0.3:
        return "Medium"
    return "Low"


def _confidence_explain(confidence: float) -> str:
    """置信度原因解释。"""
    if confidence > 0.6:
        return "多维度信号一致，评分参考性强"
    if confidence > 0.3:
        return "部分维度存在分歧，建议结合深度报告辅助判断"
    return "多维度信号冲突，评分参考性有限，务必结合深度报告辅助判断"


def _fmt_cap(market_cap: float) -> str:
    """市值格式化。"""
    if market_cap >= 1e12:
        return f"${market_cap / 1e12:.2f}T"
    if market_cap >= 1e9:
        return f"${market_cap / 1e9:.1f}B"
    if market_cap >= 1e6:
        return f"${market_cap / 1e6:.0f}M"
    return f"${market_cap:,.0f}"


def _judge_premium(premium: float) -> str:
    """溢价/折价判定。"""
    if premium > 30:
        return "显著溢价"
    if premium > 10:
        return "小幅溢价"
    if premium > -10:
        return "接近均值"
    if premium > -30:
        return "小幅折价"
    return "显著折价"


def _metric_table(
    title: str,
    metrics: list[tuple[str, str, str | None, str]],
    dim: dict,
    sector: str = "",
) -> list[str]:
    """生成指标子表。"""
    lines = [f"### {title}", ""]
    lines.append("| 指标 | 值 | 含义 | 判定 |")
    lines.append("|------|-----|------|------|")

    has_data = False
    for display, key, prefix, suffix in metrics:
        val = dim.get(key)
        if val is None:
            continue
        has_data = True
        gloss = GLOSSARY.get(key, "")
        gloss_short = gloss if gloss else ""

        # 格式化值
        if key == "free_cashflow":
            val_str = _fmt_cap(val) if isinstance(val, (int, float)) else str(val)
        elif isinstance(val, float):
            val_str = f"{val:.2f}{suffix}"
        else:
            val_str = f"{val}{suffix}"

        judge = _judge_metric(key, val, sector)
        lines.append(f"| {display}（{gloss_short}） | {val_str} | — | {judge} |")

    if not has_data:
        return []

    lines.append("")
    return lines


def _judge_metric(key: str, value, sector: str = "") -> str:
    """指标判定（板块感知阈值）。"""
    if not isinstance(value, (int, float)):
        return "—"

    # 估值指标使用板块感知阈值
    thresholds = get_valuation_thresholds(sector)
    valuation_rules = {
        "pe_ratio": lambda v: "偏低（便宜）" if v < thresholds["pe"][0] else ("合理" if v < thresholds["pe"][1] else "偏高"),
        "peg_ratio": lambda v: "被低估" if v < thresholds["peg"][0] else ("合理" if v < thresholds["peg"][1] else "偏高"),
        "ps_ratio": lambda v: "便宜" if v < thresholds["ps"][0] else ("合理" if v < thresholds["ps"][1] else "偏高"),
        "pb_ratio": lambda v: "便宜" if v < thresholds["pb"][0] else ("合理" if v < thresholds["pb"][1] else "偏高"),
        "ev_ebitda": lambda v: "便宜" if v < thresholds["ev_ebitda"][0] else ("合理" if v < thresholds["ev_ebitda"][1] else "偏高"),
    }

    # 质量/健康指标使用通用阈值
    quality_rules = {
        "gross_margin": lambda v: "优秀" if v > 50 else ("良好" if v > 30 else "偏低"),
        "net_margin": lambda v: "优秀" if v > 20 else ("良好" if v > 10 else "偏低"),
        "roe": lambda v: "优秀" if v > 15 else ("良好" if v > 10 else "偏低"),
        "roa": lambda v: "优秀" if v > 10 else ("良好" if v > 5 else "偏低"),
        "current_ratio": lambda v: "安全" if v > 2 else ("正常" if v > 1 else "危险"),
        "debt_to_equity": lambda v: "健康" if v < 1 else ("正常" if v < 2 else "高风险"),
        "free_cashflow": lambda v: "正面" if v > 0 else "负面",
    }

    judge_fn = valuation_rules.get(key) or quality_rules.get(key)
    return judge_fn(value) if judge_fn else "—"
