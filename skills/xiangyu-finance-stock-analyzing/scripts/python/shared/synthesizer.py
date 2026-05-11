"""
信号合成 + 报告生成。

- dataclass 定义（所有分析结果容器）
- synthesize_signal()：加权合成 → 百分制 → 5 级评级
- format_output_text()：结构化 Markdown 报告
- format_output_json()：JSON 输出
"""

import json
from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Literal

from .constants import STOCK_WEIGHTS, raw_to_percentile, score_to_rating


# ============================================================================
# Dataclass 定义
# ============================================================================

@dataclass
class EarningsSurprise:
    score: float
    explanation: str
    actual_eps: float | None = None
    expected_eps: float | None = None
    surprise_pct: float | None = None


@dataclass
class Fundamentals:
    score: float
    key_metrics: dict
    explanation: str


@dataclass
class AnalystSentiment:
    score: float | None
    summary: str
    consensus_rating: str | None = None
    price_target: float | None = None
    current_price: float | None = None
    upside_pct: float | None = None
    num_analysts: int | None = None


@dataclass
class HistoricalPatterns:
    score: float
    pattern_desc: str
    beats_last_4q: int | None = None
    avg_reaction_pct: float | None = None
    total_quarters: int | None = None


@dataclass
class MarketContext:
    vix_level: float
    vix_status: str
    spy_trend_10d: float
    qqq_trend_10d: float
    market_regime: str
    score: float
    explanation: str
    gld_change_5d: float | None = None
    tlt_change_5d: float | None = None
    uup_change_5d: float | None = None
    risk_off_detected: bool = False


@dataclass
class SectorComparison:
    sector_name: str
    industry_name: str
    stock_return_1m: float
    sector_return_1m: float
    relative_strength: float
    sector_trend: str
    score: float
    explanation: str


@dataclass
class EarningsTiming:
    days_until_earnings: int | None
    days_since_earnings: int | None
    next_earnings_date: str | None
    last_earnings_date: str | None
    timing_flag: str
    price_change_5d: float | None
    confidence_adjustment: float
    caveats: list[str]


@dataclass
class MomentumAnalysis:
    """兼容旧接口。"""
    rsi_14d: float | None
    rsi_status: str
    price_vs_52w_low: float | None
    price_vs_52w_high: float | None
    near_52w_high: bool
    near_52w_low: bool
    volume_ratio: float | None
    relative_strength_vs_sector: float | None
    score: float
    explanation: str


@dataclass
class TechnicalAnalysis:
    """v9.0 技术分析完整结果。"""
    score: float
    short_term_trend: str
    # MA
    ma5: float | None
    ma20: float | None
    ma50: float | None
    ma_alignment: str
    # MACD
    macd_value: float
    macd_signal: float
    macd_histogram: float
    macd_trend: str
    # 布林带
    bb_upper: float | None
    bb_lower: float | None
    bb_position: str
    # RSI
    rsi_14d: float | None
    rsi_status: str
    # 成交量
    volume_ratio: float | None
    # 52 周
    range_position: float | None
    near_52w_high: bool
    near_52w_low: bool
    # 关键价位
    support: float | None
    resistance: float | None
    # 说明
    explanation: str


@dataclass
class SentimentAnalysis:
    score: float
    explanation: str
    fear_greed_score: float | None = None
    short_interest_score: float | None = None
    vix_structure_score: float | None = None
    insider_activity_score: float | None = None
    put_call_score: float | None = None
    fear_greed_value: int | None = None
    fear_greed_status: str | None = None
    short_interest_pct: float | None = None
    days_to_cover: float | None = None
    vix_structure: str | None = None
    vix_slope: float | None = None
    insider_net_shares: int | None = None
    insider_net_value: float | None = None
    put_call_ratio: float | None = None
    put_volume: int | None = None
    call_volume: int | None = None
    indicators_available: int = 0
    data_freshness_warnings: list[str] | None = None


