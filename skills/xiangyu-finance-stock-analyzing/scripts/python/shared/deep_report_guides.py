"""
深度报告行动指引 v12 — 6 个领域的关键结论与行动建议。

每个 guide_*() 返回完整 Markdown：发现表 + 行动建议 + 操作策略 + 后续信号。
"""


# ============================================================================
# 估值
# ============================================================================

def guide_valuation(r, signal) -> str:
    """估值报告行动指引。"""
    findings = []
    entry, risk_ctrl, timeframe = "", "", ""
    watch = []

    # --- 发现 ---
    if r.safety_margin_pct is not None:
        m = r.safety_margin_pct
        verdict = "显著低估" if m > 30 else ("低估" if m > 10 else ("高估" if m < -20 else "估值合理"))
        findings.append((f"DCF 安全边际 {m:+.0f}%", verdict))
    if r.pe_range and r.pe_range.get("percentile") is not None:
        pct = r.pe_range["percentile"]
        findings.append((
            f"P/E 历史百分位 {pct}%",
            "处于历史高位，均值回归风险大" if pct > 80 else (
                "处于历史低位，估值修复空间大" if pct < 20 else "历史中位，估值中性"),
        ))
    if r.dcf_scenarios:
        conserv = next((s for s in r.dcf_scenarios if s["scenario"] == "conservative"), None)
        optim = next((s for s in r.dcf_scenarios if s["scenario"] == "optimistic"), None)
        if conserv:
            findings.append((
                f"保守情景 vs 现价 {conserv['vs_current']:+.1f}%",
                "保守假设仍被低估，安全边际充足" if conserv["vs_current"] > 0 else "保守假设下已高估，下行风险较大",
            ))
        if optim:
            findings.append((
                f"乐观情景 vs 现价 {optim['vs_current']:+.1f}%",
                f"最优情景潜在上涨 {optim['vs_current']:.0f}%",
            ))
    if r.industry_comparison:
        premiums = [c.get("premium", 0) for c in r.industry_comparison if c.get("premium") is not None]
        if premiums:
            avg_prem = sum(premiums) / len(premiums)
            findings.append((
                f"行业相对溢价 {avg_prem:+.0f}%",
                "显著溢价，需强增长支撑" if avg_prem > 30 else ("折价，可能被市场忽视" if avg_prem < -20 else "接近行业均值"),
            ))

    # --- 操作策略 ---
    margin = r.safety_margin_pct or 0
    if margin > 20:
        action = "估值显著低估，DCF 模型和历史百分位均支持买入，可分批建仓"
        entry = "当前价格已在安全边际内，可直接分批入场（建议 2-3 次）"
        risk_ctrl = f"止损设在 DCF 保守估值下方 5-10%"
        timeframe = "中长期持有（6-12 个月），等待估值修复"
    elif margin > 0:
        action = "估值略有低估空间，但安全边际有限，建议小仓位试探"
        entry = "等待短期技术面回调至支撑位附近再入场"
        risk_ctrl = "严格止损，亏损 8% 即退出"
        timeframe = "中期持有（3-6 个月）"
    elif margin < -20:
        action = "估值明显偏高，当前价格透支了较多增长预期，建议等待回调"
        entry = "不建议当前价位入场，等待 P/E 回落至历史中位线附近"
        risk_ctrl = "若已持有，可逐步减仓至总仓位的 30-50%"
        timeframe = "观望为主，至少等 1-2 个季度再评估"
    else:
        action = "估值合理，可结合其他维度综合决策"
        entry = "等待技术面或基本面给出更明确信号后择机入场"
        risk_ctrl = "标准止损 8-10%，不追高"
        timeframe = "短中期（1-3 个月），视信号调整"

    # --- 后续信号 ---
    watch.append("下一季度财报中的营收和利润率是否支撑当前估值")
    watch.append("同行估值倍数变化（行业系统性重估风险）")
    if r.pe_range and r.pe_range.get("percentile", 50) > 80:
        watch.append("P/E 是否开始从高位回落（均值回归启动信号）")

    return _build_guide(findings[:5], action, entry, risk_ctrl, timeframe, watch)


# ============================================================================
# 成长性
# ============================================================================

