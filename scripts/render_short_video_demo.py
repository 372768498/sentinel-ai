from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "worker"))

from app.marketing.short_video_renderer import (
    ShortVideoSpec,
    render_mp4,
    write_preview_svg,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Render a Sentinel AI short-video demo")
    parser.add_argument("--ticker", default="NVDA")
    parser.add_argument("--state", default="HEATED")
    parser.add_argument("--out", default="docs/assets/sentinel-short-demo-nvda.mp4")
    parser.add_argument("--svg", default="docs/assets/sentinel-short-demo-nvda.svg")
    parser.add_argument("--duration", type=int, default=8)
    args = parser.parse_args()

    ticker = args.ticker.upper().lstrip("$")
    spec = ShortVideoSpec(
        ticker=ticker,
        state=args.state,
        hook=f"${ticker} has three signals firing right now.",
        why_now="AI-chip attention, margin expectations, and valuation pressure are all moving at the same time.",
        risk_flags=(
            "Expectation crowding",
            "Margin sensitivity",
            "Valuation compression",
        ),
        cta_url=f"https://app.jilo.ai/stocks/{ticker}",
    )
    svg_path = write_preview_svg(spec, Path(args.svg))
    mp4_path = render_mp4(spec, Path(args.out), duration_seconds=args.duration)
    print(f"svg={svg_path}")
    print(f"mp4={mp4_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
