"""Task C.3 · Rename Bitable Content Queue columns to Chinese.

Uses bitable_update_field (PUT /fields/{field_id}) which lets us change
field_name in place without losing data — field_id stays the same.

Worker code is already bilingual (reads via normalize_fields(), writes
via bitable_fields constants). So running this script is safe:
  - Pre-run: worker reads/writes English names against English columns.
  - During: a brief few-second gap while the rename API calls execute.
  - Post-run: worker reads English names via normalize_fields fallback;
    writes use bitable_fields constants which are Chinese — matches the
    renamed columns.

Idempotent: skips any field whose name is already Chinese.

Usage:
    worker/.venv/Scripts/python.exe scripts/feishu/rename_content_queue_to_chinese.py
    worker/.venv/Scripts/python.exe scripts/feishu/rename_content_queue_to_chinese.py --dry-run
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKER_DIR = REPO_ROOT / "worker"

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except AttributeError:
    pass


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


def main() -> int:
    p = argparse.ArgumentParser(description="Rename Content Queue columns to Chinese")
    p.add_argument("--dry-run", action="store_true",
                   help="Print plan, don't call Feishu API")
    args = p.parse_args()

    _load_env_local()
    sys.path.insert(0, str(WORKER_DIR))

    app_token = os.environ.get("FEISHU_BITABLE_APP_TOKEN")
    table_id = os.environ.get("FEISHU_CONTENT_QUEUE_TABLE_ID")
    if not app_token or not table_id:
        print("[error] FEISHU_BITABLE_APP_TOKEN + FEISHU_CONTENT_QUEUE_TABLE_ID required",
              file=sys.stderr)
        return 2

    from app.marketing.bitable_fields import LEGACY_TO_NEW
    from app.marketing.feishu_client import FeishuClient

    client = FeishuClient()
    current_fields = client.bitable_list_fields(app_token, table_id)
    by_name = {f.get("field_name"): f for f in current_fields}

    print(f"[rename] table={table_id}  existing_fields={len(current_fields)}")
    print(f"[rename] dry_run={args.dry_run}")
    print()

    renamed = 0
    skipped_already_cn = 0
    skipped_missing = 0
    failed = 0

    for english, chinese in LEGACY_TO_NEW.items():
        if chinese in by_name:
            print(f"  [skip-cn] {english:<22s} (Chinese '{chinese}' already exists)")
            skipped_already_cn += 1
            continue
        field = by_name.get(english)
        if not field:
            print(f"  [skip-?]  {english:<22s} (not found in table)")
            skipped_missing += 1
            continue
        field_id = field.get("field_id")
        if not field_id:
            print(f"  [skip-!]  {english:<22s} (no field_id in response)")
            skipped_missing += 1
            continue
        field_type = field.get("type")
        if args.dry_run:
            print(f"  [plan]    {english:<22s} → {chinese}  (field_id={field_id}, type={field_type})")
            continue
        try:
            # Feishu API requires `type` even for rename-only — passing
            # back the existing type leaves it unchanged.
            client.bitable_update_field(
                app_token, table_id, field_id,
                field_name=chinese, field_type=field_type,
            )
            print(f"  [rename]  {english:<22s} → {chinese}")
            renamed += 1
        except Exception as exc:
            print(f"  [fail]    {english:<22s}: {exc}")
            failed += 1

    print()
    print(f"[summary] renamed={renamed}  already_chinese={skipped_already_cn}  "
          f"missing={skipped_missing}  failed={failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