def guide_growth(r, signal) -> str:
    """成长性报告行动指引。"""
    findings = []
    entry, risk_ctrl, timeframe = "", "", ""
    watch = []

    # --- 发现 ---
    if r.rev_cagr_3y is not None:
        c3 = r.rev_cagr_3y
        grade = "高速成长（>20%）" if c3 > 20 else ("稳健增长（10-20%）" if c3 > 10 else "增速偏低（<10%）")
        findings.append((f"3 年营收 CAGR {c3}%", grade))
    if r.rev_cagr_5y is not None:
        c5 = r.rev_cagr_5y
        accel = "加速" if r.rev_cagr_3y and r.rev_cagr_3y > c5 else "减速"
        findings.append((f"5 年营收 CAGR {c5}%", f"3 年 vs 5 年：增速{accel}"))
    if r.growth_attitude:
        findings.append((f"增长态势：{r.growth_attitude}", "动能" + ("增强" if "加速" in r.growth_attitude else "减弱")))
    if r.peg_ratio is not None:
        peg = r.peg_ratio
        findings.append((
            f"PEG {peg:.2f}",
            "增长未被充分定价，性价比高" if peg < 1 else ("溢价过高，增长已被过度定价" if peg > 2 else "估值与增速基本匹配"),
        ))
    if r.growth_quality:
        fcf_cagr = r.growth_quality.get("fcf_cagr")
        if fcf_cagr is not None:
            findings.append((f"FCF CAGR {fcf_cagr}%", "现金流增长" + ("强劲" if fcf_cagr > 15 else "稳健")))
    # 回退
    if not findings:
        if r.analyst_forecasts:
            g = r.analyst_forecasts.get("eps_growth_pct")
            if g is not None:
                findings.append((f"EPS 增长预期 {g}%", "分析师前瞻"))
        if r.growth_rating:
            findings.append((f"综合评级 {r.growth_rating}", {
                "A": "高速成长", "B": "稳健增长", "C": "增长平淡", "D": "增长乏力",
            }.get(r.growth_rating, "—")))

    # --- 操作策略 ---
    rating = r.growth_rating or "C"
    peg = r.peg_ratio
    attitude = r.growth_attitude or ""
    if rating in ("A", "B") and peg and peg < 1.5:
        action = "高增长 + 低 PEG，成长性价比突出，适合成长型投资者配置"
        entry = "回调至 20 日均线附近入场，或财报超预期后追入"
        risk_ctrl = "止损设在前低下方 5%，保护利润用移动止盈"
        timeframe = "中长期持有（6-12 个月），享受增长带来的估值扩张"
    elif "减速" in attitude or "收缩" in attitude:
        action = "增长放缓信号明确，建议观察 1-2 季度是否触底回升"
        entry = "等待营收增速重新转正或 EPS 连续两季超预期后再考虑"
        risk_ctrl = "若已持有，止损收紧至 5%"
        timeframe = "短期观望（1-3 个月），等待拐点确认"
    else:
        action = "增长稳健，可作为成长型配置的候选"
        entry = "等待技术面给出明确买入信号"
        risk_ctrl = "标准止损 8-10%"
        timeframe = "中期持有（3-6 个月）"

    # --- 后续信号 ---
    watch.append("下季度营收增速是否延续或反转当前趋势")
    watch.append("分析师盈利预期修正方向（上调 = 正面催化）")
    if peg and peg > 2:
        watch.append("PEG 是否因增速提升而自然下降")

    return _build_guide(findings[:5], action, entry, risk_ctrl, timeframe, watch)


# ============================================================================
# 技术面
# ============================================================================

def guide_technical(r, signal) -> str:
    """技术面报告行动指引。"""
    findings = []
    entry, risk_ctrl, timeframe = "", "", ""
    watch = []

    # --- 发现 ---
    if r.overall_signal:
        findings.append((f"综合信号：{r.overall_signal}", f"{r.bullish_count}多 {r.bearish_count}空 {r.neutral_count}中"))
    if r.macd and r.macd.get("last_cross"):
        days = r.macd.get("cross_days_ago", "?")
        findings.append((f"MACD {r.macd['last_cross']}", f"{days} 天前交叉，信号{'新鲜' if isinstance(days, int) and days < 5 else '已老化'}"))
    if r.rsi and r.rsi.get("value"):
        v = r.rsi["value"]
        findings.append((f"RSI {v:.0f}", "超买区间，短期回调概率大" if v > 70 else (
            "超卖区间，反弹概率大" if v < 30 else "正常区间")))
    if r.support_resistance:
        sup = next((s for s in r.support_resistance if s.get("type") == "support"), None)
        res = next((s for s in r.support_resistance if s.get("type") == "resistance"), None)
        if sup and res:
            sp, rp = sup.get("price", 0), res.get("price", 0)
            findings.append((f"支撑 ${sp:.0f} / 阻力 ${rp:.0f}", "关键价位参考"))
    if r.volume_analysis:
        v_trend = r.volume_analysis.get("trend", "—")
        findings.append((f"成交量趋势：{v_trend}", "量价配合度参考"))

    # --- 操作策略 ---
    sig = r.overall_signal or ""
    if "偏多" in sig or "bullish" in sig.lower():
        action = "技术面偏多，短期做多信号明确，趋势与动量共振"
        entry = "回踩支撑位不破时入场，或突破阻力位后追入"
        risk_ctrl = f"止损设在支撑位下方 2-3%"
        timeframe = "短期交易（1-4 周），目标阻力位附近"
    elif "偏空" in sig or "bearish" in sig.lower():
        action = "技术面偏空，短期宜观望或轻仓，等待企稳信号"
        entry = "不建议此时入场做多，等待 RSI 进入超卖区或支撑位企稳"
        risk_ctrl = "若已持有，在支撑位下方 2% 设止损"
        timeframe = "观望为主（2-4 周），等待底部形态确认"
    else:
        action = "技术面中性，等待方向突破再行动"
        entry = "突破阻力位放量时做多，跌破支撑位时退出"
        risk_ctrl = "区间操作：支撑位买、阻力位卖，严格止损"
        timeframe = "短期区间操作（1-2 周）"

    # --- 后续信号 ---
    watch.append("MACD 柱状图方向变化（动量转换的先行指标）")
    watch.append("成交量是否配合价格突破（放量突破更有效）")
    if r.rsi and r.rsi.get("value", 50) > 65:
        watch.append("RSI 是否出现顶背离（价格新高但 RSI 未新高）")

    return _build_guide(findings[:5], action, entry, risk_ctrl, timeframe, watch)


