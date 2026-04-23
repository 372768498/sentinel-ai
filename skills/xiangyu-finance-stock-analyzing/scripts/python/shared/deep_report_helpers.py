"""
深度报告辅助模块 v12 — 术语库 + 解读引擎 + 通用格式化。
"""

from datetime import datetime

from .report_formatter import GLOSSARY


# ============================================================================
# 深度报告专有术语
# ============================================================================

DEEP_GLOSSARY: dict[str, str] = {
    "dcf": "现金流折现：用未来现金流倒推今天的内在价值",
    "wacc": "加权平均资本成本：公司融资的综合利率，越低越好",
    "safety_margin": "安全边际：内在价值超出股价的比例，越高越安全",
    "terminal_value": "终值：5 年后所有未来现金流的折现总和",
    "cagr": "年化复合增长率：平滑后的年均增速",
    "peg": "市盈增长比：P/E ÷ 增速，<1 说明增速没被充分定价",
    "yoy": "同比增长：与去年同期对比的变化率",
    "qoq": "环比增长：与上一季度对比的变化率",
    "ma_alignment": "均线排列：多条均线的排序方式，反映趋势强度",
    "macd_cross": "MACD 交叉：金叉看多，死叉看空",
    "rsi_14": "RSI-14：14 日相对强弱指数，>70 超买 <30 超卖",
    "bollinger_pctb": "%B：价格在布林带中的位置，0=下轨 100=上轨",
    "bandwidth": "带宽：布林带上下轨距离，收窄预示变盘",
    "atr": "平均真实波幅：衡量每日价格波动的绝对幅度",
    "volume_ratio": "量比：近期成交量 vs 均量，>1.3 放量 <0.7 缩量",
    "dupont": "杜邦分解：将 ROE 拆解为利润率×周转率×杠杆",
    "current_ratio": "流动比率：流动资产÷流动负债，>2 安全",
    "de_ratio": "负债权益比：总负债÷股东权益，<1 健康",
    "ocf_ni": "OCF/NI：经营现金流÷净利润，>1 说明利润含金量高",
    "payout_ratio": "派息比率：股息÷每股盈利，<60% 可持续",
    "fcf_coverage": "FCF 覆盖倍数：自由现金流÷总派息，>2 安全",
    "dividend_aristocrat": "股息贵族：连续 25 年以上每年加息的公司",
}

_GLOSSARY = {**GLOSSARY, **DEEP_GLOSSARY}


# ============================================================================
# 基础工具
# ============================================================================

def deep_annotate(key: str) -> str:
    """从合并术语库取括号注释。"""
    gloss = _GLOSSARY.get(key)
    if not gloss:
        return key
    name = gloss.split("：")[0]
    desc = gloss[len(name) + 1:] if "：" in gloss else ""
    return f"{name}（{desc}）" if desc else name


def interpret(text: str) -> str:
    """生成单段 blockquote 解读。"""
    return f"> **数据解读**：{text}\n"


def rich(main: str, *extras: str) -> str:
    """生成多段落 blockquote 解读，每个参数一段。"""
    parts = [f"> **数据解读**：{main}"]
    for e in extras:
        parts.append(f">\n> {e}")
    return "\n".join(parts) + "\n"


def one_liner(text: str) -> str:
    """生成一句话总结。"""
    return f"**一句话总结**：{text}\n"


def ts() -> str:
    """时间戳。"""
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def fmt_num(val, prefix: str = "", suffix: str = "", fmt: str = ",.0f") -> str:
    """格式化数字。"""
    if val is None:
        return "N/A"
    if isinstance(val, (int, float)):
        return f"{prefix}{val:{fmt}}{suffix}"
    return str(val)


def fmt_money(val) -> str:
    """格式化金额（T/B/M 三档）。"""
    if val is None:
        return "N/A"
    if abs(val) >= 1e12:
        return f"${val / 1e12:,.2f}T"
    if abs(val) >= 1e9:
        return f"${val / 1e9:,.1f}B"
    if abs(val) >= 1e6:
        return f"${val / 1e6:,.0f}M"
    return f"${val:,.2f}"


def disclaimer() -> str:
    """免责声明尾部。"""
    return (
        "---\n\n"
        "*免责声明：非投资建议，仅供参考。投资决策前请咨询持牌财务顾问。*\n"
        "*数据源：Yahoo Finance | 版本：v12*\n"
    )


# ============================================================================
# 估值解读引擎
# ============================================================================

def interp_dcf_oneliner(margin_pct):
    """DCF 一句话总结（替代 _format_valuation 中的一句话逻辑）。"""
    if margin_pct is None:
        return one_liner("DCF 数据不足，无法给出估值结论。")
    if margin_pct > 20:
        return one_liner(
            f"DCF 模型显示股价低于内在价值 {margin_pct:.0f}%，存在安全边际，估值具有吸引力。"
            f"安全边际超过 20% 意味着即使模型假设偏乐观，股价仍有缓冲空间。"
        )
    if margin_pct > 0:
        return one_liner(
            f"股价略低于内在价值 {margin_pct:.0f}%，估值基本合理但安全边际有限。"
            "建议等待更大折扣或结合其他维度确认。"
        )
    return one_liner(
        f"股价高于内在价值 {abs(margin_pct):.0f}%，当前估值偏贵。"
        "市场可能已透支增长预期，追高需谨慎。"
    )


def interp_wacc(wacc):
    """WACC 解读。"""
    if wacc > 12:
        return rich(
            f"WACC {wacc}% 偏高，说明市场认为该公司风险较大（高 Beta 或高负债），未来现金流折现后价值缩水更多。",
            "高 WACC 会显著压低 DCF 估值——如果利率环境转向宽松，WACC 可能下降，届时估值将获得上修空间。",
        )
    if wacc >= 8:
        return rich(
            f"WACC {wacc}% 处于正常范围，资金成本适中，DCF 模型的折现幅度合理。",
            "当前利率环境下该水平属于行业常态。若美联储加息，WACC 上升将压低 DCF 估值，反之亦然。",
        )
    return rich(
        f"WACC {wacc}% 偏低，说明公司风险较低或融资结构优化，有利于提升 DCF 估值。",
        "低 WACC 公司的 DCF 估值对增长率假设更敏感——微小的增长率变化会带来较大的估值波动。",
    )


def interp_fcf_projection(fcf_ttm):
    """FCF 预测解读。"""
    if fcf_ttm and fcf_ttm > 0:
        return rich(
            f"公司 TTM 自由现金流 {fmt_money(fcf_ttm)}，能持续产生现金，DCF 模型有坚实基础。",
            "正的自由现金流意味着公司在满足资本支出后仍有盈余——这是估值模型可靠性的基本前提。"
            "FCF 越稳定，DCF 估值的置信度越高。",
        )
    return rich(
        "当前自由现金流为负，DCF 模型的可靠性降低——公司尚未实现稳定造血。",
        "对于 FCF 为负的公司，DCF 估值高度依赖对未来转正时间点的假设，实际结果可能大幅偏离。"
        "建议更多参考相对估值法（P/S、EV/Revenue）。",
    )


