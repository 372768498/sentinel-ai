"""
shared — 股票分析共享模块。

导出所有公共接口供 analyze_stock.py 使用。
"""

from .constants import (
    PEER_GROUPS,
    STOCK_WEIGHTS,
    TECHNICAL_PARAMS,
    raw_to_percentile,
    score_to_rating,
)
from .data_fetcher import (
    StockData,
    cache_get,
    cache_set,
    fetch_stock_data,
    fetch_deep_data,
    fetch_verified_data,
)
from .analyzers import (
    analyze_earnings_surprise,
    analyze_fundamentals,
    analyze_analyst_sentiment,
    analyze_historical_patterns,
    analyze_market_context,
    analyze_momentum,
    analyze_sector_performance,
    analyze_technical,
)
from .sentiment import (
    analyze_earnings_timing,
    analyze_peer_comparison,
    analyze_sentiment,
    check_breaking_news,
    check_sector_geopolitical_risk,
)
from .ticker_resolver import (
    resolve_ticker,
    resolve_tickers,
)
from .synthesizer import (
    AnalystSentiment,
    EarningsSurprise,
    EarningsTiming,
    Fundamentals,
    HistoricalPatterns,
    MarketContext,
    MomentumAnalysis,
    PeerComparison,
    SectorComparison,
    SentimentAnalysis,
    Signal,
    TechnicalAnalysis,
    format_output_json,
    format_output_text,
    synthesize_signal,
)
from .web_verifier import (
    MetricVerification,
    VerifyStatus,
    WebVerification,
    build_pending_metrics,
    apply_verification,
    verify_all_metrics,
)
