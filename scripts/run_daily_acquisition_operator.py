from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "worker"))

from app.marketing.acquisition_operator import run_daily_acquisition_operator


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Sentinel AI acquisition operator once")
    parser.add_argument("--session", default="manual_acquisition_operator")
    parser.add_argument("--output-root", default="docs/growth-runs")
    parser.add_argument("--content-date", default=None)
    parser.add_argument("--campaign-id", default=None)
    parser.add_argument(
        "--render-video-packs",
        action="store_true",
        help="Also render MP4 media for Shorts/TikTok packs. Slower; requires ffmpeg.",
    )
    args = parser.parse_args()

    result = asyncio.run(
        run_daily_acquisition_operator(
            session_label=args.session,
            output_root=Path(args.output_root),
            content_date=args.content_date,
            campaign_id=args.campaign_id,
            render_video_packs=args.render_video_packs,
        )
    )
    print(f"run_id={result['run_id']}")
    print(f"output_dir={result['output_dir']}")
    print(f"drafts_created={result['drafts_created']}")
    print(f"submitted_to_review={result['submitted_to_review']}")
    print(f"video_packs_created={result['video_packs_created']}")
    print(f"blocked_count={result['blocked_count']}")
    return 0 if not result["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
