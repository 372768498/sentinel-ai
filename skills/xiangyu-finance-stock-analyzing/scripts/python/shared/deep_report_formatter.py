"""深度报告格式化引擎 v12 — 6 个领域的中文 Markdown 报告模板。"""

from .report_formatter import _annotate
from .deep_report_helpers import (
    deep_annotate as _deep_annotate, interpret as _interpret, one_liner as _one_liner,
    ts as _ts, fmt_num as _fmt_num, fmt_money as _fmt_money, disclaimer as _disclaimer,
    # 估值
    interp_dcf_oneliner, interp_wacc, interp_fcf_projection, interp_dcf_scenarios,
    interp_pe_percentile, interp_industry_relative, interp_valuation_synthesis,
    # 成长性
    interp_revenue_quarterly, interp_cagr, interp_eps_surprise, interp_margin_trend_growth,
    interp_analyst_forecast, interp_peg, interp_growth_quality, interp_growth_synthesis,
    # 技术面
    interp_ma_alignment, interp_weekly_trend, interp_macd_detail, interp_rsi_detail,
    interp_bollinger_detail, interp_atr_volatility, interp_support_resistance,
    interp_volume_pattern, interp_signal_summary,
    # 基本面
    interp_valuation_panorama, interp_margin_analysis, interp_dupont,
    interp_balance_sheet, interp_cashflow_quality, interp_health_rating,
    # 同行对比
    interp_peer_valuation, interp_peer_profitability, interp_peer_growth,
    interp_peer_health, interp_competitive_position,
    # 股息
    interp_dividend_overview, interp_payout_safety, interp_dividend_history,
    interp_dividend_cagr, interp_safety_score, interp_dividend_sustainability,
)
from .deep_report_guides import (
    guide_valuation, guide_growth, guide_technical,
    guide_fundamentals, guide_peers, guide_dividends,
    education_valuation, education_growth, education_technical,
    education_fundamentals, education_peers, education_dividends,
)


def format_deep_report(domain: str, result, signal) -> str:
    """路由到对应报告模板，末尾插入行动指引 + 教育卡片。"""
    _map = {
        "valuation": (_format_valuation, guide_valuation, education_valuation),
        "growth": (_format_growth, guide_growth, education_growth),
        "technical": (_format_technical, guide_technical, education_technical),
        "fundamentals": (_format_fundamentals, guide_fundamentals, education_fundamentals),
        "peers": (_format_peers, guide_peers, education_peers),
        "dividends": (_format_dividends, guide_dividends, education_dividends),
    }
    entry = _map.get(domain)
    if entry is None:
        return f"# 未知深度分析领域: {domain}"
    fmt_fn, guide_fn, edu_fn = entry
    body = fmt_fn(result, signal)
    guide = guide_fn(result, signal)
    edu = edu_fn()
    tail = f"{guide}{edu}" if guide else edu
    if tail:
        body = body.replace("---\n\n*免责声明", f"{tail}---\n\n*免责声明")
    return body


# --- 1. 估值深度报告 ---