@dataclass
class PeerComparison:
    """v9.0 同行对比。"""
    score: float
    peer_tickers: list[str]
    comparisons: dict
    explanation: str


@dataclass
class Signal:
    ticker: str
    company_name: str
    recommendation: str
    state: str
    confidence: float
    final_score: float
    score_100: int           # 百分制
    rating: str              # 5 级评级
    supporting_points: list[str]
    caveats: list[str]
    timestamp: str
    components: dict
    # Brave Search 验证字段
    verification_confidence: float = 1.0
    verified_metrics: dict = field(default_factory=dict)
    verification_warnings: list[str] = field(default_factory=list)


# ============================================================================
# 信号合成
# ============================================================================

def synthesize_signal(
    ticker: str,
    company_name: str,
    earnings: EarningsSurprise | None,
    fundamentals: Fundamentals | None,
    analysts: AnalystSentiment | None,
    historical: HistoricalPatterns | None,
    market_context: MarketContext | None,
    sector: SectorComparison | None,
    earnings_timing: EarningsTiming | None,
    technical: TechnicalAnalysis | None,
    sentiment: SentimentAnalysis | None,
    peer: PeerComparison | None = None,
    breaking_news: list[str] | None = None,
    geopolitical_risk_warning: str | None = None,
    geopolitical_risk_penalty: float = 0.0,
    web_verification=None,
) -> Signal:
    """加权合成 → 百分制 → 5 级评级。"""
    w = STOCK_WEIGHTS
    components = []
    weights = []

    if earnings:
        components.append(("earnings", earnings.score))
        weights.append(w["earnings_surprise"])
    if fundamentals:
        components.append(("fundamentals", fundamentals.score))
        weights.append(w["fundamentals"])
    if analysts and analysts.score is not None:
        components.append(("analysts", analysts.score))
        weights.append(w["analyst_sentiment"])
    if historical:
        components.append(("historical", historical.score))
        weights.append(w["historical_patterns"])
    if market_context:
        components.append(("market", market_context.score))
        weights.append(w["market_context"])
    if sector:
        components.append(("sector", sector.score))
        weights.append(w["sector_performance"])
    if technical:
        components.append(("technical", technical.score))
        weights.append(w["technical"])
    if sentiment:
        components.append(("sentiment", sentiment.score))
        weights.append(w["sentiment"])
    if peer:
        components.append(("peer", peer.score))
        weights.append(w["peer_comparison"])

    # 至少 2 个维度
    if len(components) < 2:
        return Signal(
            ticker=ticker, company_name=company_name,
            recommendation="NEUTRAL", state="Neutral", confidence=0.0, final_score=0.0,
            score_100=50, rating="Neutral",
            supporting_points=["Insufficient data for analysis"],
            caveats=["Limited data available"],
            timestamp=datetime.now().isoformat(), components={},
        )

    # 权重归一化 + 加权平均
    total_w = sum(weights)
    norm = [w / total_w for w in weights]
    final_score = sum(s * nw for (_, s), nw in zip(components, norm))

    # 百分制 + 评级
    score_100 = raw_to_percentile(final_score)
    rating = score_to_rating(score_100)
    confidence = abs(final_score)

    if score_100 >= 80:
        recommendation = "STRONG"
    elif score_100 >= 65:
        recommendation = "CONSTRUCTIVE"
    elif score_100 >= 50:
        recommendation = "NEUTRAL"
    elif score_100 >= 35:
        recommendation = "FRAGILE"
    else:
        recommendation = "HIGH_RISK"
    state = rating

    # ---- 风险修正（加法式衰减，避免链式乘法过度压缩） ----
    confidence_penalty = 0.0

    if earnings_timing:
        confidence_penalty += abs(earnings_timing.confidence_adjustment)
        if earnings_timing.timing_flag == "pre_earnings" and recommendation in ("STRONG", "CONSTRUCTIVE"):
            recommendation = "NEUTRAL"
            state = "Neutral"
        if (earnings_timing.timing_flag == "post_earnings"
                and earnings_timing.price_change_5d and earnings_timing.price_change_5d > 15
                and recommendation in ("STRONG", "CONSTRUCTIVE")):
            recommendation = "NEUTRAL"
            state = "Neutral"

    if technical and technical.rsi_14d and technical.rsi_14d > 70 and technical.near_52w_high:
        if recommendation in ("STRONG", "CONSTRUCTIVE"):
            recommendation = "NEUTRAL"
            state = "Neutral"
        confidence_penalty += 0.15

    if market_context and market_context.risk_off_detected and recommendation in ("STRONG", "CONSTRUCTIVE"):
        confidence_penalty += 0.15

    if geopolitical_risk_penalty > 0 and recommendation in ("STRONG", "CONSTRUCTIVE"):
        confidence_penalty += geopolitical_risk_penalty

    # ---- Brave 验证修正 ----
    verification_confidence = 1.0
    verified_metrics = {}
    verification_warnings = []

    if web_verification:
        verification_confidence = web_verification.overall_confidence
        verification_warnings = list(web_verification.warnings)
        for key, mv in web_verification.metrics.items():
            verified_metrics[key] = {
                "status": mv.status.value,
                "discrepancy_pct": mv.discrepancy_pct,
                "our_value": mv.our_value,
                "web_value": mv.web_value,
            }
        if web_verification.warning_count >= 3:
            confidence_penalty += 0.20
        elif web_verification.warning_count >= 1:
            confidence_penalty += 0.10

    confidence = max(0.05, confidence - confidence_penalty)

    # ---- 生成要点 ----
    supporting = _build_supporting(
        earnings, fundamentals, analysts, historical,
        market_context, sector, technical, sentiment, peer,
    )
    caveats = _build_caveats(
        earnings, earnings_timing, technical, sector,
        market_context, sentiment, breaking_news,
        geopolitical_risk_warning, analysts, len(components),
    )

    # 验证警告加入 caveats
    for w in verification_warnings[:2]:
        caveats.append(w)

    return Signal(
        ticker=ticker, company_name=company_name,
        recommendation=recommendation, state=state, confidence=confidence,
        final_score=final_score, score_100=score_100, rating=rating,
        supporting_points=supporting[:5], caveats=caveats[:7],
        timestamp=datetime.now().isoformat(),
        components=_build_components_dict(
            earnings, fundamentals, analysts, historical,
            market_context, sector, earnings_timing, technical,
            sentiment, peer,
        ),
        verification_confidence=verification_confidence,
        verified_metrics=verified_metrics,
        verification_warnings=verification_warnings,
    )