def interp_dcf_scenarios(optimistic, conservative):
    """DCF 三情景解读。"""
    if not optimistic or not conservative:
        return interpret("情景数据不完整，无法进行交叉验证。")
    if conservative["vs_current"] > 0:
        return rich(
            "即使在保守假设下股价仍被低估，安全边际充足，估值具有较强吸引力。",
            f"保守情景（增长率最低）给出的内在价值仍高于现价 {conservative['vs_current']:+.1f}%，"
            "说明当前价格已充分反映了下行风险。",
            "这种「保守也不亏」的格局在实战中比较稀缺，通常意味着市场可能忽略了某些正面因素。",
        )
    if optimistic["vs_current"] < 0:
        return rich(
            "即使在乐观假设下股价仍被高估，当前价格透支了未来增长预期。",
            f"乐观情景（增长率最高）给出的内在价值仍低于现价 {optimistic['vs_current']:+.1f}%，"
            "说明市场定价隐含了极其乐观的增长假设。",
            "建议等待估值回归合理区间再考虑介入，或转向其他更具安全边际的标的。",
        )
    return rich(
        "三种情景结果分化，估值合理性取决于未来增长能否达到基准预期。",
        "保守情景偏低估、乐观情景偏高估——当前价格处于合理区间内。"
        "关键变量是未来 3-5 年的实际增长率，建议密切跟踪季度财报验证增长轨迹。",
    )


def interp_pe_percentile(label, pct):
    """P/E 或 P/S 历史百分位解读。"""
    if pct > 80:
        return rich(
            f"当前 {label} 处于历史 {pct}% 分位，接近历史高位——市场给了很高的估值溢价。",
            "历史高位估值通常有两种含义：市场极度看好未来增长，或者估值泡沫正在形成。"
            "均值回归的概率随着百分位升高而增大，需警惕估值收缩风险。",
        )
    if pct >= 40:
        return rich(
            f"当前 {label} 处于历史 {pct}% 分位，估值水平适中。",
            "处于历史中位区间意味着市场定价既不过度乐观也不过度悲观。"
            "这个位置通常不构成明确的买入或卖出信号，需结合基本面趋势做判断。",
        )
    return rich(
        f"当前 {label} 处于历史 {pct}% 分位，估值处于低位区间，可能存在被低估的机会。",
        "历史低位估值可能意味着：市场过度悲观（买入机会），或者基本面确实在恶化（价值陷阱）。"
        "建议检查盈利趋势是否稳定——如果盈利在增长而估值在低位，则是积极信号。",
    )


def interp_industry_relative(avg_prem):
    """行业相对估值解读。"""
    if avg_prem > 50:
        return rich(
            "相对行业大幅溢价，说明市场给予该公司显著的竞争力加成——但也需警惕溢价过度。",
            f"平均溢价 {avg_prem:.0f}% 意味着市场认为公司具备行业领先的增长潜力或护城河。"
            "高溢价的持续性取决于公司能否持续交出超越同行的业绩——一旦增速放缓，估值收敛风险较大。",
        )
    if avg_prem > -30:
        return rich(
            "估值水平与行业接近，市场定价基本合理。",
            "与行业均值的偏差在合理范围内，说明市场对公司的定价没有明显偏差。"
            "如果公司基本面优于行业平均，当前估值可能存在低估机会。",
        )
    return rich(
        "相对行业显著折价，可能是被低估的机会，也可能反映了市场对公司前景的担忧。",
        f"平均折价 {abs(avg_prem):.0f}% 需要深入分析原因——是暂时性的市场情绪偏差，还是基本面确实落后于同行。"
        "如果盈利能力和增长指标与同行持平或更优，则折价更可能是买入机会。",
    )


def interp_valuation_synthesis(verdict, margin_pct, pe_pct=None):
    """估值综合结论。"""
    parts = [f"**综合估值判定：{verdict or '数据不足'}**"]
    if margin_pct is not None:
        if margin_pct > 20:
            parts.append(f"DCF 安全边际 {margin_pct:.0f}%，估值具有吸引力。")
        elif margin_pct > 0:
            parts.append(f"DCF 安全边际 {margin_pct:.0f}%，估值基本合理。")
        else:
            parts.append(f"DCF 显示高估 {abs(margin_pct):.0f}%，估值偏贵。")
    if pe_pct is not None:
        if pe_pct > 80:
            parts.append(f"P/E 处于历史 {pe_pct}% 高位，估值收缩风险较大。")
        elif pe_pct < 20:
            parts.append(f"P/E 处于历史 {pe_pct}% 低位，可能存在被低估。")
    return "\n".join(parts) + "\n"


# ============================================================================
# 成长性解读引擎
# ============================================================================

def interp_revenue_quarterly(yoys):
    """季度营收同比趋势解读。"""
    if not yoys:
        return ""
    if all(y > 0 for y in yoys) and len(yoys) >= 3 and yoys[-1] > yoys[-2]:
        return rich(
            "季度营收同比持续正增长且增速递增——增长动能在加速。",
            "加速增长是最理想的成长形态，意味着公司正在扩大市场份额或进入新增长曲线。"
            "这种趋势通常伴随着估值溢价的扩张。",
        )
    if all(y > 0 for y in yoys):
        return rich(
            "季度营收同比均为正增长，但增速趋于平稳或放缓——增长仍在但动能减弱。",
            "增速放缓是成熟公司的常态，关键看放缓的幅度是否超出市场预期。"
            "如果当前估值隐含了高增长假设，增速放缓可能触发估值下修。",
        )
    return rich(
        "近期出现同比负增长季度，需关注是季节性波动还是趋势性下滑。",
        "单季度负增长不一定是坏信号（可能受节假日或基数效应影响），"
        "但连续两个季度负增长则需要警惕——可能反映需求疲软或竞争加剧。",
    )


