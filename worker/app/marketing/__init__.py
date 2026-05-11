r"""Sentinel marketing module — X/Twitter automated acquisition pipeline.

Pipeline: scanner.TickerMove -> Composer (Claude) -> redline scan -> XClient post
                                                  \-> Tracker (deep-link payload)

Default mode is dry-run; flip via env vars or constructor flags before going live.
"""
from .composer import Composer, Composition, ComposerError
from .jobs import publish_marketing_alerts
from .personas import (
    ALL_PERSONAS,
    MARKET_CALENDAR,
    Persona,
    RISK_WATCHDOG,
    SEC_FILING_REPORTER,
)
from .publisher import Publisher, PublishOutcome
from .redline import RedlineResult, scan
from .signals import passes_gate, score_from_move
from .tracker import build_deep_link, build_payload, parse_payload
from .x_client import PostResult, XClient

__all__ = [
    "ALL_PERSONAS",
    "Composer",
    "Composition",
    "ComposerError",
    "MARKET_CALENDAR",
    "Persona",
    "PostResult",
    "PublishOutcome",
    "Publisher",
    "RISK_WATCHDOG",
    "RedlineResult",
    "SEC_FILING_REPORTER",
    "XClient",
    "build_deep_link",
    "build_payload",
    "parse_payload",
    "passes_gate",
    "publish_marketing_alerts",
    "scan",
    "score_from_move",
]