# ============================================================================
# 报告格式化 — Markdown
# ============================================================================

def format_output_text(
    signal: Signal,
    data_info: dict | None = None,
    technical: TechnicalAnalysis | None = None,
    peer: PeerComparison | None = None,
    sentiment: SentimentAnalysis | None = None,
    deep_valuation=None,
    web_verification=None,
) -> str:
    """中文 Markdown 报告（委托 report_formatter）。"""
    from .report_formatter import format_report
    return format_report(
        signal, data_info=data_info, technical=technical,
        peer=peer, sentiment=sentiment, deep_valuation=deep_valuation,
        web_verification=web_verification,
    )


def format_output_json(signal: Signal) -> str:
    """JSON 输出。"""
    output = {
        **asdict(signal),
        "disclaimer": "NOT FINANCIAL ADVICE. For informational purposes only.",
    }
    return json.dumps(output, indent=2)


# ============================================================================
# 内部辅助
# ============================================================================

def _build_supporting(earnings, fundamentals, analysts, historical, market, sector, technical, sentiment, peer):
    points = []
    if earnings and earnings.actual_eps is not None:
        surprise = earnings.surprise_pct or 0
        points.append(f"EPS 超预期 {surprise:+.1f}%（实际 ${earnings.actual_eps:.2f} vs 预期 ${earnings.expected_eps:.2f}）")
    if fundamentals and fundamentals.key_metrics:
        m = fundamentals.key_metrics
        parts = []
        if "roe" in m:
            parts.append(f"ROE {m['roe']}%")
        if "gross_margin" in m:
            parts.append(f"毛利率 {m['gross_margin']}%")
        if "net_margin" in m:
            parts.append(f"净利率 {m['net_margin']}%")
        if "free_cashflow" in m:
            fcf_b = m["free_cashflow"] / 1e9
            parts.append(f"FCF ${fcf_b:.1f}B")
        if "current_ratio" in m:
            cr = m["current_ratio"]
            parts.append(f"流动比率 {cr:.2f}" + ("（偏低）" if cr < 1.0 else ""))
        if parts:
            points.append("基本面：" + "；".join(parts))
    if analysts:
        rating = getattr(analysts, "consensus_rating", None) or "—"
        target = getattr(analysts, "price_target", None) or 0
        current = getattr(analysts, "current_price", None) or 0
        count = getattr(analysts, "num_analysts", None) or 0
        if target and current and current > 0:
            upside = round((target / current - 1) * 100, 1)
            points.append(f"分析师共识「{rating}」，目标价 ${target:.2f}（上行空间 {upside:+.1f}%，{count} 位分析师）")
        elif analysts.summary:
            points.append(f"分析师共识：{analysts.summary}")
    if historical and historical.pattern_desc:
        beats = getattr(historical, "beats_last_4q", None)
        avg_react = getattr(historical, "avg_reaction_pct", None)
        if beats is not None:
            total_q = historical.total_quarters or 4
            react_str = f"，平均财报后反应 {avg_react:+.1f}%" if avg_react is not None else ""
            points.append(f"历史表现：近 {total_q} 季 {beats} 次超预期{react_str}")
        else:
            points.append(f"历史表现：{historical.pattern_desc}")
    if market:
        vix = getattr(market, "vix_level", None)
        status = getattr(market, "vix_status", None) or "—"
        spy_10d = getattr(market, "spy_trend_10d", None)
        qqq_10d = getattr(market, "qqq_trend_10d", None)
        parts = []
        if vix is not None:
            parts.append(f"VIX {vix:.1f}（{status}）")
        if spy_10d is not None:
            parts.append(f"SPY 10 日 {spy_10d:+.1f}%")
        if qqq_10d is not None:
            parts.append(f"QQQ 10 日 {qqq_10d:+.1f}%")
        if parts:
            points.append(f"市场环境：{'，'.join(parts)}")
        elif market.explanation:
            points.append(f"市场环境：{market.explanation}")
    if sector:
        stock_ret = getattr(sector, "stock_return_1m", None)
        sector_ret = getattr(sector, "sector_return_1m", None)
        name = getattr(sector, "sector_name", "—")
        if stock_ret is not None and sector_ret is not None:
            diff = stock_ret - sector_ret
            points.append(f"板块趋势：{name} 板块 1 月 {sector_ret:+.1f}%，个股 {stock_ret:+.1f}%（相对 {diff:+.1f}pp）")
        elif sector.explanation:
            points.append(f"板块趋势：{sector.explanation}")
    if technical and technical.explanation:
        points.append(f"技术面：{technical.explanation}")
    if sentiment and sentiment.explanation:
        points.append(f"情绪面：{sentiment.explanation}")
    if peer and peer.explanation:
        points.append(f"同行对比：{peer.explanation}")
    return points