def _format_valuation(r, signal) -> str:
    lines = [
        f"# {signal.ticker} {signal.company_name} 估值分析深度报告",
        "",
        f"> 生成时间：{_ts()} | 数据源：Yahoo Finance",
        "",
        "---",
        "",
        "## 核心结论",
        "",
        "| 指标 | 值 |",
        "|------|-----|",
        f"| **DCF 内在价值** | ${r.dcf_value or 'N/A'} |",
        f"| **当前价格** | ${r.current_price or 'N/A'} |",
        f"| **安全边际**（{_deep_annotate('safety_margin')}） | {r.safety_margin_pct or 'N/A'}% — {r.verdict or '—'} |",
        "",
    ]

    lines.append(interp_dcf_oneliner(r.safety_margin_pct))
    lines.append("")

    # DCF 模型
    lines.extend([
        "---", "",
        "## 一、DCF 现金流折现估值", "",
        "> **方法论**：DCF 将公司未来所有自由现金流按折现率换算为今天的价值，",
        "> 回答「如果今天一次性买下整家公司，合理价格是多少」。结果对增长率和",
        "> 折现率假设高度敏感——应关注三种情景的范围而非任何单一数字。", "",
    ])

    if r.growth_rates and r.wacc:
        lines.extend([
            "### 1.1 模型假设", "",
            f"| 参数 | 保守 | 基准 | 乐观 |",
            "|------|------|------|------|",
            f"| 未来 5 年增长率 | {r.growth_rates['conservative']}% | {r.growth_rates['base']}% | {r.growth_rates['optimistic']}% |",
            f"| 永续增长率 | 2.5% | 3.0% | 3.5% |",
            f"| {_deep_annotate('wacc')} | {r.wacc}% | {r.wacc}% | {r.wacc}% |",
            "",
        ])
        lines.append(interp_wacc(r.wacc))

    # 数据来源透明度
    if r.data_sources:
        lines.extend([
            "", "### 1.1b 数据来源与置信度", "",
            "| 参数 | 来源 | 置信度 |",
            "|------|------|--------|",
        ])
        confidence_map = {
            "季度现金流": "🟢 高",
            "Yahoo Finance": "🟢 高",
            "10Y 美债": "🟢 高",
            "假设值": "🔴 低（API 数据缺失）",
        }
        for key, src in r.data_sources.items():
            label = {"fcf": "自由现金流", "beta": "Beta", "risk_free": "无风险利率", "growth": "增长率"}.get(key, key)
            conf = "🟡 中"
            for kw, c in confidence_map.items():
                if kw in src:
                    conf = c
                    break
            lines.append(f"| {label} | {src} | {conf} |")
        lines.extend(["", "> 🟢 高置信度 = API 实际返回值 | 🟡 中 = 延迟数据 | 🔴 低 = 假设值（数据缺失时的默认值）", ""])

    if r.fcf_projections:
        lines.extend([
            "### 1.2 现金流预测", "",
            "| 年份 | 自由现金流 | 折现值 |",
            "|------|-----------|--------|",
            f"| TTM（基础） | {_fmt_money(r.fcf_ttm)} | — |",
        ])
        for p in r.fcf_projections:
            lines.append(f"| Year {p['year']} | {_fmt_money(p['fcf'])} | {_fmt_money(p['pv'])} |")
        if r.terminal_value:
            lines.append(f"| {_deep_annotate('terminal_value')} | {_fmt_money(r.terminal_value)} | — |")
        if r.enterprise_value:
            lines.append(f"| **企业价值** | — | **{_fmt_money(r.enterprise_value)}** |")
        lines.append("")
        lines.append(interp_fcf_projection(r.fcf_ttm))

    if r.dcf_scenarios:
        lines.extend([
            "### 1.3 内在价值", "",
            "| 情景 | 每股内在价值 | vs 当前价 | 判定 |",
            "|------|------------|----------|------|",
        ])
        for s in r.dcf_scenarios:
            lines.append(f"| {s['scenario']} | ${s['value']} | {s['vs_current']:+.1f}% | {s['verdict']} |")
        lines.append("")
        optimistic = next((s for s in r.dcf_scenarios if s["scenario"] == "optimistic"), None)
        conservative = next((s for s in r.dcf_scenarios if s["scenario"] == "conservative"), None)
        lines.append(interp_dcf_scenarios(optimistic, conservative))

    # 历史估值
    lines.extend([
        "---", "",
        "## 二、历史估值范围", "",
        "> **方法论**：将当前的估值倍数与公司自己的历史数据对比。百分位 100% 意味着处于历史最高位，",
        "> 0% 是最低位。历史高位不一定等于「贵」——如果公司基本面发生了质的飞跃，高估值可能是合理的。",
        "> 但统计上，极端百分位往往会向均值回归。", "",
    ])
    for label, range_data in [("市盈率 (P/E)", r.pe_range), ("市销率 (P/S)", r.ps_range)]:
        if range_data:
            lines.extend([
                f"### {label} 范围", "",
                "| 指标 | 最低 | 中位数 | 最高 | **当前** | 历史位置 |",
                "|------|------|--------|------|---------|---------|",
                f"| {label} | {range_data['low']}x | {range_data['median']}x | {range_data['high']}x | **{range_data['current']}x** | {range_data['percentile']}% |",
                "",
            ])
            lines.append(interp_pe_percentile(label, range_data["percentile"]))

    # 行业相对
    if r.industry_comparison:
        lines.extend([
            "---", "",
            "## 三、行业相对估值", "",
            "> **方法论**：将公司估值倍数与同行业公司对比。溢价意味着市场认为该公司更优秀，",
            "> 折价可能是被低估或确实存在竞争劣势。高溢价需要更高的增长或更强的护城河来支撑。", "",
        ])
        lines.extend([
            "| 指标 | 本股 | 同行中位数 | 溢价/折价 |",
            "|------|------|-----------|----------|",
        ])
        has_premium = False
        for ic in r.industry_comparison:
            lines.append(f"| {ic['metric']} | {ic['stock']}x | {ic.get('industry') or 'N/A'} | {ic.get('premium') or 'N/A'} |")
            if ic.get("premium") is not None:
                has_premium = True
        lines.append("")
        if has_premium:
            premiums = [ic["premium"] for ic in r.industry_comparison if ic.get("premium") is not None]
            avg_prem = sum(premiums) / len(premiums) if premiums else 0
            lines.append(interp_industry_relative(avg_prem))

    # 综合
    lines.extend(["---", "", "## 四、估值综合判定", ""])
    lines.append(interp_valuation_synthesis(r.verdict, r.safety_margin_pct))

    lines.append(_disclaimer())
    return "\n".join(lines)


# --- 2. 成长性深度报告 ---

