"""
常量定义 v12：权重、板块感知阈值、地缘风险映射。
"""


# ============================================================================
# 评分权重 v12 — 合计精确 1.00
# ============================================================================

STOCK_WEIGHTS = {
    "earnings_surprise": 0.15,       # 盈利惊喜
    "fundamentals": 0.20,            # 基本面（最高权重）
    "analyst_sentiment": 0.12,       # 分析师情绪
    "historical_patterns": 0.05,     # 历史表现
    "market_context": 0.08,          # 市场环境
    "sector_performance": 0.08,      # 板块强度
    "technical": 0.12,               # 技术分析
    "sentiment": 0.10,               # 市场情绪
    "peer_comparison": 0.10,         # 同行对比
}
# 合计：0.15+0.20+0.12+0.05+0.08+0.08+0.12+0.10+0.10 = 1.00


# ============================================================================
# 板块感知估值阈值 v12
# (good_thresh, bad_thresh) — 越低越好的指标
# 来源：Damodaran 行业估值数据 / Morningstar / CFA 标准
# ============================================================================

SECTOR_VALUATION_THRESHOLDS = {
    "growth": {
        "pe": (25, 45),       # Damodaran 科技 forward P/E median ~34
        "ps": (5.0, 15.0),    # Damodaran Software P/S 8-11
        "pb": (5.0, 20.0),    # 科技 P/B 9-34，高 ROE 支撑高 P/B
        "ev_ebitda": (15, 30), # Damodaran 科技 EV/EBITDA 22-35
        "peg": (1.0, 2.0),    # Peter Lynch 标准
    },
    "value": {
        "pe": (12, 20),       # 传统价值投资标准
        "ps": (1.0, 3.0),     # 低增长行业
        "pb": (1.0, 3.0),     # Graham 标准
        "ev_ebitda": (8, 15),  # 全市场中位数
        "peg": (1.0, 2.0),
    },
    "industrial": {
        "pe": (15, 25),       # 周期性行业
        "ps": (1.5, 5.0),
        "pb": (2.0, 5.0),
        "ev_ebitda": (10, 20),
        "peg": (1.0, 2.0),
    },
}

SECTOR_GROUP_MAP = {
    "Technology": "growth",
    "Communication Services": "growth",
    "Healthcare": "growth",
    "Consumer Cyclical": "growth",
    "Utilities": "value",
    "Consumer Defensive": "value",
    "Energy": "value",
    "Real Estate": "value",
    "Financial Services": "value",
    "Financials": "value",
    "Industrials": "industrial",
    "Basic Materials": "industrial",
}


def get_valuation_thresholds(sector: str = "") -> dict:
    """根据板块返回对应估值阈值。未知板块回退到 value（更保守）。"""
    group = SECTOR_GROUP_MAP.get(sector, "value")
    return SECTOR_VALUATION_THRESHOLDS[group]


# ============================================================================
# 评分阈值 v12 — 百分制 + 5 级评级
# ============================================================================

RATING_THRESHOLDS = {
    "strong_buy": 80,
    "buy": 65,
    "hold": 50,
    "reduce": 35,
    # 0-34 = Sell
}

RATING_LABELS = {
    "strong_buy": "Strong Buy",
    "buy": "Buy",
    "hold": "Hold",
    "reduce": "Reduce",
    "sell": "Sell",
}


def score_to_rating(score: int) -> str:
    """百分制 → 5 级评级。"""
    if score >= RATING_THRESHOLDS["strong_buy"]:
        return "Strong Buy"
    if score >= RATING_THRESHOLDS["buy"]:
        return "Buy"
    if score >= RATING_THRESHOLDS["hold"]:
        return "Hold"
    if score >= RATING_THRESHOLDS["reduce"]:
        return "Reduce"
    return "Sell"


def raw_to_percentile(raw: float) -> int:
    """[-1, 1] 原始分 → [0, 100] 百分制。"""
    return max(0, min(100, int(50 + raw * 50)))


# ============================================================================
# 板块 ETF 映射
# ============================================================================

SECTOR_ETF_MAP = {
    "Financial Services": "XLF",
    "Financials": "XLF",
    "Technology": "XLK",
    "Healthcare": "XLV",
    "Consumer Cyclical": "XLY",
    "Consumer Defensive": "XLP",
    "Utilities": "XLU",
    "Basic Materials": "XLB",
    "Real Estate": "XLRE",
    "Communication Services": "XLC",
    "Industrials": "XLI",
    "Energy": "XLE",
}


# ============================================================================
# 突发新闻 — 危机关键词
# ============================================================================

CRISIS_KEYWORDS = {
    "war": ["war", "invasion", "military strike", "attack", "conflict", "combat"],
    "economic": ["recession", "crisis", "collapse", "default", "bankruptcy", "crash"],
    "regulatory": ["sanctions", "embargo", "ban", "investigation", "fraud", "probe"],
    "disaster": ["earthquake", "hurricane", "pandemic", "outbreak", "disaster", "catastrophe"],
    "financial": ["emergency rate", "fed emergency", "bailout", "circuit breaker", "trading halt"],
}


# ============================================================================
# 地缘政治风险映射
# ============================================================================

