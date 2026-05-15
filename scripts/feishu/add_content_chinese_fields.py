"""给飞书内容队列增加中文内容列。

新增字段：

- 钩子中文（兼容名 hook_zh）
- 正文中文（兼容名 body_zh）

脚本可重复执行：字段已存在时自动跳过。
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
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


FIELD_TYPE_TEXT = 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Add Chinese hook/body fields to Feishu Content Queue")
    parser.add_argument("--dry-run", action="store_true", help="只打印计划，不调用飞书写接口")
    args = parser.parse_args()

    _load_env_local()
    sys.path.insert(0, str(WORKER_DIR))

    app_token = os.environ.get("FEISHU_BITABLE_APP_TOKEN", "").strip()
    table_id = os.environ.get("FEISHU_CONTENT_QUEUE_TABLE_ID", "").strip()
    if not app_token or not table_id:
        print("[error] 需要 FEISHU_BITABLE_APP_TOKEN + FEISHU_CONTENT_QUEUE_TABLE_ID", file=sys.stderr)
        return 2

    from app.marketing import bitable_fields as bf
    from app.marketing.feishu_client import FeishuClient

    plan = [
        {"field_name": bf.HOOK_ZH, "legacy_name": "hook_zh", "type": FIELD_TYPE_TEXT},
        {"field_name": bf.BODY_ZH, "legacy_name": "body_zh", "type": FIELD_TYPE_TEXT},
    ]

    client = FeishuClient()
    fields = client.bitable_list_fields(app_token, table_id)
    existing_names = {item.get("field_name") for item in fields}

    print(f"[中文内容列] table_id={table_id} dry_run={args.dry_run}")
    added = 0
    skipped = 0
    for field in plan:
        name = field["field_name"]
        legacy_name = field["legacy_name"]
        if name in existing_names or legacy_name in existing_names:
            print(f"  [跳过] {name} 已存在")
            skipped += 1
            continue
        if args.dry_run:
            print(f"  [计划] 添加 {name}")
            continue
        client.bitable_add_field(
            app_token,
            table_id,
            field_name=name,
            field_type=field["type"],
        )
        print(f"  [已添加] {name}")
        added += 1

    print(f"[汇总] added={added} skipped={skipped}")
    print()
    print("[视图顺序建议]")
    print("  请在飞书内容队列视图里把列拖成：钩子 -> 钩子中文 -> 正文 -> 正文中文。")
    print("  说明：飞书 OpenAPI 当前可加字段/改字段名，但不能稳定调整列顺序。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