def _format_growth(r, signal) -> str:
    lines = [
        f"# {signal.ticker} {signal.company_name} 成长性分析深度报告",
        "",
        f"> 生成时间：{_ts()} | 数据源：Yahoo Finance",
        "",
        "---",
        "",
        "## 核心结论",
        "",
        "| 指标 | 值 |",
        "|------|-----|",
        f"| **营收增长** | {r.rev_cagr_3y}% |" if r.rev_cagr_3y is not None else "| **营收增长** | N/A |",
        f"| **前瞻 PEG** | {r.peg_ratio} |" if r.peg_ratio is not None else "| **前瞻 PEG** | N/A |",
        f"| **增长态势** | {r.growth_attitude or '—'} |",
        f"| **综合评级** | {r.growth_rating or '—'} |",
        "",
    ]

    # 一句话总结
    rating_desc = {"A": "高速成长", "B": "稳健增长", "C": "增长平淡", "D": "增长乏力"}
    att = r.growth_attitude or ""
    lines.append(_one_liner(
        f"综合评级 {r.growth_rating}（{rating_desc.get(r.growth_rating, '—')}），"
        f"增长态势{att or '待观察'}。"
    ))
    lines.append("")

    # 营收
    lines.extend([
        "---", "",
        "## 一、营收增长趋势", "",
        "> **方法论**：营收是公司增长的起点。同比增长率（YoY）消除了季节性影响，",
        "> 环比增长率（QoQ）反映短期动能变化。关注的不仅是「增速多高」，",
        "> 更重要的是「增速在加快还是放慢」——加速增长是最强的买入信号之一。", "",
    ])

    if r.quarterly_revenue:
        lines.extend([
            "### 1.1 季度营收", "",
            "| 时间 | 营收 | YoY 增长率 | 环比增长率 |",
            "|------|------|-----------|-----------|",
        ])
        for q in r.quarterly_revenue:
            yoy = f"{q['yoy']:+.1f}%" if q['yoy'] is not None else "—"
            qoq = f"{q['qoq']:+.1f}%" if q['qoq'] is not None else "—"
            lines.append(f"| {q['quarter']} | {_fmt_money(q['revenue'])} | {yoy} | {qoq} |")
        lines.append("")
        yoys = [q["yoy"] for q in r.quarterly_revenue if q["yoy"] is not None]
        if yoys:
            lines.append(interp_revenue_quarterly(yoys))

    if r.annual_revenue:
        lines.extend([
            "### 1.2 年度营收汇总", "",
            "| 年度 | 年营收 | YoY 增长率 |",
            "|------|--------|-----------|",
        ])
        for a in r.annual_revenue:
            yoy = f"{a['yoy']:+.1f}%" if a['yoy'] is not None else "—"
            lines.append(f"| {a['year']} | {_fmt_money(a['revenue'])} | {yoy} |")
        lines.append("")
        if r.rev_cagr_5y:
            lines.append(f"- **5 年 {_deep_annotate('cagr')}**：{r.rev_cagr_5y}%")
        if r.rev_cagr_3y and r.rev_cagr_5y:
            lines.append(f"- **3 年 {_deep_annotate('cagr')}**：{r.rev_cagr_3y}%")
        elif r.rev_cagr_3y:
            lines.append(f"- **营收 YoY 增长**：{r.rev_cagr_3y}%")
        lines.append("")
        cagr = r.rev_cagr_3y or r.rev_cagr_5y
        if cagr is not None:
            lines.append(interp_cagr(cagr, r.rev_cagr_3y, r.rev_cagr_5y))

    # EPS
    if r.quarterly_eps:
        lines.extend([
            "---", "",
            "## 二、盈利增长趋势", "",
            "### 2.1 季度 EPS 趋势", "",
            "| 时间 | 实际 EPS | 预期 EPS | 惊喜幅度 |",
            "|------|---------|---------|---------|",
        ])
        for e in r.quarterly_eps:
            surprise = f"{e['surprise']:+.1f}%" if e['surprise'] is not None else "—"
            est = f"${e['estimate']}" if e['estimate'] is not None else "—"
            lines.append(f"| {e['quarter']} | ${e['actual']} | {est} | {surprise} |")
        lines.append("")
        beats = sum(1 for e in r.quarterly_eps if e.get("surprise") and e["surprise"] > 0)
        lines.append(interp_eps_surprise(beats, len(r.quarterly_eps)))

    # 净利率
    if r.margin_trend:
        lines.extend([
            "### 2.2 净利率趋势", "",
            "| 时间 | 净利率 |",
            "|------|--------|",
        ])
        for m in r.margin_trend:
            lines.append(f"| {m['quarter']} | {m['net_margin']}% |")
        lines.append("")
        margins = [m["net_margin"] for m in r.margin_trend]
        lines.append(interp_margin_trend_growth(margins))

    # 分析师预测
    if r.analyst_forecasts:
        af = r.analyst_forecasts
        lines.extend([
            "---", "",
            "## 三、分析师前瞻预测", "",
            "| 指标 | 值 |",
            "|------|-----|",
            f"| 前瞻 EPS | ${af.get('forward_eps', 'N/A')} |",
            f"| 历史 EPS | ${af.get('trailing_eps', 'N/A')} |",
            f"| EPS 增长预期 | {af.get('eps_growth_pct', 'N/A')}% |",
            "",
        ])
        lines.append(interp_analyst_forecast(af.get("eps_growth_pct")))

    # PEG
    lines.extend([
        "---", "",
        "## 四、PEG 估值", "",
        "> **方法论**：PEG = P/E ÷ 盈利增速。它回答「我为每 1% 的增长付出了多少估值」。",
        "> PEG < 1 说明增长还没被充分定价（好机会），PEG > 2 说明市场对增长的定价已经很充分。",
        "> 但 PEG 假设增长会持续——高增长不可能永远维持。", "",
        "| PEG 指标 | 值 | 解读 |",
        "|----------|-----|------|",
    ])
    peg_judge = "N/A"
    if r.peg_ratio:
        peg_judge = "被低估" if r.peg_ratio < 1 else ("合理" if r.peg_ratio < 2 else "增长溢价过高")
    lines.append(f"| 当前 {_deep_annotate('peg')} | {r.peg_ratio or 'N/A'} | {peg_judge} |")
    lines.append(f"| Trailing P/E | {r.trailing_pe or 'N/A'}x | — |")
    lines.append(f"| Forward P/E | {r.forward_pe or 'N/A'}x | — |")
    lines.append(f"| 预期增长率 | {r.forward_growth or 'N/A'}% | — |")
    lines.append("")
    if r.peg_ratio is not None:
        lines.append(interp_peg(r.peg_ratio))

    # 增长质量
    if r.growth_quality:
        gq = r.growth_quality
        lines.extend([
            "---", "",
            "## 五、增长质量", "",
            "| 指标 | TTM YoY 增长 |",
            "|------|-------------|",
        ])
        for key, label in [("rev_cagr", "营收"), ("ni_cagr", "净利润"), ("ocf_cagr", "经营现金流"), ("fcf_cagr", "自由现金流")]:
            val = gq.get(key)
            lines.append(f"| {label} | {val}% |" if val is not None else f"| {label} | N/A |")
        lines.append("")
        lines.append(interp_growth_quality(gq.get("rev_cagr"), gq.get("fcf_cagr")))

    # 毛利率
    if r.gross_margin_trend:
        lines.extend([
            "### 毛利率趋势（定价权）", "",
            "| 时间 | 毛利率 |",
            "|------|--------|",
        ])
        for g in r.gross_margin_trend:
            lines.append(f"| {g['quarter']} | {g['gross_margin']}% |")
        lines.append("")
        gms = [g["gross_margin"] for g in r.gross_margin_trend]
        lines.append(interp_margin_trend_growth(gms, "毛利率"))

    # 综合评级
    lines.extend(["---", "", "## 六、成长性综合评级", ""])
    lines.append(interp_growth_synthesis(r.growth_rating, r.growth_attitude))

    lines.append(_disclaimer())
    return "\n".join(lines)