GEOPOLITICAL_RISK_MAP = {
    "taiwan": {
        "keywords": ["taiwan", "tsmc", "strait"],
        "sectors": ["Technology", "Communication Services"],
        "sector_etfs": ["XLK", "XLC"],
        "impact": "Semiconductor supply chain disruption",
        "affected_tickers": ["NVDA", "AMD", "TSM", "INTC", "QCOM", "AVGO", "MU"],
    },
    "china": {
        "keywords": ["china", "beijing", "tariff", "trade war"],
        "sectors": ["Technology", "Consumer Cyclical", "Consumer Defensive"],
        "sector_etfs": ["XLK", "XLY", "XLP"],
        "impact": "Tech supply chain and consumer market exposure",
        "affected_tickers": ["AAPL", "QCOM", "NKE", "SBUX", "MCD", "YUM", "TGT", "WMT"],
    },
    "russia_ukraine": {
        "keywords": ["russia", "ukraine", "putin", "kyiv", "moscow"],
        "sectors": ["Energy", "Materials"],
        "sector_etfs": ["XLE", "XLB"],
        "impact": "Energy and commodity price volatility",
        "affected_tickers": ["XOM", "CVX", "COP", "SLB", "MOS", "CF", "NTR", "ADM"],
    },
    "middle_east": {
        "keywords": ["iran", "israel", "gaza", "saudi", "middle east", "gulf"],
        "sectors": ["Energy", "Industrials"],
        "sector_etfs": ["XLE", "XLI"],
        "impact": "Oil price volatility and defense spending",
        "affected_tickers": ["XOM", "CVX", "COP", "LMT", "RTX", "NOC", "GD", "BA"],
    },
    "banking_crisis": {
        "keywords": ["bank failure", "credit crisis", "liquidity crisis", "bank run"],
        "sectors": ["Financials"],
        "sector_etfs": ["XLF"],
        "impact": "Financial sector contagion risk",
        "affected_tickers": ["JPM", "BAC", "WFC", "C", "GS", "MS", "USB", "PNC"],
    },
}


# ============================================================================
# 同行分组 — 按行业龙头映射
# ============================================================================

PEER_GROUPS = {
    "Technology": {
        "Software—Infrastructure": ["MSFT", "ORCL", "CRM", "ADBE", "NOW"],
        "Semiconductors": ["NVDA", "AMD", "INTC", "AVGO", "QCOM", "TSM"],
        "Consumer Electronics": ["AAPL", "MSFT", "DELL", "HPQ", "LOGI"],
        "Internet Content & Information": ["GOOGL", "META", "SNAP", "PINS"],
        "Software—Application": ["ADBE", "CRM", "INTU", "WDAY"],
        "_default": ["AAPL", "MSFT", "GOOGL", "META", "NVDA"],
    },
    "Financial Services": {
        "Banks—Diversified": ["JPM", "BAC", "WFC", "C", "GS"],
        "Insurance—Diversified": ["BRK-B", "AIG", "MET", "PRU"],
        "Capital Markets": ["GS", "MS", "SCHW", "BLK"],
        "_default": ["JPM", "BAC", "GS", "MS", "BLK"],
    },
    "Healthcare": {
        "Drug Manufacturers—General": ["JNJ", "PFE", "MRK", "ABBV", "LLY"],
        "Medical Devices": ["MDT", "ABT", "SYK", "BSX", "ISRG"],
        "Biotechnology": ["AMGN", "GILD", "REGN", "VRTX", "BIIB"],
        "_default": ["JNJ", "UNH", "PFE", "ABBV", "LLY"],
    },
    "Consumer Cyclical": {
        "Internet Retail": ["AMZN", "BABA", "JD", "MELI", "ETSY"],
        "Restaurants": ["MCD", "SBUX", "YUM", "CMG", "DRI"],
        "Auto Manufacturers": ["TSLA", "TM", "F", "GM", "RIVN"],
        "_default": ["AMZN", "TSLA", "NKE", "MCD", "HD"],
    },
    "Consumer Defensive": {
        "_default": ["PG", "KO", "PEP", "WMT", "COST"],
    },
    "Energy": {
        "_default": ["XOM", "CVX", "COP", "SLB", "EOG"],
    },
    "Industrials": {
        "_default": ["CAT", "HON", "UNP", "BA", "GE"],
    },
    "Communication Services": {
        "_default": ["GOOGL", "META", "NFLX", "DIS", "CMCSA"],
    },
    "Utilities": {
        "_default": ["NEE", "DUK", "SO", "D", "AEP"],
    },
    "Real Estate": {
        "_default": ["AMT", "PLD", "CCI", "EQIX", "SPG"],
    },
    "Basic Materials": {
        "_default": ["LIN", "APD", "ECL", "SHW", "NEM"],
    },
}


# ============================================================================
# 技术分析参数
# ============================================================================

TECHNICAL_PARAMS = {
    "ma_short": 5,
    "ma_mid": 20,
    "ma_long": 50,
    "macd_fast": 12,
    "macd_slow": 26,
    "macd_signal": 9,
    "bb_period": 20,
    "bb_std": 2.0,
    "rsi_period": 14,
    "volume_avg_period": 20,
}