def _build_caveats(earnings, timing, technical, sector, market, sentiment, news, geo_warning, analysts, n_components):
    caveats = []
    if timing and timing.caveats:
        caveats.extend(timing.caveats)
    if sentiment and sentiment.data_freshness_warnings:
        caveats.extend(sentiment.data_freshness_warnings)
    if technical and technical.rsi_14d and technical.rsi_14d > 70 and technical.near_52w_high:
        caveats.append("技术面超买 + 接近 52 周高点，追高风险大")
    if sector and sector.score < -0.2:
        caveats.append(f"板块 {sector.sector_name} 走势偏弱，拖累个股表现")
    if market and market.vix_status == "fear":
        caveats.append(f"市场波动性偏高（VIX {market.vix_level:.0f}），系统性风险升温")
    if market and market.risk_off_detected:
        caveats.append(f"避险模式：GLD {market.gld_change_5d:+.1f}%, TLT {market.tlt_change_5d:+.1f}%, UUP {market.uup_change_5d:+.1f}%")
    if news:
        for alert in news[:2]:
            caveats.append(f"突发新闻：{alert}")
    if geo_warning:
        caveats.append(geo_warning)
    if not analysts or analysts.score is None:
        caveats.append("分析师覆盖不足")
    if not earnings:
        caveats.append("缺少近期财报数据")
    if n_components < 4:
        caveats.append("可用数据维度有限，分析覆盖面不足")
    if not caveats:
        caveats.append("市场情况随时可能变化")
    return caveats


