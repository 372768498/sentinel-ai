"""Smoke-test the Market Intelligence Layer end-to-end.

Reads .env.local, calls `build_daily_profiles`, prints a human-readable summary
(or JSON with --json). All adapters degrade gracefully when keys are missing —
the script prints which data sources were skipped.

Usage:
    worker/.venv/Scripts/python.exe scripts/marketing_intelligence_smoke.py
    worker/.venv/Scripts/python.exe scripts/marketing_intelligence_smoke.py --tickers NVDA TSLA
    worker/.venv/Scripts/python.exe scripts/marketing_intelligence_smoke.py --json
    worker/.venv/Scripts/python.exe scripts/marketing_intelligence_smoke.py --no-external
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKER_DIR = REPO_ROOT / "worker"


def _load_env_local(path: Path) -> None:
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _check_keys() -> dict[str, bool]:
    return {
        "fmp": bool(os.environ.get("FMP_API_KEY", "").strip()),
        "sec_api": bool(os.environ.get("SEC_API_KEY", "").strip()),
        "dataforseo": bool(
            os.environ.get("DATAFORSEO_LOGIN", "").strip()
            and os.environ.get("DATAFORSEO_PASSWORD", "").strip()
        ),
        "tavily": bool(os.environ.get("TAVILY_API_KEY", "").strip()),
        "youtube": bool(os.environ.get("YOUTUBE_DATA_API_KEY", "").strip()),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tickers", nargs="+", default=None)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--no-external",
        action="store_true",
        help="Skip all external API keys (uses EDGAR fallback only) — useful for offline smoke",
    )
    args = parser.parse_args()

    _load_env_local(REPO_ROOT / ".env.local")

    if args.no_external:
        for var in (
            "FMP_API_KEY",
            "SEC_API_KEY",
            "DATAFORSEO_LOGIN",
            "DATAFORSEO_PASSWORD",
            "TAVILY_API_KEY",
            "YOUTUBE_DATA_API_KEY",
        ):
            os.environ.pop(var, None)

    sys.path.insert(0, str(WORKER_DIR))
    from app.marketing.intelligence import build_daily_profiles

    keys = _check_keys()
    print("[intel-smoke] adapters configured:")
    for name, present in keys.items():
        marker = "yes" if present else "no"
        print(f"  - {name:12s} {marker}")

    profiles = asyncio.run(
        build_daily_profiles(seed_tickers=args.tickers, limit=args.limit)
    )

    if args.json:
        out = []
        for p in profiles:
            d = asdict(p)
            out.append(d)
        print(json.dumps(out, indent=2, default=str))
        return 0

    if not profiles:
        print("\n[intel-smoke] no profiles produced (all sources empty)")
        return 0

    print(f"\n[intel-smoke] {len(profiles)} profile(s), sorted by overall_opportunity desc:\n")
    for p in profiles:
        print(
            f"  ${p.ticker:6s} overall={p.overall_opportunity:3d}  "
            f"M={p.market_heat:3d} S={p.social_heat:3d} R={p.search_heat:3d} "
            f"N={p.news_heat:3d} C={p.competitor_heat:3d}  conf={p.confidence}"
        )
        print(f"    why_now: {p.why_now}")
        if p.market_signals:
            print(f"    market: {' · '.join(p.market_signals)}")
        if p.catalysts:
            print(f"    catalysts: {' · '.join(p.catalysts)}")
        if p.social_signals:
            print(f"    social ({len(p.social_signals)}): {p.social_signals[0]}")
        print(f"    angles: {', '.join(p.recommended_angles)}")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