def interp_cagr(cagr, rev_3y, rev_5y):
    """CAGR 解读。"""
    acc = ""
    if rev_3y is not None and rev_5y is not None:
        acc = "，且近 3 年快于 5 年——增长在加速" if rev_3y > rev_5y else "，但近 3 年慢于 5 年——增长在减速"
    if cagr > 20:
        return rich(
            f"营收增长 {cagr}%，属于高速成长{acc}。",
            "年化 20%+ 的增速在成熟市场中属于顶尖水平。"
            "高增长通常能支撑较高的估值溢价，但投资者需关注增速能否持续——"
            "历史上超过一半的高增长公司在 3-5 年内会回归到行业均值。",
        )
    if cagr > 10:
        return rich(
            f"营收增长 {cagr}%，增长稳健{acc}。",
            "10-20% 的年化增速在多数行业中属于中上水平，兼具增长性和稳定性。"
            "这个增速通常能跑赢通胀和 GDP 增长，是长期投资者比较理想的持仓选择。",
        )
    if cagr > 0:
        return rich(
            f"营收增长 {cagr}%，增速偏低{acc}。",
            "个位数增长可能意味着公司已进入成熟期，或面临市场饱和。"
            "低增长公司需要靠利润率改善或资本回报（回购/分红）来创造股东价值。",
        )
    return rich(
        f"营收增长 {cagr}%，处于收缩阶段{acc}。",
        "负增长是明确的警告信号——收入在缩水，可能面临市场萎缩或份额流失。"
        "除非有明确的触底回升迹象，否则建议谨慎对待。",
    )


def interp_eps_surprise(beats, total):
    """EPS 超预期连续性解读。"""
    if beats == total and total >= 4:
        return rich(
            f"近 {total} 个季度全部超预期——盈利能力持续超出市场预判，管理层执行力强。",
            "全胜记录说明管理层在指引时偏保守，实际运营能力超出承诺。"
            "这种模式下，分析师往往会逐步上调预期，形成「预期上修→股价上涨→再上修」的正循环。",
        )
    if beats >= total * 0.75:
        return rich(
            f"近 {total} 季中 {beats} 次超预期——大多数季度表现优于预期，偶有波动。",
            "超预期率 75%+ 在市场中属于优秀水平。偶尔的不及预期可能是季节性因素或一次性费用。"
            "关键看不及预期时的幅度和市场反应——小幅不及预期且股价不跌，说明市场信心依然稳固。",
        )
    return rich(
        f"近 {total} 季仅 {beats} 次超预期——盈利可预测性较低，需警惕业绩不达预期的风险。",
        "低超预期率意味着公司盈利波动较大，或者分析师预期模型难以准确捕捉公司运营节奏。"
        "对于可预测性差的公司，市场通常会给予较低的估值倍数作为风险补偿。",
    )


def interp_margin_trend_growth(margins, label="净利率"):
    """利润率趋势解读（成长性报告用）。"""
    if len(margins) < 2:
        return ""
    diff = margins[-1] - margins[0]
    if diff > 2:
        return rich(
            f"{label}从 {margins[0]}% 升至 {margins[-1]}%（+{diff:.1f}pp），盈利效率在改善。",
            f"{label}上升意味着公司在收入增长的同时控制住了成本，或者产品组合向高利润率品类转移。"
            "利润率改善叠加收入增长，是盈利增速的「双引擎」——每一元收入创造更多利润。",
        )
    if diff < -2:
        return rich(
            f"{label}从 {margins[0]}% 降至 {margins[-1]}%（{diff:.1f}pp），盈利效率承压。",
            "利润率下降需要区分原因：研发/营销投入增加（短期牺牲利润换增长）还是成本失控。"
            "如果是主动投入，关注是否在未来 2-3 个季度转化为收入增长；如果是被动承压，则需警惕。",
        )
    return rich(
        f"{label}在 {margins[-1]}% 附近波动，盈利结构稳定。",
        "稳定的利润率说明公司在成本管理方面有较好的纪律性，收入增长能直接转化为利润增长。",
    )


def interp_analyst_forecast(eps_g):
    """分析师前瞻预测解读。"""
    if eps_g is None:
        return ""
    if eps_g > 20:
        return rich(
            f"分析师预期 EPS 增长 {eps_g}%，市场对增长抱有很高期待。",
            "高增长预期是把双刃剑——如果实现，股价可能进一步上涨；但高预期也意味着高「失望风险」。"
            "实际 EPS 如果略低于这一预期，股价可能出现较大回调。建议关注财报前的预期修正方向。",
        )
    if eps_g > 0:
        return rich(
            f"分析师预期 EPS 温和增长 {eps_g}%，预期稳健。",
            "温和的增长预期意味着市场已经充分消化了可见的增长因素。"
            "超预期的概率取决于公司是否有尚未被市场定价的增长催化剂。",
        )
    return rich(
        f"分析师预期 EPS 下降 {eps_g}%，盈利面临下行压力。",
        "负增长预期意味着分析师集体认为公司盈利能力在恶化。"
        "但值得注意的是，过度悲观的一致预期有时反而提供了「低预期→超预期」的反转机会。",
    )


def interp_peg(peg):
    """PEG 增强解读。"""
    if peg < 0.5:
        return rich(
            f"PEG {peg:.2f} 极低，增长潜力远未被股价充分定价——典型的被低估信号。",
            "PEG < 0.5 意味着以当前估值买入，每 1% 的增长只需支付不到 0.5 倍的 P/E 溢价。"
            "如果增长能持续，这一估值水平具有很强的安全边际。但需确认增长数据的可靠性。",
        )
    if peg < 1:
        return rich(
            f"PEG {peg:.2f} 低于 1，增长速度快于估值水平——仍具性价比。",
            "PEG < 1 被彼得·林奇视为成长股的理想买入区间。"
            "当前估值尚未完全反映增长潜力，如果增速能维持，估值有上修空间。",
        )
    if peg < 1.5:
        return rich(
            f"PEG {peg:.2f} 在合理区间，估值与增速基本匹配。",
            "PEG 1-1.5 意味着市场给予了与增速匹配的估值——既不便宜也不贵。"
            "在这个区间，股价的走势主要取决于增速能否达到或超过预期。",
        )
    if peg < 2:
        return rich(
            f"PEG {peg:.2f} 偏高，市场已提前消化了部分增长预期。",
            "较高的 PEG 意味着投资者为增长支付了溢价。"
            "如果实际增速略低于预期，估值可能面临双杀（增速下降 + 估值倍数收缩）。",
        )
    return rich(
        f"PEG {peg:.2f} 显著偏高，增长溢价过大——除非增速能超预期加速，否则估值难以维持。",
        "PEG > 2 通常出现在市场对公司有极端乐观预期的时期。"
        "历史经验表明，高 PEG 公司的股价在增速放缓时回调幅度往往较大。谨慎追高。",
    )