# ============================================================================
# 基本面
# ============================================================================

def guide_fundamentals(r, signal) -> str:
    """基本面报告行动指引。"""
    findings = []
    entry, risk_ctrl, timeframe = "", "", ""
    watch = []

    # --- 发现 ---
    if r.health_rating:
        label = {"A": "优秀（财务稳健）", "B": "良好（整体健康）", "C": "中性（需关注）", "D": "有风险（警惕恶化）"}.get(r.health_rating, "—")
        findings.append((f"财务健康评级 {r.health_rating}", label))
    if r.dupont:
        driver = r.dupont.get("driver", "—")
        roe = r.dupont.get("roe", "N/A")
        findings.append((f"ROE {roe}%，驱动因素：{driver}", "利润驱动型更健康，杠杆驱动型需警惕"))
    if r.cashflow_trend:
        ratios = [c.get("ocf_ni_ratio") for c in r.cashflow_trend if c.get("ocf_ni_ratio") is not None]
        if ratios:
            avg = sum(ratios) / len(ratios)
            findings.append((f"OCF/NI 均值 {avg:.1f}x", "利润含金量" + ("高，盈利质量好" if avg > 1.2 else ("正常" if avg >= 0.8 else "低，警惕利润注水"))))
    if r.margin_trend:
        latest = r.margin_trend[-1] if r.margin_trend else {}
        gm = latest.get("gross_margin")
        nm = latest.get("net_margin")
        if gm and nm:
            findings.append((f"毛利率 {gm:.1f}% / 净利率 {nm:.1f}%", "定价权" + ("强" if gm > 40 else "一般")))
    if r.balance_trend:
        latest_bal = r.balance_trend[-1] if r.balance_trend else {}
        cr = latest_bal.get("current_ratio")
        if cr is not None:
            findings.append((f"流动比率 {cr:.2f}", "流动性" + ("充裕" if cr > 2 else ("正常" if cr >= 1 else "紧张，需关注短期偿债"))))

    # --- 操作策略 ---
    hr = r.health_rating or "C"
    if hr in ("A", "B"):
        action = "基本面稳健，财务风险低，适合作为核心持仓"
        entry = "回调至合理估值区间时入场"
        risk_ctrl = "基本面安全垫厚，止损可放宽至 10-12%"
        timeframe = "中长期持有（6-12 个月）"
    elif hr == "D":
        action = "基本面存在隐忧，财务指标恶化趋势明显，建议降低仓位或规避"
        entry = "不建议当前入场，等待财务指标连续 2 季度改善"
        risk_ctrl = "若已持有，收紧止损至 5%，做好止损准备"
        timeframe = "短期观望（等待基本面拐点）"
    else:
        action = "基本面中性，需结合估值和成长性综合判断"
        entry = "等待催化剂（财报超预期、毛利率回升等）"
        risk_ctrl = "标准止损 8-10%"
        timeframe = "中期（3-6 个月）"

    # --- 后续信号 ---
    watch.append("下季度毛利率和净利率变化趋势")
    watch.append("OCF/NI 比值是否维持在 1.0 以上（利润含金量）")
    if r.balance_trend and r.balance_trend[-1].get("current_ratio", 2) < 1:
        watch.append("流动比率是否进一步下滑（破产预警指标）")

    return _build_guide(findings[:5], action, entry, risk_ctrl, timeframe, watch)


# ============================================================================
# 同行对比
# ============================================================================