# --- 3. 技术面深度报告 ---

def _format_technical(r, signal) -> str:
    lines = [
        f"# {signal.ticker} {signal.company_name} 技术分析深度报告",
        "",
        f"> 生成时间：{_ts()} | 数据源：Yahoo Finance",
        "",
        "---",
        "",
        "## 核心结论",
        "",
        "| 指标 | 值 |",
        "|------|-----|",
        f"| **综合信号** | {r.overall_signal} |",
    ]
    # 技术面一句话总结（在构建完核心结论表后插入）
    _tech_summary = (
        "技术面偏多，多项指标支持看涨。" if "偏多" in (r.overall_signal or "") else
        "技术面偏空，多项指标发出警告信号。" if "偏空" in (r.overall_signal or "") else
        "技术面中性，多空力量均衡，等待方向选择。"
    )

    if r.week_52:
        s1 = [lv for lv in (r.support_resistance or []) if "支撑" in lv.get("type", "")]
        r1 = [lv for lv in (r.support_resistance or []) if "阻力" in lv.get("type", "")]
        lines.append(f"| **关键支撑** | ${s1[0]['price'] if s1 else 'N/A'} |")
        lines.append(f"| **关键阻力** | ${r1[-1]['price'] if r1 else 'N/A'} |")
    lines.append("")
    lines.append(_one_liner(_tech_summary))

    # 日线
    if r.daily_ma:
        dm = r.daily_ma
        lines.extend([
            "---", "",
            "## 一、多时间框架趋势", "",
            "> **方法论**：同时分析日线和周线趋势。当两个时间框架方向一致时信号最可靠。",
            "> 日线反映短期（1-4 周）走势，周线反映中期（1-3 月）趋势。",
            "> 均线排列是趋势强度的核心指标：多头排列=健康上升趋势，空头排列=下降趋势主导。", "",
            "### 1.1 日线分析", "",
            "| 均线 | 价格 | 信号 |",
            "|------|------|------|",
        ])
        for label, key in [("MA5", "ma5"), ("MA20", "ma20"), ("MA50", "ma50"), ("MA200", "ma200")]:
            val = dm.get(key)
            lines.append(f"| {label} | ${val or 'N/A'} | — |")
        lines.append("")
        lines.append(f"- **{_deep_annotate('ma_alignment')}**：{dm.get('alignment', '—')}")
        lines.append("")
        lines.append(interp_ma_alignment(dm.get("alignment", "")))

    if r.weekly_ma:
        wm = r.weekly_ma
        lines.extend([
            "### 1.2 周线分析", "",
            f"- 10 周均线：${wm.get('w10', 'N/A')}",
            f"- 30 周均线：${wm.get('w30', 'N/A')}",
            f"- **中期趋势**：{wm.get('trend', '—')}",
            "",
        ])
        lines.append(interp_weekly_trend(wm.get("trend", "")))

    # MACD
    if r.macd:
        m = r.macd
        lines.extend([
            "---", "",
            "## 二、动量指标详解", "",
            f"### 2.1 {_annotate('macd')}", "",
            "| 参数 | 值 |",
            "|------|-----|",
            f"| MACD 线 | {m.get('line', 'N/A')} |",
            f"| 信号线 | {m.get('signal', 'N/A')} |",
            f"| 柱状图 | {m.get('histogram', 'N/A')}（{'扩张' if m.get('histogram_expanding') else '收缩'}） |",
            f"| 最近{_deep_annotate('macd_cross')} | {m.get('last_cross', '—')}，{m.get('cross_days_ago', '—')} 天前 |",
            "",
            f"- **MACD 背离检测**：{m.get('divergence', '无背离')}",
            f"- **MACD 判断**：{m.get('trend', '—')}",
            "",
        ])
        lines.append(interp_macd_detail(
            m.get("last_cross", ""), m.get("histogram_expanding", False),
            m.get("histogram", 0), m.get("divergence", "无背离"), m.get("cross_days_ago"),
        ))

    # RSI
    if r.rsi:
        rs = r.rsi
        lines.extend([
            f"### 2.2 {_deep_annotate('rsi_14')}", "",
            "| 指标 | 值 |",
            "|------|-----|",
            f"| RSI-14 | {rs.get('value', 'N/A')} |",
            f"| 状态 | {rs.get('status', '—')} |",
            "",
        ])
        rsi_v = rs.get("value")
        if rsi_v is not None:
            lines.append(interp_rsi_detail(rsi_v))

    # 布林带
    if r.bollinger:
        b = r.bollinger
        lines.extend([
            "---", "",
            "## 三、波动性分析", "",
            "> **方法论**：波动性衡量价格的波动幅度。布林带通过标准差构建价格通道——",
            "> 带宽收窄预示即将变盘（方向未定），扩张说明趋势正在进行中。",
            "> ATR 给出每日平均波动幅度，是设置止损距离的重要参考。", "",
            "### 3.1 布林带", "",
            "| 参数 | 值 |",
            "|------|-----|",
            f"| 上轨 | ${b.get('upper', 'N/A')} |",
            f"| 中轨 (MA20) | ${b.get('mid', 'N/A')} |",
            f"| 下轨 | ${b.get('lower', 'N/A')} |",
            f"| {_deep_annotate('bollinger_pctb')} | {b.get('pct_b', 'N/A')} |",
            f"| {_deep_annotate('bandwidth')} | {b.get('bandwidth', 'N/A')}（{b.get('bandwidth_status', '—')}） |",
            "",
        ])
        lines.append(interp_bollinger_detail(b.get("pct_b"), b.get("bandwidth_status", "")))

    # ATR
    if r.atr:
        a = r.atr
        lines.extend([
            f"### 3.2 {_deep_annotate('atr')}", "",
            "| 指标 | 值 |",
            "|------|-----|",
            f"| ATR-14 | ${a.get('value', 'N/A')} |",
            f"| ATR 占价格比 | {a.get('pct', 'N/A')}% |",
            f"| 波动性 | {a.get('volatility', '—')} |",
            "",
        ])
        lines.append(interp_atr_volatility(a.get("pct")))

    # 支撑阻力
    if r.support_resistance:
        lines.extend([
            "---", "",
            "## 四、关键价位", "",
            "| 类型 | 价位 | 来源 | 强度 |",
            "|------|------|------|------|",
        ])
        for lv in r.support_resistance:
            lines.append(f"| {lv['type']} | ${lv['price']} | {lv['source']} | {lv['strength']} |")
        lines.append("")
        supports = [lv for lv in r.support_resistance if "支撑" in lv.get("type", "")]
        resists = [lv for lv in r.support_resistance if "阻力" in lv.get("type", "")]
        lines.append(interp_support_resistance(supports, resists))

    # 52 周
    if r.week_52:
        w = r.week_52
        lines.extend([
            f"- 52 周最高：${w['high']}",
            f"- 52 周最低：${w['low']}",
            f"- 距高点：{w['pct_from_high']:+.1f}%，距低点：{w['pct_from_low']:+.1f}%",
            "",
        ])

    # 成交量
    if r.volume_analysis:
        v = r.volume_analysis
        lines.extend([
            "---", "",
            "## 五、成交量分析", "",
            "| 指标 | 值 | 判定 |",
            "|------|-----|------|",
            f"| 今日成交量 | {v['today']:,} | — |",
            f"| 5 日均量 | {v['avg_5d']:,} | — |",
            f"| 20 日均量 | {v['avg_20d']:,} | — |",
            f"| {_deep_annotate('volume_ratio')} | {v['ratio']}x | — |",
            "",
            f"- **量价配合**：{v['price_volume']}",
            "",
        ])
        lines.append(interp_volume_pattern(v["ratio"], v["price_volume"]))

    # 信号汇总
    if r.signal_summary:
        lines.extend([
            "---", "",
            "## 六、买卖信号汇总", "",
            "| # | 指标 | 当前信号 | 方向 | 强度 |",
            "|---|------|---------|------|------|",
        ])
        for i, s in enumerate(r.signal_summary, 1):
            lines.append(f"| {i} | {s['indicator']} | {s['signal']} | {s['direction']} | {s['strength']} |")
        lines.append(f"| — | **综合** | — | **{r.overall_signal}** | **{r.bullish_count}多 {r.bearish_count}空 {r.neutral_count}中** |")
        lines.append("")
        lines.append(interp_signal_summary(r.bullish_count, r.bearish_count))

    lines.append(_disclaimer())
    return "\n".join(lines)