def _build_components_dict(earnings, fundamentals, analysts, historical, market, sector, timing, technical, sentiment, peer):
    d = {}
    if earnings:
        d["earnings_surprise"] = {
            "score": earnings.score, "actual_eps": earnings.actual_eps,
            "expected_eps": earnings.expected_eps, "surprise_pct": earnings.surprise_pct,
        }
    if fundamentals:
        d["fundamentals"] = {"score": fundamentals.score, **fundamentals.key_metrics}
    if analysts:
        d["analyst_sentiment"] = {
            "score": analysts.score, "consensus_rating": analysts.consensus_rating,
            "price_target": analysts.price_target, "current_price": analysts.current_price,
            "upside_pct": analysts.upside_pct, "num_analysts": analysts.num_analysts,
        }
    if historical:
        d["historical_patterns"] = {
            "score": historical.score, "beats_last_4q": historical.beats_last_4q,
            "avg_reaction_pct": historical.avg_reaction_pct,
            "pattern_desc": historical.pattern_desc,
            "total_quarters": historical.total_quarters,
        }
    if market:
        d["market_context"] = {
            "score": market.score, "vix_level": market.vix_level,
            "vix_status": market.vix_status, "spy_trend_10d": market.spy_trend_10d,
            "qqq_trend_10d": market.qqq_trend_10d, "market_regime": market.market_regime,
            "risk_off_detected": market.risk_off_detected,
        }
    if sector:
        d["sector_performance"] = {
            "score": sector.score, "sector_name": sector.sector_name,
            "stock_return_1m": sector.stock_return_1m, "sector_return_1m": sector.sector_return_1m,
            "relative_strength": sector.relative_strength,
        }
    if timing:
        d["earnings_timing"] = {
            "days_until_earnings": timing.days_until_earnings,
            "timing_flag": timing.timing_flag,
            "confidence_adjustment": timing.confidence_adjustment,
        }
    if technical:
        d["technical"] = {
            "score": technical.score, "trend": technical.short_term_trend,
            "ma_alignment": technical.ma_alignment, "macd_trend": technical.macd_trend,
            "rsi_14d": technical.rsi_14d, "rsi_status": technical.rsi_status,
            "bb_position": technical.bb_position, "volume_ratio": technical.volume_ratio,
            "support": technical.support, "resistance": technical.resistance,
        }
    if sentiment:
        d["sentiment_analysis"] = {
            "score": sentiment.score, "indicators_available": sentiment.indicators_available,
            "fear_greed_value": sentiment.fear_greed_value, "fear_greed_status": sentiment.fear_greed_status,
            "short_interest_pct": sentiment.short_interest_pct, "put_call_ratio": sentiment.put_call_ratio,
            "vix_structure": sentiment.vix_structure,
        }
    if peer:
        d["peer_comparison"] = {
            "score": peer.score, "peer_tickers": peer.peer_tickers,
            "comparisons": peer.comparisons,
        }
    return d