def guide_peers(r, signal) -> str:
    """同行对比报告行动指引。"""
    findings = []
    entry, risk_ctrl, timeframe = "", "", ""
    watch = []

    # --- 发现 ---
    if r.competitive_position:
        findings.append((f"竞争位置：{r.competitive_position}", "行业内相对排名"))
    if r.strengths and r.strengths != ["数据不足"]:
        findings.append(("核心优势", "、".join(r.strengths[:3])))
    if r.weaknesses and r.weaknesses != ["无明显劣势"]:
        findings.append(("主要劣势", "、".join(r.weaknesses[:3])))
    if r.rankings:
        top_ranks = [rk for rk in r.rankings if isinstance(rk, dict) and rk.get("rank") == 1]
        if top_ranks:
            findings.append(("排名第一的维度", "、".join(rk.get("dimension", "?") for rk in top_ranks[:3])))
        bottom_ranks = [rk for rk in r.rankings if isinstance(rk, dict) and isinstance(rk.get("rank"), int) and rk["rank"] >= 3]
        if bottom_ranks:
            findings.append(("排名靠后的维度", "、".join(rk.get("dimension", "?") for rk in bottom_ranks[:3])))

    # --- 操作策略 ---
    pos = r.competitive_position or ""
    if "领先" in pos:
        action = "行业领先，具备竞争壁垒，估值溢价有基本面支撑"
        entry = "作为行业配置首选，回调时优先买入"
        risk_ctrl = "行业龙头抗跌性强，止损可适当放宽"
        timeframe = "中长期持有（6-12 个月），享受行业领先红利"
    elif "落后" in pos:
        action = "竞争力有限，建议对比同行中更优标的，或等待基本面改善"
        entry = "不建议仅因估值便宜入场，需等到竞争力拐点"
        risk_ctrl = "严格止损 5-8%，落后者容易持续落后"
        timeframe = "短期观望，除非出现明确的转型信号"
    else:
        action = "行业中游，需关注是否有差异化突破口"
        entry = "寻找独立于行业的正面催化剂后再入场"
        risk_ctrl = "标准止损 8-10%"
        timeframe = "中期（3-6 个月）"

    # --- 后续信号 ---
    watch.append("同行估值倍数变化（板块整体重估信号）")
    watch.append("市场份额数据更新（竞争格局是否变化）")
    if r.weaknesses and "流动性" in str(r.weaknesses):
        watch.append("财务健康指标是否改善（劣势修复信号）")

    return _build_guide(findings[:5], action, entry, risk_ctrl, timeframe, watch)


# ============================================================================
# 股息
# ============================================================================

def guide_dividends(r, signal) -> str:
    """股息报告行动指引。"""
    if r.income_rating == "NO_DIVIDEND":
        return ""
    findings = []
    entry, risk_ctrl, timeframe = "", "", ""
    watch = []

    # --- 发现 ---
    if r.dividend_yield:
        y = r.dividend_yield
        findings.append((f"股息率 {y:.2f}%", "高收益" if y > 4 else ("中等收益" if y > 2 else "低收益")))
    if r.safety_score:
        label = {"EXCELLENT": "优秀，削减风险极低", "GOOD": "良好，安全性较高",
                 "MODERATE": "一般，需关注可持续性", "POOR": "堪忧，存在削减风险"}.get(r.income_rating, "—")
        findings.append((f"安全评分 {r.safety_score}/100", label))
    if r.consecutive_years:
        findings.append((
            f"连续加息 {r.consecutive_years} 年",
            "已达股息贵族标准（≥25 年），管理层高度承诺" if r.is_aristocrat else (
                f"接近贵族标准，差 {25 - r.consecutive_years} 年" if r.consecutive_years >= 20 else "稳定加息历史"),
        ))
    if r.cagr_5y is not None:
        findings.append((f"5 年股息 CAGR {r.cagr_5y:.1f}%", "增长" + ("强劲" if r.cagr_5y > 10 else ("稳健" if r.cagr_5y > 5 else "缓慢"))))
    if r.payout_ratio is not None:
        pr = r.payout_ratio
        findings.append((f"派息比率 {pr:.0f}%", "安全" if pr < 60 else ("偏高" if pr < 80 else "过高，可持续性存疑")))

    # --- 操作策略 ---
    rating = r.income_rating or "MODERATE"
    if rating == "EXCELLENT":
        action = "优质收入来源：高安全性 + 持续加息，适合作为收入型组合的核心持仓"
        entry = "股息率高于历史均值时入场更划算（相当于股价偏低）"
        risk_ctrl = "收入型投资关注股息是否削减，而非短期股价波动"
        timeframe = "长期持有（1-3 年+），复利再投资"
    elif rating == "GOOD":
        action = "收入投资候选，安全性良好，建议纳入收入型组合"
        entry = "下次除息日前 2-3 周内建仓，可立即享受分红"
        risk_ctrl = "关注派息比率趋势，若连续上升需提高警惕"
        timeframe = "中长期持有（6-12 个月+）"
    elif rating == "MODERATE":
        action = "股息可持续性存疑，不建议作为主要收入来源，可少量配置"
        entry = "等待下一次财报确认盈利能力后再决定"
        risk_ctrl = "派息比率 >80% 时警示，>100% 时考虑退出"
        timeframe = "短中期（3-6 个月），密切监控"
    else:
        action = "股息风险较高，不建议依赖其收入，以资本增值为主"
        entry = "不建议为股息入场，除非有明确的基本面反转信号"
        risk_ctrl = "做好股息被削减的心理准备"
        timeframe = "观望或轻仓"

    # --- 后续信号 ---
    watch.append("下季度财报中的自由现金流变化（股息安全性核心指标）")
    watch.append("管理层关于分红政策的最新指引")
    if r.payout_ratio and r.payout_ratio > 70:
        watch.append("派息比率是否继续攀升（削减前兆信号）")

    return _build_guide(findings[:5], action, entry, risk_ctrl, timeframe, watch)


