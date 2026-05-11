"""Poll the Feishu Content Queue for Approved-not-yet-published records.

Each run:
  - Lists Content Queue.
  - Filters review_status=Approved AND published_url is empty.
  - Marks each as Published with a dry-run URL.
  - Posts a "Published" card to the review chat.

In Week 2 the dry-run URL is `about:dryrun?...`. Week 4+ will swap in real
publisher calls (X, Telegram, etc.).

Usage:

    worker/.venv/Scripts/python.exe scripts/feishu/poll_review_status.py

Flags:
  --no-notify    skip the "Published" card (useful for batch backfill)
  --once         run once and exit (default)
"""

from __future__ import annotations

import argparse
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
    parser = argparse.ArgumentParser(description="Poll Feishu Approved records and mark Published")
    parser.add_argument("--no-notify", action="store_true", help="Skip chat notification card")
    parser.add_argument("--once", action="store_true", help="Run once and exit (default)")
    args = parser.parse_args()
    _ = args.once  # reserved for future daemon mode

    _load_env_local(REPO_ROOT / ".env.local")
    sys.path.insert(0, str(WORKER_DIR))
    try:
        from app.marketing.review_poller import ReviewPollerError, run_once_sync
        from app.marketing.feishu_client import FeishuConfigError
    except ImportError as exc:
        print(f"[error] Cannot import review_poller: {exc}", file=sys.stderr)
        return 2

    try:
        result = run_once_sync(notify_chat=not args.no_notify)
    except (ReviewPollerError, FeishuConfigError) as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 1

    print(f"[scan] Approved-not-published: {result.scanned}")
    for outcome in result.processed:
        tag = "published" if outcome.get("outcome") == "published" else "dry-run"
        print(
            f"  [{tag}] {outcome['content_id']} ({outcome['platform']}, ${outcome.get('ticker','')}) "
            f"→ {outcome.get('published_url')}"
        )
    for outcome in result.failed:
        print(
            f"  [failed] {outcome['content_id']} ({outcome['platform']}): {outcome.get('reason')}",
            file=sys.stderr,
        )
    for err in result.errors:
        print(f"  [error] {err['record_id']}: {err['error']}", file=sys.stderr)

    if result.errors:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
