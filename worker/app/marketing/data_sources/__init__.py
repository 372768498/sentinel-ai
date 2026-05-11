"""Data source adapters for the Sentinel AI Market Intelligence Layer.

Each module exposes:
  - a frozen dataclass result type (e.g. MarketMover, SocialSignal)
  - an async fetch function with graceful fallback to [] when keys are missing

Adapters are independent — failure of one never blocks the others.
"""

from .enrichment import SourceSummary, fetch_summaries
from .fmp import MarketMover, fetch_market_movers
from .sec_api import CatalystSignal, fetch_recent_catalysts
from .x_serp import SocialSignal, scan_x_serp_signals
from .youtube import YouTubeSignal, search_stock_videos

__all__ = [
    "CatalystSignal",
    "MarketMover",
    "SocialSignal",
    "SourceSummary",
    "YouTubeSignal",
    "fetch_market_movers",
    "fetch_recent_catalysts",
    "fetch_summaries",
    "scan_x_serp_signals",
    "search_stock_videos",
]