# ============================================================================
# 通用指引模板
# ============================================================================

def _build_guide(
    findings: list[tuple[str, str]],
    action: str,
    entry: str = "",
    risk_ctrl: str = "",
    timeframe: str = "",
    watch: list[str] | None = None,
) -> str:
    """构建统一的行动指引板块（增强版）。"""
    lines = [
        "---", "",
        "## 关键结论与行动指引", "",
        "| # | 发现 | 意义 |",
        "|---|------|------|",
    ]
    for i, (finding, meaning) in enumerate(findings, 1):
        lines.append(f"| {i} | {finding} | {meaning} |")

    lines.extend(["", f"**行动建议**：{action}", ""])

    # 操作策略（增强）
    if entry or risk_ctrl or timeframe:
        lines.append("**操作策略**：")
        if entry:
            lines.append(f"- 入场条件：{entry}")
        if risk_ctrl:
            lines.append(f"- 风险控制：{risk_ctrl}")
        if timeframe:
            lines.append(f"- 时间框架：{timeframe}")
        lines.append("")

    # 后续信号
    if watch:
        lines.append("**需要关注的后续信号**：")
        for i, w in enumerate(watch, 1):
            lines.append(f"{i}. {w}")
        lines.append("")

    lines.extend([
        "> 以上结论基于历史数据和量化模型，不构成投资建议。",
        "",
    ])
    return "\n".join(lines) + "\n"


# ============================================================================
# 教育性知识卡片 — 帮零基础投资者理解每个深度报告的分析方法
# ============================================================================

def education_valuation() -> str:
    """估值报告知识卡片。"""
    return "\n".join([
        "---", "",
        "## 投资者知识卡片：估值分析", "",
        "### 什么是估值？", "",
        "估值是回答「这家公司到底值多少钱」的过程。股票价格是市场给出的标签，",
        "而内在价值是基于公司真实赚钱能力计算出的「合理价格」。当市场价格",
        "低于内在价值时，我们说股票「被低估」，反之为「被高估」。", "",
        "### 三种估值方法及其局限", "",
        "**1. DCF 现金流折现法（绝对估值）**",
        "- 原理：将公司未来所有能产生的自由现金流，按一定利率折算为今天的价值",
        "- 优点：最贴近「公司真实价值」的理论方法",
        "- 局限：对增长率和折现率假设极度敏感——改变 1% 的增长率，结果可能变化 20%+",
        "- 适用：成熟、现金流稳定的公司（科技龙头、消费品巨头等）", "",
        "**2. 历史估值法（相对自身）**",
        "- 原理：将当前的 P/E、P/S 等倍数与公司自己的历史数据对比",
        "- 优点：考虑了公司自身的估值波动规律",
        "- 局限：如果公司基本面发生质变（转型、并购等），历史数据可能失效",
        "- 核心指标：百分位（0%=历史最低，100%=历史最高）", "",
        "**3. 行业相对估值法（相对同行）**",
        "- 原理：将公司的估值倍数与同行业公司对比",
        "- 优点：考虑了行业周期和市场情绪的影响",
        "- 局限：如果整个行业被高估或低估，该方法会失效",
        "- 关键概念：溢价（比同行贵）和折价（比同行便宜）", "",
        "### 如何使用本报告", "",
        "1. 先看 DCF 安全边际：>20% 意味着有足够缓冲，<0% 需要更多增长支撑当前股价",
        "2. 再看历史百分位：如果 P/E 处于历史 80%+ 高位，即使 DCF 没有高估，也要警惕均值回归",
        "3. 最后看行业对比：高溢价需要有更高的增长或更强的竞争优势来支撑",
        "4. **三个维度交叉验证**：如果三种方法都指向同一结论，可信度更高", "",
    ]) + "\n"


