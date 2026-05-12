"""Preview new Sentinel templates against real (or stubbed) IntelligenceProfiles.

Sprint 1 wire-up tool. Print-only — never submits to Feishu, never posts
to Telegram. Lets you eyeball the new free_telegram_anomaly output side-
by-side with what the LLM composer would produce for the same ticker.

Usage:
    worker/.venv/Scripts/python.exe scripts/preview_new_templates.py \\
        --channel free_telegram --tickers NVDA TSLA AMD MSFT GOOGL

    # Show only the 'nothing unusual' branch
    worker/.venv/Scripts/python.exe scripts/preview_new_templates.py \\
        --channel free_telegram --nothing-only

    # Render via mock data (no FMP key required)
    worker/.venv/Scripts/python.exe scripts/preview_new_templates.py \\
        --channel free_telegram --mock
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Force UTF-8 stdout — template output uses emojis (🛰 🟠 🔴 etc.) that
# Windows default code page (gbk / cp936) can't encode.
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except AttributeError:
    pass

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKER_DIR = REPO_ROOT / "worker"

SUPPORTED_CHANNELS = ("free_telegram",)


def _load_env_local() -> None:
    path = REPO_ROOT / ".env.local"
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def _mock_profile(ticker: str):
    """Build a stub TickerIntelligenceProfile so the preview works without
    FMP/SEC/DataForSEO keys configured."""
    from app.marketing.intelligence import TickerIntelligenceProfile

    return TickerIntelligenceProfile(
        ticker=ticker,
        company_name=f"{ticker} Corp.",
        market_heat=72,
        social_heat=78,
        search_heat=64,
        news_heat=50,
        competitor_heat=15,
        overall_opportunity=85,
        why_now=f"${ticker} — sample anomaly for preview only.",
        market_signals=(
            "Intraday +2.5%",
            "Volume 150M (1.8x avg)",
            f"Market cap $1.5T",
        ),
        social_signals=(
            f"[high_intent_question] $ {ticker} thread on X",
            f"[ticker_buzz] {ticker} mentions doubled",
        ),
        catalysts=("8-K · sample filing (2026-05-12)",),
        recommended_angles=("valuation_gap",),
        evidence={
            "mover": {
                "price": 100.0,
                "change_pct": 2.5,
                "volume": 150_000_000,
                "relative_volume": 1.8,
                "source_url": f"https://example/{ticker}",
            },
            "catalyst_count": 1,
            "sources_used": 4,
        },
        confidence="high",
    )


async def _build_real_profiles(tickers: list[str]):
    from app.marketing.intelligence import build_daily_profiles

    return await build_daily_profiles(seed_tickers=tickers, limit=len(tickers))


def _render_one(profile, idx: int, total: int) -> None:
    from app.marketing.content_factory import _render_free_telegram_body
    from app.marketing.intelligence import profile_to_opportunity

    opp = profile_to_opportunity(profile)
    body = _render_free_telegram_body(opp, f"https://app.jilo.ai/stocks/{opp.ticker}")

    print()
    print("=" * 76)
    print(f" [{idx}/{total}] {opp.ticker}  · state={opp.state}  · chars={len(body)}")
    print("=" * 76)
    print(body)


def _render_nothing_example() -> None:
    from app.marketing.templates.free_telegram import NothingPayload, render_nothing

    body = render_nothing(
        NothingPayload(
            session_label="Pre-market",
            timestamp_et=datetime.now(timezone.utc).strftime("%H:%M UTC"),
            scan_universe_size=7400,
        )
    )
    print()
    print("=" * 76)
    print(f" [nothing-unusual branch]  · chars={len(body)}")
    print("=" * 76)
    print(body)


def main() -> int:
    p = argparse.ArgumentParser(description="Preview new templates without publishing.")
    p.add_argument("--channel", required=True, choices=SUPPORTED_CHANNELS)
    p.add_argument(
        "--tickers",
        nargs="+",
        default=["NVDA", "TSLA", "AMD", "MSFT", "GOOGL"],
        help="Tickers to render (default: 5 mega-caps)",
    )
    p.add_argument(
        "--mock",
        action="store_true",
        help="Use stub profiles, don't call FMP/SEC/etc",
    )
    p.add_argument(
        "--nothing-only",
        action="store_true",
        help="Skip anomaly rendering, only print the 'nothing unusual' branch",
    )
    args = p.parse_args()

    _load_env_local()
    sys.path.insert(0, str(WORKER_DIR))

    print(f"[preview] channel={args.channel}  mock={args.mock}  tickers={args.tickers}")

    if args.nothing_only:
        _render_nothing_example()
        return 0

    try:
        if args.mock:
            profiles = [_mock_profile(t.upper()) for t in args.tickers]
        else:
            profiles = asyncio.run(_build_real_profiles([t.upper() for t in args.tickers]))
    except Exception as exc:
        print(f"[error] profile build failed: {exc}", file=sys.stderr)
        return 1

    if not profiles:
        print("[info] no profiles returned — falling back to 'nothing unusual' branch.")
        _render_nothing_example()
        return 0

    for i, prof in enumerate(profiles, start=1):
        try:
            _render_one(prof, i, len(profiles))
        except Exception as exc:
            print(f"[warn] {prof.ticker} render failed: {exc}", file=sys.stderr)

    print()
    print(f"[preview] rendered {len(profiles)} ticker(s) + showing nothing-unusual fallback below")
    _render_nothing_example()
    return 0


if __name__ == "__main__":
    sys.exit(main())