def interp_growth_quality(rev_c, fcf_c):
    """增长质量解读。"""
    if rev_c is None or fcf_c is None:
        return ""
    if fcf_c >= rev_c:
        return rich(
            "自由现金流增速 ≥ 营收增速——增长质量优秀，利润能转化为真金白银。",
            "FCF 增长快于收入增长，说明公司不仅在扩大规模，还在提升经营效率。"
            "这类公司有更强的回购、分红和抗周期能力——是最理想的成长投资标的。",
        )
    if fcf_c > 0:
        return rich(
            "自由现金流增长为正但慢于营收——增长消耗了部分现金，仍在可接受范围。",
            "FCF 增速低于收入增速，说明增长需要额外的资本投入（研发、产能扩张等）。"
            "这在高速成长期是正常现象，关键看投入能否在未来转化为更高的 FCF。",
        )
    return rich(
        "自由现金流增速为负——增长依赖大量资本投入，盈利质量需警惕。",
        "FCF 下降意味着公司在「烧钱换增长」，这种模式对融资环境高度敏感。"
        "如果利率上升或融资渠道收紧，增长可能难以为继。建议重点关注 FCF 何时转正。",
    )


def interp_growth_synthesis(rating, attitude):
    """成长性综合评级解读。"""
    desc = {"A": "高速成长", "B": "稳健增长", "C": "增长平淡", "D": "增长乏力"}.get(rating, "—")
    if rating in ("A", "B"):
        return rich(
            f"综合评级 {rating}（{desc}），增长态势{attitude or '待观察'}——成长性指标整体积极。",
            "评级 A/B 意味着营收增速、盈利趋势和增长质量多数表现良好。"
            "适合成长型投资者作为核心持仓候选，但仍需关注估值是否合理。",
        )
    if rating == "C":
        return rich(
            f"综合评级 {rating}（{desc}），增长态势{attitude or '待观察'}——增长动能不足。",
            "C 级评级意味着增长指标平平，既无明显亮点也无严重隐忧。"
            "这类公司更适合作为价值/收入型投资标的，而非成长型配置。",
        )
    return rich(
        f"综合评级 {rating}（{desc}），增长态势{attitude or '待观察'}——增长面临挑战。",
        "D 级评级反映出增长的多个维度出现问题。"
        "建议谨慎对待，除非有明确的转型/触底催化剂。",
    )


# ============================================================================
# 技术面解读引擎
# ============================================================================

def interp_ma_alignment(align):
    """均线排列解读。"""
    if "多头" in align:
        return rich(
            "均线呈多头排列（短期>中期>长期），趋势向上，适合顺势做多。",
            "多头排列是最健康的上升趋势形态——每次回调到短期均线附近都可能是加仓机会。"
            "趋势投资者在多头排列期间应持股待涨，避免过早获利了结。",
        )
    if "空头" in align:
        return rich(
            "均线呈空头排列（短期<中期<长期），趋势向下，反弹可能受阻。",
            "空头排列意味着每次反弹到短期均线附近都可能遇到抛压。"
            "在空头排列未被打破之前，不建议抄底——等待均线开始收敛或金叉再考虑入场。",
        )
    return rich(
        "均线缠绕交织，趋势不明朗，短线操作需谨慎。",
        "均线纠缠通常出现在趋势转换期或横盘整理期——此时做多做空都容易被套。"
        "等待均线重新排列形成明确方向后再操作，能显著提高胜率。",
    )


def interp_weekly_trend(wt):
    """周线趋势解读。"""
    if "上升" in wt or "多" in wt:
        return rich(
            "周线趋势向上，中期看多——回调可视为加仓机会。",
            "周线代表中期趋势（数周到数月），方向向上说明中期资金面持续流入。"
            "日线回调只要不破坏周线趋势结构，都属于健康的技术性调整。",
        )
    if "下降" in wt or "空" in wt:
        return rich(
            "周线趋势向下，中期看空——反弹可能是减仓窗口。",
            "周线下行意味着中期趋势偏空，日线的反弹通常是对下跌的修复而非反转。"
            "在周线趋势反转之前，每次反弹都应视为减仓或出场的机会而非加仓时机。",
        )
    return rich(
        "周线趋势中性，中期方向不明，等待趋势确认。",
        "中性的周线意味着市场在中期时间框架上正在「选择方向」。"
        "此时最佳策略是降低仓位、缩小止损幅度，等待方向明确后再加大操作力度。",
    )


def interp_macd_detail(cross, expanding, histogram, divergence, days_ago):
    """MACD 综合解读。"""
    parts = []
    if "金叉" in (cross or ""):
        parts.append(f"近期出现金叉（{days_ago or '?'} 天前），看多信号")
    elif "死叉" in (cross or ""):
        parts.append(f"近期出现死叉（{days_ago or '?'} 天前），看空信号")
    if expanding and histogram and histogram > 0:
        parts.append("柱状图正向扩张，多方力量在增强")
    elif expanding and histogram and histogram < 0:
        parts.append("柱状图负向扩张，空方力量在增强")
    if divergence and "背离" in divergence and divergence != "无背离":
        parts.append(f"检测到{divergence}——可能的趋势反转预警")
    if not parts:
        return interpret("MACD 未发出明确信号，动量处于中性状态。")
    main = "；".join(parts) + "。"
    detail = (
        "MACD 是趋势跟踪指标中最常用的工具之一。金叉/死叉提供方向信号，"
        "柱状图的扩张/收缩反映动能强弱，背离则是潜在反转的预警。"
        "多个 MACD 信号共振时，信号可靠性更高。"
    )
    return rich(main, detail)


def interp_rsi_detail(rsi_v):
    """RSI 详细解读。"""
    if rsi_v > 70:
        return rich(
            f"RSI {rsi_v:.0f} 处于超买区间（>70），短期获利回吐压力较大，谨慎追高。",
            "超买不等于立即下跌——在强势上涨行情中，RSI 可能长期维持在 70 以上。"
            "但 RSI > 80 后出现拐头下行（从超买区回落），通常是比较可靠的短线卖出信号。",
        )
    if rsi_v >= 50:
        return rich(
            f"RSI {rsi_v:.0f} 处于多方区间（50-70），动能偏强但未过热。",
            "RSI 50-70 是上升趋势中最健康的区间——既有上涨动能，又未触及超买。"
            "如果 RSI 从 50 附近反弹向上，通常确认上升趋势仍在延续。",
        )
    if rsi_v >= 30:
        return rich(
            f"RSI {rsi_v:.0f} 处于空方区间（30-50），动能偏弱，反弹力度可能有限。",
            "RSI 30-50 意味着空方占主导。如果 RSI 持续在 40 以下运行，"
            "说明卖压仍然沉重，任何反弹都可能被迅速消化。",
        )
    return rich(
        f"RSI {rsi_v:.0f} 处于超卖区间（<30），短期可能存在技术性反弹机会。",
        "超卖是潜在的买入信号——历史上 RSI < 30 后反弹的概率较高。"
        "但在极端熊市中，RSI 可能在超卖区域停留很长时间。"
        "建议等待 RSI 从超卖区拐头向上突破 30 后再考虑入场。",
    )