def education_growth() -> str:
    """成长性报告知识卡片。"""
    return "\n".join([
        "---", "",
        "## 投资者知识卡片：成长性分析", "",
        "### 为什么要分析成长性？", "",
        "股票的长期回报最终由公司的利润增长驱动。一家公司如果能持续以 20% 的速度",
        "增长营收和利润，即使当前估值偏高，时间也会让它「长进」估值里。", "",
        "### 核心概念", "",
        "**CAGR（年化复合增长率）**",
        "- 将多年的增长平滑为每年均匀增速，消除了单年波动的干扰",
        "- 3 年 CAGR vs 5 年 CAGR：3 年更接近当下趋势，5 年反映长期能力",
        "- 如果 3 年 > 5 年，说明增速在加快；反之在减速", "",
        "**PEG（市盈增长比）**",
        "- 公式：P/E ÷ 盈利增速。PEG < 1 说明增长还没被充分定价",
        "- PEG 是 Peter Lynch 最推崇的指标之一——「用合理的价格买入高增长」",
        "- 局限：PEG 假设增长会持续，但没有公司能永远高增长", "",
        "**增长质量 vs 增长速度**",
        "- 营收增长容易通过降价、促销甚至并购实现——关键看利润是否同步增长",
        "- 高质量增长的标志：营收增长的同时毛利率稳定或提升",
        "- 警惕「增收不增利」——营收涨但净利润不涨，说明增长是低质量的", "",
        "### 如何使用本报告", "",
        "1. **看趋势方向**：营收 CAGR 是在加速还是减速？",
        "2. **看增长定价**：PEG < 1 是买入信号，PEG > 2 意味着增长已被充分定价",
        "3. **看增长质量**：FCF（自由现金流）增长是否跟上营收增长？利润率是否稳定？",
        "4. **看分析师预期**：EPS 增长预期反映市场共识，连续上调是强信号", "",
    ]) + "\n"


def education_technical() -> str:
    """技术面报告知识卡片。"""
    return "\n".join([
        "---", "",
        "## 投资者知识卡片：技术分析", "",
        "### 技术分析是什么？", "",
        "技术分析通过研究价格走势和成交量来预判未来价格方向。核心假设是",
        "「历史会重演」——市场参与者的心理和行为模式会在价格图上留下可识别的规律。", "",
        "### 核心工具解读", "",
        "**均线（MA）**",
        "- 短期均线（5/10/20 日）反映短期趋势，长期均线（50/200 日）反映长期趋势",
        "- 多头排列（短期在上）= 上升趋势健康；空头排列（短期在下）= 下降趋势主导",
        "- 「金叉」（短期上穿长期）通常是买入信号；「死叉」是卖出信号", "",
        "**MACD**",
        "- 由快线、慢线、柱状图三部分组成",
        "- 快线上穿慢线 = 金叉（看多）；反之 = 死叉（看空）",
        "- 柱状图由负转正 = 动能增强；由正转负 = 动能减弱",
        "- 重点关注「背离」：价格创新高但 MACD 未创新高 = 顶背离（卖出预警）", "",
        "**RSI（相对强弱指数）**",
        "- 0-100 的范围，>70 超买（可能回调），<30 超卖（可能反弹）",
        "- RSI 不是买卖信号，而是「概率倾斜」——超买区追高风险大，超卖区做空风险大",
        "- 强势股可以长时间维持在 60-80 区间而不回调", "",
        "**布林带**",
        "- 基于标准差构建的通道，带宽收窄预示变盘，扩张说明趋势进行中",
        "- 价格触上轨不一定卖，触下轨不一定买——要结合趋势方向判断", "",
        "### 如何使用本报告", "",
        "1. **先看趋势**：日线和周线趋势是否一致？一致性越高信号越可靠",
        "2. **再看动量**：MACD 和 RSI 是否支持趋势方向？",
        "3. **关注关键价位**：支撑位和阻力位是最重要的操作参考",
        "4. **成交量验证**：放量突破比缩量突破更可信", "",
    ]) + "\n"


