"""
Render English one-liners from xiangyu's component dict.

xiangyu emits CN-flavored supporting_points / caveats which are great for
the underlying Chinese-language analyst tool but read poorly in the
English Sentinel AI surface. Here we walk the structured `components`
dict (all keys & numeric values are English) and produce per-dimension
labels we can drop straight into the Pro DM detail card.

Public API:
    component_label(name)       — short English label for a dimension key
    component_highlight(name, c) — short English value summary, e.g.
                                   "EPS surprise +5.2%", "Fear&Greed 52
                                   (Neutral)". Returns None when the
                                   dimension dict is empty or unparseable.
    rank_components(components) — (strongest3, weakest3) lists of
                                   (key, score) pairs from the
                                   `components` dict by .score field.
"""
from __future__ import annotations

from typing import Any

_LABELS: dict[str, str] = {
    "earnings_surprise": "Earnings surprise",
    "fundamentals": "Fundamentals",
    "analyst_sentiment": "Analyst consensus",
    "historical_patterns": "Earnings track",
    "market_context": "Market regime",
    "sector_performance": "Sector strength",
    "technical": "Technicals",
    "sentiment_analysis": "Sentiment",
    "peer_comparison": "Peer comp",
}


def component_label(name: str) -> str:
    return _LABELS.get(name, name.replace("_", " ").title())


def _fmt_pct(value: Any) -> str | None:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return f"{v:+.1f}%"


def _fmt_roe(value: Any) -> str | None:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    # xiangyu emits ROE either as 0.27 (fraction) or 27 (already percent)
    if abs(v) < 5:
        return f"{v * 100:.0f}%"
    return f"{v:.0f}%"


def _fmt_billions(value: Any) -> str | None:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return f"${v / 1e9:.1f}B"


def _hl_earnings_surprise(c: dict) -> str | None:
    pct = _fmt_pct(c.get("surprise_pct"))
    if pct is None:
        return None
    return f"EPS surprise {pct}"


def _hl_fundamentals(c: dict) -> str | None:
    parts: list[str] = []
    roe = _fmt_roe(c.get("roe"))
    if roe:
        parts.append(f"ROE {roe}")
    fcf = _fmt_billions(c.get("free_cashflow") or c.get("fcf"))
    if fcf:
        parts.append(f"FCF {fcf}")
    pe = c.get("pe_ratio")
    if not parts and isinstance(pe, (int, float)):
        parts.append(f"P/E {pe:.1f}")
    return " · ".join(parts) if parts else None


def _hl_analyst_sentiment(c: dict) -> str | None:
    rating = c.get("consensus_rating")
    upside = c.get("upside_pct")
    if rating and isinstance(upside, (int, float)):
        return f"{rating} · {upside:+.0f}% upside"
    if rating:
        return str(rating)
    if isinstance(upside, (int, float)):
        return f"{upside:+.0f}% upside"
    return None


def _hl_historical_patterns(c: dict) -> str | None:
    beats = c.get("beats_last_4q")
    total = c.get("total_quarters") or 4
    if isinstance(beats, int):
        return f"{beats}/{total} earnings beats"
    desc = c.get("pattern_desc")
    return str(desc) if desc else None


def _hl_market_context(c: dict) -> str | None:
    vix = c.get("vix_level")
    status = c.get("vix_status") or ""
    if isinstance(vix, (int, float)):
        return f"VIX {vix:.1f}" + (f" ({status})" if status else "")
    regime = c.get("market_regime")
    return str(regime) if regime else None


def _hl_sector_performance(c: dict) -> str | None:
    stock = c.get("stock_return_1m")
    sector = c.get("sector_return_1m")
    if isinstance(stock, (int, float)) and isinstance(sector, (int, float)):
        diff = (stock - sector) * 100
        return f"{diff:+.1f}% vs sector (1m)"
    rel = c.get("relative_strength")
    if isinstance(rel, (int, float)):
        return f"Rel. strength {rel:+.1f}"
    return None


def _hl_technical(c: dict) -> str | None:
    trend = c.get("trend") or ""
    rsi = c.get("rsi_14d")
    if trend and isinstance(rsi, (int, float)):
        return f"{trend} · RSI {rsi:.0f}"
    if trend:
        return str(trend)
    return None


def _hl_sentiment_analysis(c: dict) -> str | None:
    fg = c.get("fear_greed_value")
    status = c.get("fear_greed_status") or ""
    if isinstance(fg, (int, float)):
        return f"Fear&amp;Greed {fg:.0f}" + (f" ({status})" if status else "")
    return None


def _hl_peer_comparison(c: dict) -> str | None:
    peers = c.get("peer_tickers") or []
    if not peers:
        return None
    # Highlight the single most prominent premium/discount line
    comps = c.get("comparisons") or {}
    pe = comps.get("pe", {})
    premium = pe.get("premium_pct")
    if isinstance(premium, (int, float)):
        direction = "premium" if premium > 0 else "discount"
        return f"P/E {abs(premium):.0f}% {direction} vs peers"
    return f"Peers: {' · '.join(list(peers)[:5])}"


_HIGHLIGHTERS = {
    "earnings_surprise": _hl_earnings_surprise,
    "fundamentals": _hl_fundamentals,
    "analyst_sentiment": _hl_analyst_sentiment,
    "historical_patterns": _hl_historical_patterns,
    "market_context": _hl_market_context,
    "sector_performance": _hl_sector_performance,
    "technical": _hl_technical,
    "sentiment_analysis": _hl_sentiment_analysis,
    "peer_comparison": _hl_peer_comparison,
}


def component_highlight(name: str, component: Any) -> str | None:
    if not isinstance(component, dict):
        return None
    fn = _HIGHLIGHTERS.get(name)
    if fn is None:
        return None
    try:
        return fn(component)
    except Exception:
        return None


def rank_components(
    components: dict, top_n: int = 3,
) -> tuple[list[tuple[str, float]], list[tuple[str, float]]]:
    """
    Sort components by their `score` field, return (strongest, weakest).
    Components without a numeric score are skipped.
    """
    scored: list[tuple[str, float]] = []
    for name, c in components.items():
        if not isinstance(c, dict):
            continue
        s = c.get("score")
        if not isinstance(s, (int, float)):
            continue
        scored.append((name, float(s)))

    scored.sort(key=lambda x: x[1], reverse=True)
    strongest = scored[:top_n]
    weakest = list(reversed(scored[-top_n:])) if len(scored) >= top_n else []
    # Avoid overlap when the watchlist has < 2*top_n dimensions
    strongest_keys = {k for k, _ in strongest}
    weakest = [(k, s) for k, s in weakest if k not in strongest_keys]
    return strongest, weakest


def extract_peer_tickers(components: dict) -> list[str]:
    peer = components.get("peer_comparison") if isinstance(components, dict) else None
    if not isinstance(peer, dict):
        return []
    return list(peer.get("peer_tickers") or [])