def interp_bollinger_detail(pct_b, bw_status):
    """布林带解读。"""
    parts = []
    if pct_b is not None:
        if pct_b > 80:
            parts.append(f"%B {pct_b:.0f} 接近上轨，价格处于相对高位——可能面临回落压力")
        elif pct_b < 20:
            parts.append(f"%B {pct_b:.0f} 接近下轨，价格处于相对低位——可能获得支撑反弹")
        else:
            parts.append(f"%B {pct_b:.0f} 处于布林带中段，价格波动正常")
    if "收窄" in (bw_status or ""):
        parts.append("带宽收窄预示即将出现方向性突破——波动率收缩后往往伴随大幅变动")
    if not parts:
        return ""
    detail = (
        "布林带是基于统计学的波动率指标。价格触及上/下轨不一定意味着反转，"
        "在强趋势中价格可以沿上/下轨「行走」。带宽收窄（挤压）后的突破方向更值得关注。"
    )
    return rich("；".join(parts) + "。", detail)


def interp_atr_volatility(atr_pct):
    """ATR 波动性解读。"""
    if atr_pct is None:
        return ""
    if atr_pct > 3:
        return rich(
            f"ATR 占价格 {atr_pct}%，波动性较高——单日振幅大，适合短线交易但仓位需控制。",
            f"高波动意味着止损需要设置更宽（建议 1.5-2 倍 ATR），同时持仓量应相应缩小。"
            f"以当前 ATR 计算，合理的日内止损幅度约为 {atr_pct * 1.5:.1f}%。",
        )
    if atr_pct >= 1.5:
        return rich(
            f"ATR 占价格 {atr_pct}%，波动性适中，正常交易范围。",
            "中等波动性兼顾了交易机会和风险控制的平衡。"
            f"建议止损设置在 1-1.5 倍 ATR（约 {atr_pct * 1.25:.1f}%），可以过滤日常噪音。",
        )
    return rich(
        f"ATR 占价格 {atr_pct}%，波动性偏低——价格相对平稳，可能处于盘整蓄势阶段。",
        "低波动期通常预示着即将出现较大波动——这是「暴风雨前的平静」。"
        "建议关注布林带收窄信号，突破方向出现后再跟进操作。",
    )


def interp_support_resistance(supports, resists, price=None):
    """支撑阻力位解读。"""
    parts = []
    if supports:
        sup_price = supports[0]["price"]
        parts.append(f"最近支撑 ${sup_price}（跌到此处可能企稳）")
        if price and isinstance(price, (int, float)) and isinstance(sup_price, (int, float)):
            dist = (price - sup_price) / price * 100
            parts.append(f"距当前价 {dist:.1f}%——{'较近，谨防跌破' if dist < 3 else '有一定缓冲空间'}")
    if resists:
        res_price = resists[-1]["price"]
        parts.append(f"最近阻力 ${res_price}（涨到此处可能遇阻）")
        if price and isinstance(price, (int, float)) and isinstance(res_price, (int, float)):
            dist = (res_price - price) / price * 100
            parts.append(f"距当前价 {dist:.1f}%——{'接近阻力位，突破概率有待确认' if dist < 3 else '有上涨空间'}")
    if not parts:
        return ""
    detail = "支撑位和阻力位是技术分析的核心概念——支撑位跌破后往往变成新的阻力位，反之亦然。多次测试未破的支撑/阻力位强度越高。"
    return rich("；".join(parts) + "。", detail)


def interp_volume_pattern(vr, pv):
    """成交量模式解读。"""
    if vr > 2 and "涨" in pv:
        return rich(
            "放量上涨——资金积极涌入，上涨得到成交量确认，趋势可信度高。",
            "成交量是「价格的X光」——放量上涨说明有大量资金在现价水平愿意买入。"
            "这种量价配合是技术分析中最可靠的看多信号之一。",
        )
    if vr > 2 and "跌" in pv:
        return rich(
            "放量下跌——抛售压力大，恐慌情绪蔓延，短期需回避。",
            "放量下跌意味着大量筹码在抛售——这可能是机构资金在出逃。"
            "在放量下跌企稳之前，不宜抄底。等待成交量回落至均量以下且价格止跌后再观察。",
        )
    if vr < 0.7:
        return rich(
            "缩量运行——市场观望情绪浓厚，需等待放量确认方向。",
            "缩量通常意味着多空双方都在等待催化剂。如果在上涨趋势中缩量回调，这是健康信号；"
            "但如果在高位缩量横盘过久，可能是资金撤退的前兆。",
        )
    return rich(
        "量价配合正常，成交量未发出异常信号。",
        "成交量在正常范围内波动，不构成额外的看多或看空依据。",
    )


def interp_signal_summary(b, br):
    """信号汇总解读。"""
    if b >= br * 2:
        return rich(
            f"多方 {b} vs 空方 {br}，多方压倒性占优——短期做多信号明确。",
            "当多方信号数量是空方的 2 倍以上时，技术面共振看多。"
            "这种情况下顺势做多的胜率较高，但仍需设置止损以防突发利空。",
        )
    if br >= b * 2:
        return rich(
            f"多方 {b} vs 空方 {br}，空方压倒性占优——短期宜观望或轻仓。",
            "空方信号大幅领先意味着短期下行压力显著。"
            "此时即使基本面良好，也可能受到技术面卖压拖累——建议等待技术面改善后再入场。",
        )
    return rich(
        f"多方 {b} vs 空方 {br}，力量接近——方向不明，等待突破确认。",
        "多空势均力敌时，市场往往在等待新的催化剂来打破平衡。"
        "此时最佳策略是降低仓位、收窄止损，等待突破方向确认后再跟进。",
    )


# ============================================================================
# 基本面解读引擎
# ============================================================================

def interp_valuation_panorama(verdicts):
    """估值全景解读。"""
    high_c = sum(1 for v in verdicts if "高" in v or "贵" in v)
    low_c = sum(1 for v in verdicts if "便宜" in v or "低" in v)
    total = len(verdicts)
    if high_c > total / 2:
        return rich(
            "多数估值指标偏高——市场给予较高溢价，可能反映了对未来增长的强烈预期。",
            f"{high_c}/{total} 个指标显示估值偏高。高估值需要强劲的盈利增长来支撑——"
            "如果增速不达预期，估值可能面临收缩压力。建议结合成长性分析综合判断。",
        )
    if low_c > total / 2:
        return rich(
            "多数估值指标偏低——可能存在价值洼地，值得深入研究是否有被低估的机会。",
            f"{low_c}/{total} 个指标显示估值偏低。低估值可能是机会（市场错价），"
            "也可能是陷阱（基本面恶化）。区分两者的关键：盈利能力是否稳定或改善。",
        )
    return rich(
        "估值指标整体合理，市场定价未出现明显偏差。",
        "估值处于合理区间意味着市场已充分反映了已知信息。"
        "股价的进一步走势将更多取决于未来盈利和增长的超预期（或不及预期）程度。",
    )