def education_fundamentals() -> str:
    """基本面报告知识卡片。"""
    return "\n".join([
        "---", "",
        "## 投资者知识卡片：基本面分析", "",
        "### 基本面分析是什么？", "",
        "基本面分析是通过研究公司的财务报表来评估其真实经营状况。",
        "如果说技术分析是「看图」，基本面分析就是「看账本」。", "",
        "### 核心财务报表", "",
        "**利润表 → 公司赚不赚钱**",
        "- 毛利率：直接成本控制能力，反映定价权。>50% 说明有很强的定价能力",
        "- 净利率：最终利润占比。>20% 在大多数行业属于优秀水平",
        "- 趋势比绝对值更重要：毛利率连续 3 季度下降是危险信号", "",
        "**资产负债表 → 公司安不安全**",
        "- 流动比率（流动资产÷流动负债）：>2 很安全，<1 有短期偿债风险",
        "- 负债权益比：<1 健康，>2 高风险。高杠杆公司在经济下行时最脆弱",
        "- 现金储备：现金越多，越能扛过市场寒冬和抓住并购机会", "",
        "**现金流量表 → 公司有没有真金白银**",
        "- 经营现金流（OCF）：>净利润说明利润质量高（真金白银）",
        "- 自由现金流（FCF）：可用于分红、回购、还债的钱",
        "- 如果利润增长但 FCF 下降——警惕「纸面利润」，可能是会计手段美化了报表", "",
        "**杜邦分解 → ROE 为什么高**",
        "- ROE = 利润率 × 周转率 × 杠杆。三种驱动模式：",
        "  - 利润率驱动（最健康）：靠高毛利赚钱",
        "  - 周转率驱动（效率型）：靠薄利多销",
        "  - 杠杆驱动（风险型）：靠借债放大——经济好时漂亮，衰退时危险", "",
        "### 如何使用本报告", "",
        "1. **先看健康评级**：A/B 可以放心，C 需要关注，D 要警惕",
        "2. **关注利润趋势**：毛利率是否稳定？净利率是否在扩大？",
        "3. **检查现金流**：OCF/NI > 1 是基本要求，持续低于 0.8 是警告",
        "4. **理解 ROE 来源**：杠杆驱动的高 ROE 不如利润驱动可靠", "",
    ]) + "\n"


def education_peers() -> str:
    """同行对比报告知识卡片。"""
    return "\n".join([
        "---", "",
        "## 投资者知识卡片：同行对比分析", "",
        "### 为什么要对比同行？", "",
        "单看一家公司很难判断「好不好」——毛利率 30% 在零售业是优秀，",
        "在软件行业却是落后。通过与同行对比，才能看出一家公司的真实竞争力。", "",
        "### 对比维度", "",
        "**估值对比**：PE、PS、PB 比同行高多少？",
        "- 溢价 30%+ 意味着市场认为公司更优秀——但如果盈利和增长不领先，溢价可能不可持续",
        "- 折价 30%+ 可能是被市场忽视的机会，也可能是基本面有隐患", "",
        "**盈利能力对比**：毛利率、净利率、ROE 在同行中排第几？",
        "- 排名第一说明有定价权和效率优势",
        "- 持续落后意味着缺乏竞争壁垒", "",
        "**增长对比**：谁增长更快？",
        "- 营收增速领先 = 正在抢占市场份额",
        "- 增速落后 = 可能在失去竞争力", "",
        "**财务健康对比**：谁的资产负债表更安全？",
        "- 行业下行期，最先倒下的总是负债最高的公司",
        "- 财务健康排名是「抗风险能力」的直接体现", "",
        "### 理解「竞争位置」评级", "",
        "- **领先**：多个维度优于同行，具备差异化竞争优势",
        "- **中游**：表现中规中矩，需要寻找突破点",
        "- **落后**：竞争力不足，除非有明确转型计划否则不宜重仓", "",
        "### 如何使用本报告", "",
        "1. 先看竞争位置总评，了解公司在行业中的整体站位",
        "2. 关注优势和劣势的具体内容——优势要可持续，劣势要可改善",
        "3. 高估值溢价需要高增长或高盈利来支撑——否则存在收敛风险", "",
    ]) + "\n"


def education_dividends() -> str:
    """股息报告知识卡片。"""
    return "\n".join([
        "---", "",
        "## 投资者知识卡片：股息分析", "",
        "### 什么是股息投资？", "",
        "股息是公司将利润分配给股东的一种方式。股息投资策略追求",
        "稳定的现金收入，特别适合退休规划和保守型投资者。", "",
        "### 核心概念", "",
        "**股息率（Dividend Yield）**",
        "- 年度股息 ÷ 股价。越高说明每投入 1 元能获得更多分红",
        "- 陷阱：股息率过高（>8%）可能是因为股价暴跌导致，而非真正的高分红",
        "- 合理区间：2-5% 通常是健康的股息率范围", "",
        "**派息比率（Payout Ratio）**",
        "- 股息总额 ÷ 净利润。反映公司将多少利润分给了股东",
        "- <60% 安全：公司保留了足够利润用于再投资和应对风险",
        "- >80% 危险：几乎所有利润都拿去分红了，一旦利润下滑就可能削减股息",
        "- >100% 红色警报：公司在「吃老本」分红，长期不可持续", "",
        "**股息贵族（Dividend Aristocrat）**",
        "- 标普 500 成分股中连续 25 年以上每年加息的公司",
        "- 股息贵族的历史回报率优于市场平均——因为只有优秀公司才能做到 25 年持续加息",
        "- 不是所有高分红公司都好——要看分红是否有持续增长", "",
        "**FCF 覆盖倍数**",
        "- 自由现金流 ÷ 总派息金额。>2 意味着公司用来分红的钱还不到自由现金流的一半",
        "- 这是比派息比率更保守的安全指标——因为自由现金流排除了会计调整的影响", "",
        "### 如何使用本报告", "",
        "1. **先看安全评分**：低于 50 分的股息存在被削减的风险",
        "2. **检查派息比率**：持续上升意味着分红增长来自「压缩自身空间」而非利润增长",
        "3. **看增长历史**：连续加息 10 年以上的公司，管理层对分红有较强承诺",
        "4. **对比股息率与增长**：高股息率 + 低增长 = 纯收入；低股息率 + 高增长 = 未来回报更大", "",
    ]) + "\n"


