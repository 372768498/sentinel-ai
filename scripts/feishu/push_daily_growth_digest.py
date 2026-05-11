"""Push the Sentinel AI Daily Growth Digest to the Feishu review chat.

Pipeline:
  1. Reads VisitEvent / EmailLead / SubscriptionStatus from Postgres for today
     in the America/New_York window (00:00 ET → now).
  2. Upserts a row per content_id in Feishu Performance table.
  3. Sends a digest card to the review chat with Top 3 content + pipeline counts.

Usage (typically after market close, but runnable any time):

    worker/.venv/Scripts/python.exe scripts/feishu/push_daily_growth_digest.py

Flags:
  --no-notify     Skip the digest card (just upsert Performance rows)
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-notify", action="store_true")
    args = parser.parse_args()

    _load_env_local(REPO_ROOT / ".env.local")
    sys.path.insert(0, str(WORKER_DIR))
    try:
        from app.marketing.kpi_aggregator import (
            KPIAggregatorError,
            aggregate_and_push_digest,
        )
        from app.marketing.feishu_client import FeishuConfigError
    except ImportError as exc:
        print(f"[error] import failed: {exc}", file=sys.stderr)
        return 2

    try:
        result = asyncio.run(aggregate_and_push_digest(notify_chat=not args.no_notify))
    except (KPIAggregatorError, FeishuConfigError) as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 1

    print(f"[digest] date={result.date_label} (ET)")
    print(f"[digest] rollups={len(result.rollups)} upserted={result.performance_rows_upserted}")
    print(
        f"[digest] pending_review={result.pending_review} "
        f"blocked_by_redline={result.blocked_by_redline} "
        f"failed_publish={result.failed_publish}"
    )
    print(f"[digest] notified={result.notified}")
    for r in sorted(result.rollups, key=lambda x: -x.clicks)[:5]:
        print(
            f"  [top] {r.content_id}: clicks={r.clicks} emails={r.emails_captured} "
            f"signups={r.signups} paid={r.paid_users}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