def interp_margin_analysis(gross_vals, net_vals):
    """利润率趋势解读（基本面报告用）。"""
    if not gross_vals or not net_vals or len(gross_vals) < 2:
        return ""
    g_diff = gross_vals[-1] - gross_vals[0]
    n_diff = net_vals[-1] - net_vals[0]
    if g_diff > 0 and n_diff > 0:
        return rich(
            "毛利率和净利率双双上升——盈利能力全面改善，经营效率提高。",
            f"毛利率变化 {g_diff:+.1f}pp，净利率变化 {n_diff:+.1f}pp。"
            "利润率双升是最理想的基本面形态——公司在扩大收入的同时控制住了成本，形成正向飞轮效应。",
        )
    if g_diff > 0 > n_diff:
        return rich(
            "毛利率上升但净利率下降——产品定价能力增强，但费用侵蚀了底线利润。",
            "这种剪刀差通常由管理费用增长、研发投入加大或财务费用上升导致。"
            "如果费用增长是战略性投入（如研发），短期牺牲利润可能换来长期竞争力。",
        )
    if g_diff < 0:
        return rich(
            "毛利率下降——成本压力增大或竞争导致定价能力减弱，需密切关注。",
            "毛利率是产品竞争力的直接体现。持续下降意味着公司可能面临："
            "原材料涨价、竞争对手降价挤压、产品组合向低毛利品类倾斜。",
        )
    return interpret("利润率趋势平稳，未出现显著变化。")


def interp_dupont(driver):
    """杜邦分解解读。"""
    if "利润" in driver:
        return rich(
            "ROE 主要由利润率驱动——说明公司靠赚取更多利润来提高股东回报，这是最健康的模式。",
            "利润率驱动的高 ROE 意味着公司拥有定价权或成本优势。"
            "这种模式的可持续性最强，因为不依赖杠杆放大风险。",
        )
    if "杠杆" in driver:
        return rich(
            "ROE 主要由杠杆驱动——公司通过借债放大回报，虽然效率高但增加了财务风险。",
            "杠杆驱动的高 ROE 在经济好的时候收益可观，但在经济下行或利率上升时风险加倍。"
            "建议关注公司的负债水平和利息覆盖倍数——如果杠杆过高，一旦盈利下滑，ROE 可能急剧恶化。",
        )
    if "周转" in driver:
        return rich(
            "ROE 主要由资产周转率驱动——公司善于用现有资产创造更多收入。",
            "周转率驱动的模式常见于零售和轻资产行业。"
            "这意味着公司在库存管理、应收账款周转等方面有优势，但提升空间可能有限。",
        )
    return interpret("杜邦分解数据不足，无法判断 ROE 的主要驱动因素。")


def interp_balance_sheet(cr_v, de_v):
    """资产负债表强度解读。"""
    if not isinstance(cr_v, (int, float)) or not isinstance(de_v, (int, float)):
        return interpret("资产负债表数据不完整。")
    if cr_v >= 1.5 and de_v < 1:
        return rich(
            "流动性充足 + 杠杆率低——财务安全垫厚实。",
            f"流动比率 {cr_v:.2f}（>1.5），负债权益比 {de_v:.2f}x（<1）。"
            "公司短期偿债无忧，长期债务风险可控。即使遇到行业周期下行，也有充足的财务缓冲。",
        )
    if cr_v < 1:
        return rich(
            f"流动比率 {cr_v:.2f} 低于 1——短期偿债能力偏弱，需关注现金流状况。",
            "流动比率 < 1 意味着流动资产无法覆盖流动负债——公司需要依赖经营现金流或外部融资来偿还短期债务。"
            "如果同时自由现金流为正，问题不大；但如果 FCF 也为负，则流动性风险显著。",
        )
    if de_v > 2:
        return rich(
            f"负债权益比 {de_v:.2f}x 偏高——杠杆较大，利率敏感性强。",
            "高杠杆公司在利率上升环境中财务负担加重。"
            "建议关注利息覆盖倍数（EBIT/利息费用）——低于 3x 则债务违约风险开始上升。",
        )
    return rich(
        "资产负债表健康度适中，流动性和杠杆均在正常范围。",
        f"流动比率 {cr_v:.2f}，负债权益比 {de_v:.2f}x——不构成明显的风险信号。",
    )


def interp_cashflow_quality(avg_ratio):
    """现金流质量解读。"""
    if avg_ratio > 1.2:
        return rich(
            f"OCF/NI 均值 {avg_ratio:.1f}x，利润含金量优秀——每赚 1 元利润能收回更多现金。",
            "OCF/NI > 1.2 说明公司的利润不是「纸面利润」，而是能切实转化为银行账户里的现金。"
            "这类公司的财报可信度高，盈利能力的可持续性也更强。",
        )
    if avg_ratio >= 0.8:
        return rich(
            f"OCF/NI 均值 {avg_ratio:.1f}x，利润质量正常——现金流与利润基本匹配。",
            "OCF/NI 在 0.8-1.2 之间属于正常水平，不构成正面或负面信号。"
            "但如果该比率呈逐季下降趋势，需警惕利润质量可能在恶化。",
        )
    return rich(
        f"OCF/NI 均值 {avg_ratio:.1f}x，利润含金量不足——可能存在应收账款积压或非现金利润。",
        "OCF/NI < 0.8 意味着利润转化为现金的效率偏低。"
        "常见原因：大量应收账款未回收、存货积压、非现金收入占比高。"
        "如果持续低于 0.8，建议深入审查资产负债表的应收和存货科目。",
    )


def interp_health_rating(rating):
    """财务健康综合评级解读。"""
    desc = {
        "A": "各项财务指标全面优秀，公司财务状况极为稳健，风险极低。",
        "B": "多数指标健康，个别维度有改善空间，整体风险可控。",
        "C": "部分指标出现黄灯，需要持续跟踪，关注是否有恶化趋势。",
        "D": "多项指标发出警告，财务风险偏高，建议谨慎对待。",
    }
    advice = {
        "A": "A 级公司是财务安全型投资者的理想选择——即使估值偏高，财务风险也极低。",
        "B": "B 级公司在正常经济环境下不会出现财务困境，但在极端情况下可能面临一定压力。",
        "C": "C 级公司的某些财务指标已接近警戒线——建议设置更严格的止损，并密切跟踪季度财报。",
        "D": "D 级公司的财务健康状况令人担忧——除非有明确的改善迹象，否则建议避免或大幅降低仓位。",
    }
    return rich(
        desc.get(rating, "评级数据不足。"),
        advice.get(rating, "建议结合其他维度综合判断。"),
    )