# --- 4. 基本面深度报告 ---

def _format_fundamentals(r, signal) -> str:
    lines = [
        f"# {signal.ticker} {signal.company_name} 基本面分析深度报告",
        "",
        f"> 生成时间：{_ts()} | 数据源：Yahoo Finance",
        "",
        "---",
        "",
        "## 核心结论",
        "",
        "| 指标 | 值 |",
        "|------|-----|",
        f"| **财务健康评级** | {r.health_rating} |",
        "",
    ]

    # 一句话总结
    health_desc = {"A": "优秀，财务状况稳健", "B": "良好，多数指标健康", "C": "中性，部分指标需关注", "D": "有风险，多项指标发出警告"}
    lines.append(_one_liner(f"财务健康评级 {r.health_rating} — {health_desc.get(r.health_rating, '—')}。"))
    lines.append("")

    # 估值全景
    if r.valuation_metrics:
        lines.extend([
            "---", "",
            "## 一、估值指标全景", "",
            "> **方法论**：多个估值指标交叉验证，避免单一指标的盲区。P/E 看盈利估值，",
            "> P/S 看营收估值（适合尚未盈利的公司），P/B 看资产估值，EV/EBITDA 排除了资本结构差异。",
            "> 如果多数指标方向一致，结论可信度更高。", "",
            "| 指标 | 当前值 | 同行中位数 | 判定 |",
            "|------|--------|-----------|------|",
        ])
        for m in r.valuation_metrics:
            lines.append(f"| {m['metric']} | {m['current']}x | {m.get('industry') or 'N/A'} | {m['verdict']} |")
        lines.append("")
        verdicts = [m["verdict"] for m in r.valuation_metrics]
        lines.append(interp_valuation_panorama(verdicts))

    # 利润率趋势
    if r.margin_trend:
        lines.extend([
            "---", "",
            "## 二、盈利能力趋势", "",
            "> **方法论**：利润率趋势比绝对值更重要。毛利率反映定价权和成本控制，",
            "> 净利率反映最终赚钱效率。趋势上升=竞争优势在增强，趋势下降=可能面临竞争压力或成本上涨。", "",
            "| 季度 | 毛利率 | 营业利润率 | 净利率 |",
            "|------|--------|----------|--------|",
        ])
        for m in r.margin_trend:
            gm = f"{m.get('gross', 'N/A')}%"
            om = f"{m.get('operating', 'N/A')}%"
            nm = f"{m.get('net', 'N/A')}%"
            lines.append(f"| {m['quarter']} | {gm} | {om} | {nm} |")
        lines.append("")
        gross_vals = [m.get("gross") for m in r.margin_trend if m.get("gross") is not None]
        net_vals = [m.get("net") for m in r.margin_trend if m.get("net") is not None]
        lines.append(interp_margin_analysis(gross_vals, net_vals))

    # 资本回报
    if r.return_metrics:
        lines.extend([
            "### 资本回报效率", "",
            "| 周期 | ROE | ROA |",
            "|------|-----|-----|",
        ])
        for rm in r.return_metrics:
            lines.append(f"| {rm['quarter']} | {rm.get('roe', 'N/A')}% | {rm.get('roa', 'N/A')}% |")
        lines.append("")

    if r.dupont:
        dp = r.dupont
        lines.extend([
            f"**{_deep_annotate('dupont')}**：净利率 {dp.get('net_margin', 'N/A')}% → ROE {dp.get('roe', 'N/A')}% | 驱动因素：{dp.get('driver', '—')}",
            "",
        ])
        lines.append(interp_dupont(dp.get("driver", "")))

    # 资产负债表
    if r.balance_trend:
        lines.extend([
            "---", "",
            "## 三、财务健康", "",
            "> **方法论**：财务健康分析关注公司的偿债能力和抗风险能力。流动比率>2表示短期安全，",
            "> 负债权益比<1表示长期稳健。现金流质量用OCF/NI衡量——>1说明利润背后有真金白银。", "",
            "### 资产负债表强度", "",
            "| 季度 | 流动比率 | 负债权益比 |",
            "|------|---------|-----------|",
        ])
        for b in r.balance_trend:
            cr = b.get("current_ratio", "N/A")
            de = b.get("de_ratio", "N/A")
            lines.append(f"| {b['quarter']} | {cr} | {de}x |")
        lines.append("")
        last_b = r.balance_trend[-1]
        lines.append(interp_balance_sheet(last_b.get("current_ratio"), last_b.get("de_ratio")))

    # 现金流
    if r.cashflow_trend:
        lines.extend([
            "### 现金流健康度", "",
            "| 季度 | 经营现金流 | 净利润 | OCF/NI | 自由现金流 |",
            "|------|-----------|--------|--------|-----------|",
        ])
        for c in r.cashflow_trend:
            ocf = _fmt_money(c.get("ocf"))
            ni = _fmt_money(c.get("ni"))
            ratio = c.get("ocf_ni_ratio", "N/A")
            fcf = _fmt_money(c.get("fcf"))
            lines.append(f"| {c['quarter']} | {ocf} | {ni} | {_deep_annotate('ocf_ni')} {ratio}x | {fcf} |")
        lines.append("")
        ratios = [c.get("ocf_ni_ratio") for c in r.cashflow_trend if c.get("ocf_ni_ratio") is not None]
        if ratios:
            lines.append(interp_cashflow_quality(sum(ratios) / len(ratios)))

    # 综合
    lines.extend([
        "---", "",
        "## 四、财务健康综合评级", "",
        f"**综合评级：{r.health_rating}**",
        "",
        "评级标准：A=优秀 | B=良好 | C=中性 | D=有风险",
        "",
    ])
    lines.append(interp_health_rating(r.health_rating))

    lines.append(_disclaimer())
    return "\n".join(lines)


