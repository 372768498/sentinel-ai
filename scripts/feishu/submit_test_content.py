"""End-to-end smoke test: submit a mock NVDA X-thread to the Feishu review queue.

Usage (from repo root):

    worker/.venv/Scripts/python.exe scripts/feishu/submit_test_content.py

Reads Feishu credentials + Bitable IDs from `.env.local`. After running, check:
  - Bitable Content Queue: a new row with content_id=CT-YYYYMMDD-NVDA-x
  - Feishu review chat: a message starting "[Sentinel AI Review Needed]"
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
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
    _load_env_local(REPO_ROOT / ".env.local")
    sys.path.insert(0, str(WORKER_DIR))
    try:
        from app.marketing.review_queue import ContentDraft, ReviewQueueError, submit_to_review
        from app.marketing.feishu_client import FeishuConfigError
    except ImportError as exc:
        print(f"[error] Cannot import review_queue: {exc}", file=sys.stderr)
        return 2

    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    public_url = os.environ.get("GROWTH_OS_PUBLIC_URL", "http://localhost:3000")
    cta_url = (
        f"{public_url}/stocks/NVDA"
        f"?utm_source=x&utm_medium=thread"
        f"&utm_campaign=CMP-{today}-01&utm_content=CT-{today}-NVDA-x"
    )

    body = (
        "$NVDA Sentinel AI score: 78/100 (SOLID)\n\n"
        "3 things stand out:\n"
        "1. Data center revenue accelerating year-over-year\n"
        "2. Margins expanded vs. last quarter\n"
        "3. Export-restriction risk under regulatory review\n\n"
        "Main risk flag: export restrictions may weigh on Q3 guidance.\n\n"
        "Full 10-dimension breakdown:\n"
        f"{cta_url}\n\n"
        "Context, not financial advice."
    )

    draft = ContentDraft(
        content_id=f"CT-{today}-NVDA-x",
        campaign_id=f"CMP-{today}-01",
        platform="X",
        ticker="NVDA",
        hook="$NVDA Sentinel AI score 78/100 — one risk stands out.",
        body=body,
        cta_url=cta_url,
        risk_level="Medium",
        publish_time=None,
    )

    print(f"[submit] content_id={draft.content_id}")
    try:
        result = submit_to_review(draft)
    except (ReviewQueueError, FeishuConfigError) as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 1

    print(f"[ok] record_id={result.record_id}")
    print(f"[ok] review_status={result.review_status}")
    print(f"[ok] redline={'pass' if result.redline.ok else result.redline.reason()}")
    print(f"[ok] open in browser: {result.record_url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