# ============================================================================
# 同行对比解读引擎
# ============================================================================

def interp_peer_valuation(target_pe, avg_pe):
    """同行估值矩阵解读。"""
    if not target_pe or not avg_pe:
        return ""
    prem = (target_pe - avg_pe) / avg_pe * 100
    if prem > 50:
        return rich(
            f"P/E 相对同行溢价 {prem:.0f}%——市场给予显著估值溢价，需有强劲增长支撑。",
            "高溢价意味着市场认为公司的盈利质量、增长前景或护城河优于同行。"
            "但如果增速放缓至行业平均水平，溢价收敛的风险较大——P/E 向同行均值靠拢可能意味着显著的股价下跌。",
        )
    if prem > -20:
        return rich(
            f"P/E 与同行差距在 ±20% 内，估值水平基本一致。",
            "与同行的小幅偏差属于正常范围。如果公司的盈利能力或增速优于同行但估值接近，"
            "可能存在相对低估的机会。",
        )
    return rich(
        f"P/E 相对同行折价 {abs(prem):.0f}%——可能是被低估的机会。",
        "折价可能反映：市场对公司有特定担忧（管理层更换、诉讼风险等），"
        "或者只是暂时性的市场忽略。如果基本面指标与同行持平或更优，折价更可能是买入机会。",
    )


def interp_peer_profitability(target_prof, all_profs):
    """盈利能力排名解读。"""
    if not target_prof:
        return ""
    parts = []
    gm_vals = sorted([p.get("gross_margin") for p in all_profs if p.get("gross_margin") is not None], reverse=True)
    roe_vals = sorted([p.get("roe") for p in all_profs if p.get("roe") is not None], reverse=True)
    if gm_vals and target_prof.get("gross_margin") == gm_vals[0]:
        parts.append("毛利率排名第一")
    elif gm_vals and target_prof.get("gross_margin") == gm_vals[-1]:
        parts.append("毛利率排名末位")
    if roe_vals and target_prof.get("roe") == roe_vals[0]:
        parts.append("ROE 排名第一")
    elif roe_vals and target_prof.get("roe") == roe_vals[-1]:
        parts.append("ROE 排名末位")
    if not parts:
        return interpret("盈利能力在同行中处于中游水平。")
    main = "在盈利能力维度，" + "、".join(parts) + "。"
    detail = (
        "毛利率反映产品竞争力和定价权，ROE 反映股东资金的赚钱效率。"
        "在同行中排名领先意味着公司具备差异化的竞争优势或更高效的经营模式。"
    )
    return rich(main, detail)


def interp_peer_growth(target_g, growth_matrix):
    """增长对比解读。"""
    if not target_g or target_g.get("rev_growth") is None:
        return ""
    rev_vals = sorted([g.get("rev_growth") for g in growth_matrix if g.get("rev_growth") is not None], reverse=True)
    if rev_vals and target_g["rev_growth"] == rev_vals[0]:
        return rich(
            "营收增速在同行中排名第一——增长领先优势明显。",
            "增速领先意味着公司正在扩大市场份额或开拓新的增长引擎。"
            "增速领先 + 高估值溢价是合理的组合；增速领先 + 低估值则可能是绝佳的投资机会。",
        )
    if rev_vals and target_g["rev_growth"] == rev_vals[-1]:
        return rich(
            "营收增速在同行中排名末位——增长动能落后于竞争对手。",
            "增速落后需要分析原因：是整体市场饱和导致所有公司增速下降，"
            "还是公司正在失去市场份额。如果是后者，可能面临长期竞争力衰退的风险。",
        )
    return rich(
        "营收增速在同行中处于中游位置，增长表现中规中矩。",
        "中游增速意味着公司跟上了行业发展节奏，但没有展现出超越同行的增长能力。",
    )


def interp_peer_health(target_h, health_matrix):
    """财务健康对比解读。"""
    if not target_h or target_h.get("current_ratio") is None:
        return ""
    cr_vals = sorted([h.get("current_ratio") for h in health_matrix if h.get("current_ratio") is not None], reverse=True)
    if cr_vals and target_h["current_ratio"] == cr_vals[-1]:
        return rich(
            "流动性在同行中排名末位——短期财务弹性弱于竞争对手。",
            "流动性末位意味着公司在应对突发事件（需求下滑、供应链中断）时缓冲空间最小。"
            "如果同时负债率也偏高，则需特别警惕流动性危机风险。",
        )
    if cr_vals and target_h["current_ratio"] == cr_vals[0]:
        return rich(
            "流动性在同行中排名第一——财务安全垫最为充足。",
            "最强的流动性意味着公司在行业低谷期有更多的战略选择空间（逆周期投资、并购机会等）。",
        )
    return rich(
        "流动性在同行中处于中游，财务弹性一般。",
        "中游的流动性不构成明显优势或劣势，但在行业下行周期中可能面临一定压力。",
    )


def interp_competitive_position(s_count, w_count, strengths, weaknesses):
    """竞争位置综合解读。"""
    s_text = "、".join(strengths[:3]) if strengths else "无显著优势"
    w_text = "、".join(weaknesses[:3]) if weaknesses else "无明显劣势"
    if s_count > w_count:
        return rich(
            "优势多于劣势，竞争力较强——在行业中具备差异化的竞争壁垒。",
            f"核心优势：{s_text}。这些优势如果是结构性的（品牌、专利、网络效应），"
            "则长期竞争力有保障。",
            f"需关注的劣势：{w_text}。关注这些劣势是否在恶化。",
        )
    if w_count > s_count:
        return rich(
            "劣势多于优势——需关注是否有改善趋势，或考虑同行中更优质的标的。",
            f"主要劣势：{w_text}。劣势集中在哪些维度决定了改善的难度——"
            "估值劣势相对容易修复，但盈利能力劣势可能需要更长的时间。",
            f"仍有的优势：{s_text}。可以作为公司逆转的潜在基础。",
        )
    return rich(
        "优劣势基本均衡——需结合估值水平判断是否值得配置。",
        f"优势：{s_text}。劣势：{w_text}。均衡的局面意味着公司没有明显的竞争短板，但也缺乏突出亮点。"
        "此时估值水平成为关键决策因素——便宜则值得配置，偏贵则等待。",
    )


# ============================================================================
# 股息解读引擎
# ============================================================================