# --- 5. 同行对比深度报告 ---

def _format_peers(r, signal) -> str:
    lines = [
        f"# {signal.ticker} {signal.company_name} 同行对比深度报告",
        "",
        f"> 生成时间：{_ts()} | 数据源：Yahoo Finance",
        "",
        "---",
        "",
        "## 核心结论",
        "",
        "| 指标 | 值 |",
        "|------|-----|",
        f"| **竞争位置** | {r.competitive_position or '—'} |",
        "",
    ]

    # 一句话总结
    pos = r.competitive_position or ""
    if "领先" in pos:
        lines.append(_one_liner("在同行中处于领先地位，多个维度优于竞争对手。"))
    elif "中上" in pos:
        lines.append(_one_liner("在同行中表现中上，部分维度具有优势。"))
    else:
        lines.append(_one_liner("在同行中处于中游位置，无显著优势或劣势。"))
    lines.append("")

    # 同行选取
    if r.peers:
        lines.extend([
            "---", "",
            "## 一、同行选取", "",
            "| # | 公司 | Ticker | 市值 |",
            "|---|------|--------|------|",
            f"| ★ | **{signal.company_name}（标的）** | **{r.target_ticker}** | — |",
        ])
        for i, p in enumerate(r.peers, 1):
            cap = _fmt_money(p.get("market_cap"))
            lines.append(f"| {i} | {p['name']} | {p['ticker']} | {cap} |")
        lines.append("")

    # 估值矩阵
    if r.valuation_matrix:
        lines.extend([
            "---", "",
            "## 二、估值对比矩阵", "",
            "> **方法论**：将标的公司与同行在多个估值维度横向对比。溢价代表市场愿意为竞争优势支付的额外价格，",
            "> 折价可能是机会也可能反映真实劣势。重点不是「溢价就是贵」，而是「溢价有没有基本面支撑」。", "",
            "| 公司 | P/E | P/S | P/B | EV/EBITDA | PEG |",
            "|------|-----|-----|-----|-----------|-----|",
        ])
        for v in r.valuation_matrix:
            bold = "**" if v["company"] == r.target_ticker else ""
            lines.append(
                f"| {bold}{v['company']}{bold} | {v.get('pe', 'N/A')} | {v.get('ps', 'N/A')} | "
                f"{v.get('pb', 'N/A')} | {v.get('ev_ebitda', 'N/A')} | {v.get('peg', 'N/A')} |"
            )
        lines.append("")
        target_row = next((v for v in r.valuation_matrix if v["company"] == r.target_ticker), None)
        peer_pes = [v.get("pe") for v in r.valuation_matrix if v["company"] != r.target_ticker and v.get("pe") is not None]
        if target_row and target_row.get("pe") and peer_pes:
            lines.append(interp_peer_valuation(target_row["pe"], sum(peer_pes) / len(peer_pes)))

    # 盈利能力
    if r.profitability_matrix:
        lines.extend([
            "---", "",
            "## 三、盈利能力对比", "",
            "| 公司 | 毛利率 | 净利率 | ROE | ROA |",
            "|------|--------|--------|-----|-----|",
        ])
        for p in r.profitability_matrix:
            bold = "**" if p["company"] == r.target_ticker else ""
            gm = f"{p['gross_margin']}%" if p.get('gross_margin') is not None else "N/A"
            nm = f"{p['net_margin']}%" if p.get('net_margin') is not None else "N/A"
            roe = f"{p['roe']}%" if p.get('roe') is not None else "N/A"
            roa = f"{p['roa']}%" if p.get('roa') is not None else "N/A"
            lines.append(f"| {bold}{p['company']}{bold} | {gm} | {nm} | {roe} | {roa} |")
        lines.append("")
        target_prof = next((p for p in r.profitability_matrix if p["company"] == r.target_ticker), None)
        if target_prof:
            lines.append(interp_peer_profitability(target_prof, r.profitability_matrix))

    # 增长
    if r.growth_matrix:
        lines.extend([
            "---", "",
            "## 四、增长对比", "",
            "| 公司 | 营收增长(YoY) | EPS 增长 |",
            "|------|-------------|---------|",
        ])
        for g in r.growth_matrix:
            bold = "**" if g["company"] == r.target_ticker else ""
            rg = f"{g['rev_growth']}%" if g.get('rev_growth') is not None else "N/A"
            eg = f"{g['eps_growth']}%" if g.get('eps_growth') is not None else "N/A"
            lines.append(f"| {bold}{g['company']}{bold} | {rg} | {eg} |")
        lines.append("")
        target_g = next((g for g in r.growth_matrix if g["company"] == r.target_ticker), None)
        if target_g:
            lines.append(interp_peer_growth(target_g, r.growth_matrix))

    # 财务健康
    if r.health_matrix:
        lines.extend([
            "---", "",
            "## 五、财务健康对比", "",
            "| 公司 | 流动比率 | 负债权益比 | FCF |",
            "|------|---------|-----------|-----|",
        ])
        for h in r.health_matrix:
            bold = "**" if h["company"] == r.target_ticker else ""
            cr = h.get("current_ratio", "N/A")
            de = f"{h['de_ratio']}x" if h.get("de_ratio") is not None else "N/A"
            fcf = _fmt_money(h.get("fcf"))
            lines.append(f"| {bold}{h['company']}{bold} | {cr} | {de} | {fcf} |")
        lines.append("")
        target_h = next((h for h in r.health_matrix if h["company"] == r.target_ticker), None)
        if target_h:
            lines.append(interp_peer_health(target_h, r.health_matrix))

    # 排名
    if r.rankings:
        lines.extend([
            "---", "",
            "## 六、竞争位置综合评估", "",
            "| 维度 | 本股 vs 同行 | 排名 | 评价 |",
            "|------|-------------|------|------|",
        ])
        for rk in r.rankings:
            lines.append(f"| {rk['dimension']} | {rk['vs_peers']} | {rk['rank']} | {rk['assessment']} |")
        lines.append(f"| **综合位置** | — | — | **{r.competitive_position}** |")
        lines.append("")

    # 核心发现
    lines.extend([
        "**核心发现**：",
        f"- 优势：{'、'.join(r.strengths or ['—'])}",
        f"- 劣势：{'、'.join(r.weaknesses or ['—'])}",
        "",
    ])
    lines.append(interp_competitive_position(
        len(r.strengths or []), len(r.weaknesses or []),
        r.strengths or [], r.weaknesses or [],
    ))

    lines.append(_disclaimer())
    return "\n".join(lines)


