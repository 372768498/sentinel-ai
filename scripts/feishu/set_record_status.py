"""Manually set a Content Queue record's review_status via OpenAPI.

Useful for testing the poll → publish handoff without clicking the Bitable cell.

Usage:

    # By content_id (find latest matching row, recommended for tests)
    worker/.venv/Scripts/python.exe scripts/feishu/set_record_status.py \\
        --content-id CT-20260511-NVDA-x --status 已通过

    # By record_id (exact row, faster)
    worker/.venv/Scripts/python.exe scripts/feishu/set_record_status.py \\
        --record-id recXXXXX --status 已通过

Status values: 待审核 / 已拦截 / 已通过 / 已拒绝 / 已发布 / 发布失败
Legacy English aliases are still accepted for CLI convenience.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKER_DIR = REPO_ROOT / "worker"

ALLOWED_STATUS = (
    "待审核",
    "已拦截",
    "已通过",
    "已拒绝",
    "已发布",
    "发布失败",
    "Pending",
    "Blocked",
    "Approved",
    "Rejected",
    "Published",
    "Failed",
)


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
    parser = argparse.ArgumentParser(description="Set Content Queue review_status via OpenAPI")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--content-id", help="content_id to find (uses latest matching row)")
    group.add_argument("--record-id", help="exact Bitable record_id")
    parser.add_argument("--status", required=True, choices=ALLOWED_STATUS)
    args = parser.parse_args()

    _load_env_local(REPO_ROOT / ".env.local")
    sys.path.insert(0, str(WORKER_DIR))
    try:
        from app.marketing import bitable_fields as bf
        from app.marketing.feishu_client import FeishuAPIError, FeishuClient, FeishuConfigError
    except ImportError as exc:
        print(f"[error] Cannot import feishu_client: {exc}", file=sys.stderr)
        return 2

    app_token = os.environ.get("FEISHU_BITABLE_APP_TOKEN", "").strip()
    table_id = os.environ.get("FEISHU_CONTENT_QUEUE_TABLE_ID", "").strip()
    if not app_token or not table_id:
        print("[error] FEISHU_BITABLE_APP_TOKEN / FEISHU_CONTENT_QUEUE_TABLE_ID missing", file=sys.stderr)
        return 2

    try:
        client = FeishuClient()
    except FeishuConfigError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 2

    record_id = args.record_id
    if not record_id:
        print(f"[1/2] Searching for content_id={args.content_id}...")
        try:
            page = client.bitable_list_records(app_token, table_id, page_size=100)
        except FeishuAPIError as exc:
            print(f"[error] {exc}", file=sys.stderr)
            return 1
        matches = [
            r for r in page.get("items", [])
            if bf.normalize_fields(r.get("fields", {})).get(bf.CONTENT_ID) == args.content_id
        ]
        if not matches:
            print(f"[error] No record found for content_id={args.content_id}", file=sys.stderr)
            return 1
        record_id = matches[-1]["record_id"]
        print(f"       latest match: {record_id} (of {len(matches)} candidates)")

    status = bf.normalize_review_status(args.status)
    print(f"[2/2] Updating {record_id} → review_status={status}...")
    try:
        client.bitable_update_record(
            app_token, table_id, record_id, {bf.REVIEW_STATUS: status}
        )
    except FeishuAPIError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 1
    print(f"[ok] {record_id} review_status = {status}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