# ============================================================================
# 综合报告新手指南
# ============================================================================

def reading_guide_comprehensive() -> str:
    """综合报告的阅读指南和教育内容。"""
    return "\n".join([
        "---", "",
        "## 新手指南：如何读懂这份报告", "",
        "### 评分系统", "",
        "本报告的核心是一个 **0-100 分** 的综合评分系统，整合了 9 个独立维度的分析。",
        "每个维度独立打分后，按照预设权重加权平均。权重反映了各维度对股价的影响力：",
        "基本面权重最高（20%），因为长期来看公司业绩是股价的根本驱动力。", "",
        "| 评分范围 | 评级 | 建议动作 |",
        "|---------|------|---------|",
        "| 80-100 | 强烈买入 | 多维度共振看多，可积极建仓 |",
        "| 65-79 | 买入 | 整体偏正面，适合分批入场 |",
        "| 50-64 | 持有 | 多空分歧大，不急于行动 |",
        "| 35-49 | 减持 | 偏负面信号，考虑减仓 |",
        "| 0-34 | 卖出 | 多项警告，建议规避 |", "",
        "### 置信度", "",
        "评分之外还有一个「置信度」指标——它衡量各维度之间是否方向一致。",
        "如果 8 个维度都看多、1 个看空，置信度很高（信号一致）。",
        "如果 4 个看多、4 个看空，置信度很低（信号冲突）。", "",
        "**低置信度时，评分本身的参考价值下降**——建议看深度报告做进一步分析。", "",
        "### 九大维度速查", "",
        "| 维度 | 回答的问题 | 数据来源 | 适合新手关注 |",
        "|------|-----------|---------|------------|",
        "| 盈利惊喜 | 公司比预期赚得多还是少？ | 财报 EPS | ★★★ |",
        "| 基本面 | 公司值这个价吗？赚钱能力怎样？ | 财务报表 | ★★★ |",
        "| 分析师 | 专业人士怎么看？目标价多少？ | 华尔街研报 | ★★☆ |",
        "| 历史表现 | 过去的财报反应有什么规律？ | 过往财报 | ★☆☆ |",
        "| 市场环境 | 大盘和 VIX 对个股有什么影响？ | 指数/VIX | ★★☆ |",
        "| 板块强度 | 整个行业在涨还是跌？ | 板块 ETF | ★★☆ |",
        "| 技术分析 | 股价趋势和动量如何？ | 价格/成交量 | ★★☆ |",
        "| 市场情绪 | 市场参与者的情绪和押注方向？ | 期权/空头 | ★☆☆ |",
        "| 同行对比 | 跟竞争对手比表现怎样？ | 同行数据 | ★★★ |", "",
        "### 数据源与时效性", "",
        "- 所有数据来自 Yahoo Finance，延迟 15-20 分钟",
        "- 空头数据来自 FINRA，延迟约 2 周",
        "- 本报告是某一时刻的快照，市场条件随时变化",
        "- 美股交易时间：东部时间 9:30-16:00（北京时间 21:30-次日 4:00）", "",
        "### 常见投资陷阱", "",
        "1. **追涨杀跌**：看到涨就买、跌就卖——应该反过来思考",
        "2. **只看单一指标**：P/E 低不等于便宜——可能是公司有问题",
        "3. **忽略止损**：每笔交易前都应该设好止损，否则小亏变大亏",
        "4. **过度交易**：频繁买卖会被手续费和税费侵蚀利润",
        "5. **情绪化决策**：恐惧和贪婪是投资最大的敌人", "",
        "### 重要提醒", "",
        "1. **永远不要基于单一信号做决策**——综合多个维度交叉验证",
        "2. **控制仓位**——单一个股不超过投资组合的 10-15%",
        "3. **设置止损**——在买入前就决定好最大可接受亏损",
        "4. **本报告不构成投资建议**——任何投资决策前请咨询持牌财务顾问", "",
    ]) + "\n"