def interp_dividend_overview(dy):
    """股息概览解读。"""
    if dy is None:
        return ""
    if dy >= 4:
        return rich(
            f"收益率 {dy}% 可观——在当前利率环境下具有吸引力。",
            "4%+ 的收益率超过了多数固收产品的回报率。"
            "但高收益率有时是股价下跌的结果而非公司慷慨——需结合股价趋势和派息安全性综合判断。",
        )
    if dy >= 2:
        return rich(
            f"收益率 {dy}% 中等——提供一定的现金回报，兼顾收入和增长。",
            "2-4% 的收益率是「均衡型」股息的典型水平——既有稳定的现金分红，又保留了资本增值空间。"
            "适合追求稳健回报的中长期投资者。",
        )
    return rich(
        f"收益率 {dy}% 偏低——更多是资本增值型标的，股息收入有限。",
        "低收益率通常意味着：公司更倾向于将利润再投入增长，或者股价估值过高导致收益率被压低。"
        "如果公司同时有高增长和持续加息记录，低收益率可能在未来随着股息增长而改善。",
    )


def interp_payout_safety(pr):
    """派息安全性解读。"""
    if pr is None:
        return ""
    if pr < 50:
        return rich(
            f"派息比率 {pr}%，远低于警戒线——股息可持续性强，加息空间充足。",
            "低派息比率意味着公司只用了不到一半的利润来分红，剩余利润可用于再投资或回购。"
            "即使盈利短期下滑 20-30%，股息也不会面临削减压力。",
        )
    if pr < 80:
        return rich(
            f"派息比率 {pr}%，适中——股息基本安全，但加息空间有限。",
            "50-80% 的派息比率说明公司将大部分利润用于分红。"
            "股息安全性取决于盈利的稳定性——如果公司盈利周期性较强，需警惕低谷期派息比率超过 100%。",
        )
    return rich(
        f"派息比率 {pr}% 偏高——大部分利润用于派息，削减风险上升。",
        "派息比率 > 80% 意味着公司几乎没有利润缓冲。一旦盈利下滑，公司可能面临两难选择："
        "维持股息（牺牲再投资）或削减股息（导致股价下跌）。历史上多数股息削减都发生在派息比率持续高于 80% 之后。",
    )


def interp_dividend_history(yoys):
    """股息增长历史解读。"""
    if not yoys:
        return ""
    if all(y > 0 for y in yoys):
        return rich(
            f"连续 {len(yoys)} 年加息——股息增长记录优异，管理层对未来现金流充满信心。",
            "持续加息是管理层向市场传递的强烈正面信号——说明他们对公司的长期盈利前景有信心。"
            "连续加息 25 年以上的公司被称为「股息贵族」，通常具有更强的抗跌性。",
        )
    if any(y < 0 for y in yoys):
        return rich(
            "历史上出现过削减股息——需警惕股息可持续性，关注盈利和现金流趋势。",
            "股息削减是公司财务健康的重大负面信号——通常发生在盈利大幅下滑或现金流枯竭时。"
            "有过削减记录的公司，其股息承诺的可信度会打折扣。",
        )
    return rich(
        "股息保持稳定但未持续增长——适合追求稳定收入但不期望增长的投资者。",
        "不增不减的股息说明公司在维护基本分红承诺，但可能缺乏足够的盈利增长来支撑加息。",
    )


def interp_dividend_cagr(cagr):
    """CAGR 解读。"""
    if cagr is None:
        return ""
    if cagr > 10:
        return rich(
            f"5 年 CAGR {cagr}%，股息增长强劲——复利效应可观。",
            f"以 {cagr}% 的年化增速计算，10 年后的年化股息将是当前的 {(1 + cagr/100)**10:.1f} 倍。"
            "高股息增速叠加再投资复利，长期总回报非常可观。",
        )
    if cagr > 5:
        return rich(
            f"5 年 CAGR {cagr}%，股息增长稳健——能跑赢通胀。",
            "5-10% 的年化增速意味着股息的购买力在持续增长。"
            "这个水平在股息投资中属于中上——兼顾了稳定性和增长性。",
        )
    if cagr > 0:
        return rich(
            f"5 年 CAGR {cagr}%，股息增长缓慢——难以抵御通胀侵蚀。",
            "低于 5% 的股息增速可能无法跟上通胀。"
            "实际购买力可能在缓慢缩水——如果更看重收入增长，建议考虑增速更高的标的。",
        )
    return rich(
        f"5 年 CAGR {cagr}%，股息在倒退——增长前景堪忧。",
        "负增长意味着公司在缩减分红——这通常是盈利恶化的滞后反映。"
        "除非有明确的触底回升迹象，否则不建议作为收入投资的核心持仓。",
    )


def interp_safety_score(score):
    """安全评分解读。"""
    if score >= 80:
        return rich(
            f"安全评分 {score}/100——股息安全性优秀，派息比率低、增长持续、覆盖充足。",
            "80+ 的安全评分意味着股息在可预见的未来不太可能被削减。"
            "适合作为收入投资组合的核心持仓——即使在经济衰退中也能维持分红。",
        )
    if score >= 60:
        return rich(
            f"安全评分 {score}/100——安全性良好，多数因子健康，但仍需定期检视。",
            "60-80 的评分说明股息基本安全，但某些因子处于边缘状态。"
            "建议每季度检查派息比率和现金流覆盖——如果这两个指标恶化，安全评分可能下调。",
        )
    if score >= 40:
        return rich(
            f"安全评分 {score}/100——安全性一般，存在部分风险信号，需密切关注。",
            "40-60 的评分意味着股息面临一定的不确定性。"
            "在这个区间，任何盈利不及预期或现金流恶化都可能触发股息削减的讨论。",
        )
    return rich(
        f"安全评分 {score}/100——安全性堪忧，多项指标发出警告，股息削减风险较高。",
        "低于 40 的安全评分是强烈的警告信号——历史上该评分区间的公司在 2 年内削减股息的概率超过 50%。"
        "建议降低对股息收入的预期，或转向更安全的标的。",
    )


def interp_dividend_sustainability(pr, fcf_cov, cagr):
    """股息可持续性综合分析。"""
    risks = []
    if pr is not None and pr > 80:
        risks.append(f"派息比率 {pr}% 偏高")
    if fcf_cov is not None and fcf_cov < 1.5:
        risks.append(f"FCF 覆盖仅 {fcf_cov}x")
    if cagr is not None and cagr < 0:
        risks.append("股息增速为负")
    if not risks:
        return rich(
            "股息可持续性评估：良好。派息比率、现金流覆盖和增长趋势均在安全范围内。",
            "当前股息政策可持续性强，短期内不太可能被削减。建议定期跟踪季度财报确认趋势。",
        )
    return rich(
        f"股息可持续性评估：存在风险。" + "、".join(risks) + "。",
        "以上风险因子中任何一个恶化都可能导致股息削减。"
        "建议密切关注下一季度的盈利和现金流数据——如果派息比率继续上升或 FCF 继续下降，"
        "应提前调整仓位。",
    )
