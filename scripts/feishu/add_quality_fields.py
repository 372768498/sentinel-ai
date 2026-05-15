"""Task 4.1 · Add three quality-control columns to the Content Queue
Bitable table. Idempotent — safe to re-run.

Adds:
  jojo_quality_score  · number (1-5)
  jojo_kill_reason    · single select (6 options)
  jojo_one_word       · text (free form)

Why these three:
  - quality_score forces Operator-jojo to leave a numeric judgement on
    every Approved draft (Task 4.2 enforces this server-side).
  - kill_reason explains rejects so we can spot category patterns
    (wrong state vs bad copy vs bad ticker).
  - one_word is the gut-feel slot: a single word per draft. Cheap to
    fill, signals tone drift over time.

Usage:
    worker/.venv/Scripts/python.exe scripts/feishu/add_quality_fields.py
    worker/.venv/Scripts/python.exe scripts/feishu/add_quality_fields.py --dry-run
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKER_DIR = REPO_ROOT / "worker"


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


# Field-type integers from Bitable API docs.
FIELD_TYPE_TEXT = 1
FIELD_TYPE_NUMBER = 2
FIELD_TYPE_SINGLE_SELECT = 3

KILL_REASON_OPTIONS = [
    "wrong_state",
    "bad_copy",
    "wrong_ticker",
    "missing_data",
    "tone_off",
    "other",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Add quality control fields to Content Queue")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print what would be added, don't call Feishu API",
    )
    args = parser.parse_args()

    _load_env_local()
    sys.path.insert(0, str(WORKER_DIR))

    app_token = os.environ.get("FEISHU_BITABLE_APP_TOKEN")
    table_id = os.environ.get("FEISHU_CONTENT_QUEUE_TABLE_ID")
    if not app_token or not table_id:
        print("[error] FEISHU_BITABLE_APP_TOKEN + FEISHU_CONTENT_QUEUE_TABLE_ID required", file=sys.stderr)
        return 2

    from app.marketing import bitable_fields as bf
    from app.marketing.feishu_client import FeishuClient

    client = FeishuClient()

    print(f"[add-quality-fields] app_token={app_token[:8]}…  table_id={table_id}")
    print(f"[add-quality-fields] dry_run={args.dry_run}")

    # Inspect existing fields so we can skip duplicates and surface what's there.
    existing = client.bitable_list_fields(app_token, table_id)
    existing_names = {f.get("field_name") for f in existing}
    print(f"[add-quality-fields] existing fields ({len(existing)}):")
    for f in existing:
        print(f"  - {f.get('field_name')!r}  type={f.get('type')}")

    plan = [
        {
            "field_name": bf.QUALITY_SCORE,
            "legacy_name": "jojo_quality_score",
            "type": FIELD_TYPE_NUMBER,
            "property": {"formatter": "0"},
        },
        {
            "field_name": bf.KILL_REASON,
            "legacy_name": "jojo_kill_reason",
            "type": FIELD_TYPE_SINGLE_SELECT,
            "property": {"options": [{"name": name} for name in KILL_REASON_OPTIONS]},
        },
        {
            "field_name": bf.ONE_WORD,
            "legacy_name": "jojo_one_word",
            "type": FIELD_TYPE_TEXT,
            "property": None,
        },
    ]

    print()
    added = 0
    skipped = 0
    for field in plan:
        name = field["field_name"]
        legacy_name = field["legacy_name"]
        if name in existing_names or legacy_name in existing_names:
            print(f"  [skip]  {name} (already exists)")
            skipped += 1
            continue
        if args.dry_run:
            print(f"  [plan]  {name} (type={field['type']})")
            continue
        try:
            client.bitable_add_field(
                app_token,
                table_id,
                field_name=name,
                field_type=field["type"],
                property=field.get("property"),
            )
            print(f"  [add]   {name} (type={field['type']})")
            added += 1
        except Exception as exc:
            print(f"  [fail]  {name}: {exc}")
            return 1

    print()
    print(f"[summary] added={added}  skipped={skipped}  total_planned={len(plan)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