# --- 6. 股息深度报告 ---

def _format_dividends(r, signal) -> str:
    lines = [
        f"# {signal.ticker} {signal.company_name} 股息分析深度报告",
        "",
        f"> 生成时间：{_ts()} | 数据源：Yahoo Finance",
        "",
        "---",
        "",
        "## 核心结论",
        "",
        "| 指标 | 值 |",
        "|------|-----|",
        f"| **股息收益率** | {r.dividend_yield or 'N/A'}% |",
        f"| **安全评分** | {r.safety_score}/100 |",
        f"| **收入投资评级** | {r.income_rating} |",
        f"| **连续加息** | {r.consecutive_years or 'N/A'} 年 |",
        "",
    ]

    # 一句话总结
    rating_map = {
        "EXCELLENT": "优秀的收入来源，适合作为核心收入持仓",
        "GOOD": "良好的股息投资标的，适合纳入收入组合",
        "MODERATE": "股息存在部分风险信号，需密切关注可持续性",
        "POOR": "股息风险较高，不建议作为主要收入来源",
    }
    lines.append(_one_liner(f"收入投资评级 {r.income_rating} — {rating_map.get(r.income_rating, '—')}。"))
    lines.append("")

    if r.income_rating == "NO_DIVIDEND":
        lines.extend(["**该股票不支付股息。**", ""])
        lines.append(_disclaimer())
        return "\n".join(lines)

    # 概览
    lines.extend([
        "---", "",
        "## 一、股息概览", "",
        "> **方法论**：股息投资的核心是「安全性 + 增长性」的平衡。高股息率如果没有安全性支撑",
        "> 可能是陷阱（股价暴跌导致）。理想的股息投资标的应具备：合理收益率 + 低派息比率 + 持续加息历史。", "",
        "| 指标 | 值 |",
        "|------|-----|",
        f"| 当前股价 | ${r.current_price or 'N/A'} |",
        f"| 年化股息 | ${r.annual_dividend or 'N/A'}/股 |",
        f"| 股息收益率 | {r.dividend_yield or 'N/A'}% |",
        f"| 派息频率 | {r.payment_frequency or 'N/A'} |",
        f"| 除息日 | {r.ex_dividend_date or 'N/A'} |",
        "",
    ])
    lines.append(interp_dividend_overview(r.dividend_yield))

    # 安全性
    lines.extend([
        "---", "",
        "## 二、派息安全性", "",
        "| 指标 | 值 | 判定 |",
        "|------|-----|------|",
        f"| 派息比率 | {r.payout_ratio or 'N/A'}% | {r.payout_status or '—'} |",
        f"| FCF 覆盖倍数 | {r.fcf_coverage or 'N/A'}x | {r.fcf_coverage_status or '—'} |",
        "",
    ])
    lines.append(interp_payout_safety(r.payout_ratio))

    # 增长
    if r.yearly_dividends:
        lines.extend([
            "---", "",
            "## 三、股息增长", "",
            "### 逐年股息历史", "",
            "| 年度 | 年化股息 | YoY 增长率 |",
            "|------|---------|-----------|",
        ])
        for yd in r.yearly_dividends:
            yoy = f"{yd['yoy_growth']:+.1f}%" if yd['yoy_growth'] is not None else "—"
            lines.append(f"| {yd['year']} | ${yd['amount']} | {yoy} |")
        lines.append("")
        yoys = [yd["yoy_growth"] for yd in r.yearly_dividends if yd["yoy_growth"] is not None]
        if yoys:
            lines.append(interp_dividend_history(yoys))

        lines.extend([
            "### 增长指标", "",
            "| 指标 | 值 |",
            "|------|-----|",
            f"| 5 年 CAGR | {r.cagr_5y or 'N/A'}% |",
            f"| 3 年 CAGR | {r.cagr_3y or 'N/A'}% |",
            f"| 最近加息幅度 | {r.last_raise_pct or 'N/A'}% |",
            f"| 连续加息年数 | {r.consecutive_years or 'N/A'} 年 |",
            f"| 股息贵族状态 | {'是（≥25 年）' if r.is_aristocrat else '否'} |",
            "",
        ])
        lines.append(interp_dividend_cagr(r.cagr_5y))

    # 安全评分
    lines.extend([
        "---", "",
        f"## 四、安全评分详解：{r.safety_score}/100", "",
    ])
    if r.safety_factors:
        lines.extend([
            "| 因子 | 贡献分 | 说明 |",
            "|------|--------|------|",
        ])
        for f in r.safety_factors:
            lines.append(f"| {f['factor']} | {f['contribution']} | {f['description']} |")
        lines.append("")
    lines.append(interp_safety_score(r.safety_score))
    lines.append(interp_dividend_sustainability(r.payout_ratio, r.fcf_coverage, r.cagr_5y))

    # 评级
    lines.extend([
        "---", "",
        "## 五、收入投资评级", "",
        f"### 评级：{r.income_rating}", "",
        f"**当前评级**：**{r.income_rating}** — {r.summary}",
        "",
    ])

    lines.append(_disclaimer())
    return "\n".join(lines)


