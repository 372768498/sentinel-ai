"""确保飞书内容队列的单选字段选项完整。

脚本可重复执行：已有选项会保留，审核状态会迁移为中文选项。
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


REQUIRED_SELECT_OPTIONS = {
    "平台": ("X", "Reddit", "Telegram", "TikTok", "YouTube Shorts", "YouTube Long", "Email"),
    "风险等级": ("Low", "Medium", "High"),
    "合规检查": ("Pass", "Needs Edit", "Blocked"),
    "审核状态": ("待审核", "已拦截", "已通过", "已拒绝", "已发布", "发布失败"),
    "拒绝原因": ("wrong_state", "bad_copy", "wrong_ticker", "missing_data", "tone_off", "other"),
}


def _merged_options(
    existing: list[dict],
    required: tuple[str, ...],
    *,
    replace: bool = False,
) -> list[dict]:
    by_name = {item.get("name"): dict(item) for item in existing if item.get("name")}
    merged: list[dict] = []
    for idx, name in enumerate(required):
        item = by_name.get(name)
        if item is None:
            item = {"name": name, "color": idx}
        merged.append(item)
    if replace:
        return merged
    for item in existing:
        name = item.get("name")
        if name and name not in required:
            merged.append(dict(item))
    return merged


def _read_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = []
        for seg in value:
            if isinstance(seg, dict):
                parts.append(seg.get("text", "") or "")
            else:
                parts.append(str(seg))
        return "".join(parts)
    if isinstance(value, dict):
        return value.get("text", "") or value.get("value", "") or ""
    return str(value)


def _migrate_review_status_records(client, app_token: str, table_id: str, *, dry_run: bool) -> tuple[int, int]:
    from app.marketing import bitable_fields as bf

    migrated = 0
    failed = 0
    page_token = None
    while True:
        page = client.bitable_list_records(
            app_token, table_id, page_size=100, page_token=page_token
        )
        for record in page.get("items", []):
            fields = record.get("fields", {})
            current = _read_text(fields.get(bf.REVIEW_STATUS) or fields.get("review_status"))
            target = bf.normalize_review_status(current)
            if not current or current == target:
                continue
            record_id = record["record_id"]
            print(f"[审核状态] 记录迁移：{record_id} {current} -> {target}")
            if dry_run:
                migrated += 1
                continue
            try:
                client.bitable_update_record(
                    app_token,
                    table_id,
                    record_id,
                    {bf.REVIEW_STATUS: target},
                )
                migrated += 1
            except Exception as exc:
                failed += 1
                print(f"[失败] 记录 {record_id}: {exc}")
        if not page.get("has_more"):
            break
        page_token = page.get("page_token")
        if not page_token:
            break
    return migrated, failed


def main() -> int:
    parser = argparse.ArgumentParser(description="Ensure Feishu Content Queue select options are complete")
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

    client = FeishuClient()
    fields = client.bitable_list_fields(app_token, table_id)
    aliases = {
        bf.PLATFORM: "平台",
        "platform": "平台",
        bf.RISK_LEVEL: "风险等级",
        "risk_level": "风险等级",
        bf.REDLINE_RESULT: "合规检查",
        "redline_result": "合规检查",
        bf.REVIEW_STATUS: "审核状态",
        "review_status": "审核状态",
        bf.KILL_REASON: "拒绝原因",
        "jojo_kill_reason": "拒绝原因",
    }

    updated = 0
    failed = 0
    review_field_to_finalize: dict | None = None
    for field in fields:
        field_name = field.get("field_name")
        canonical = aliases.get(field_name)
        if canonical is None:
            continue
        if field.get("type") != 3:
            print(f"[错误] {canonical} 字段类型不是单选：type={field.get('type')}")
            failed += 1
            continue
        required = REQUIRED_SELECT_OPTIONS[canonical]
        existing = (field.get("property") or {}).get("options", []) or []
        existing_names = [item.get("name") for item in existing if item.get("name")]
        obsolete = []
        if canonical == "审核状态":
            obsolete = [name for name in existing_names if name not in required]
        missing = [name for name in required if name not in existing_names]
        print(f"[{canonical}] 当前选项：{', '.join(existing_names) if existing_names else '(空)'}")
        print(f"[{canonical}] 缺失选项：{', '.join(missing) if missing else '无'}")
        if obsolete:
            print(f"[{canonical}] 将移除英文旧选项：{', '.join(obsolete)}")
            review_field_to_finalize = field
        if not missing and not obsolete:
            continue
        if canonical == "审核状态" and obsolete and not missing:
            print("[审核状态] 先迁移记录，随后移除英文旧选项")
            continue
        merged = _merged_options(existing, required)
        if args.dry_run:
            print(f"[计划] {canonical} 更新为：{', '.join(item.get('name', '') for item in merged)}")
            continue
        try:
            client.bitable_update_field(
                app_token,
                table_id,
                field["field_id"],
                field_name=field_name,
                field_type=field.get("type"),
                property={"options": merged},
            )
            updated += 1
            print(f"[已更新] {canonical}")
        except Exception as exc:
            failed += 1
            print(f"[失败] {canonical}: {exc}")

    migrated, migrate_failed = _migrate_review_status_records(
        client, app_token, table_id, dry_run=args.dry_run
    )
    failed += migrate_failed

    if review_field_to_finalize is not None:
        final_options = [{"name": name, "color": idx} for idx, name in enumerate(REQUIRED_SELECT_OPTIONS["审核状态"])]
        if args.dry_run:
            print("[计划] 审核状态最终保留中文选项：" + ", ".join(item["name"] for item in final_options))
        else:
            try:
                client.bitable_update_field(
                    app_token,
                    table_id,
                    review_field_to_finalize["field_id"],
                    field_name=review_field_to_finalize.get("field_name"),
                    field_type=review_field_to_finalize.get("type"),
                    property={"options": final_options},
                )
                updated += 1
                print("[已更新] 审核状态最终保留中文选项")
            except Exception as exc:
                failed += 1
                print(f"[失败] 审核状态最终中文化: {exc}")

    print(f"[汇总] updated={updated} migrated={migrated} failed={failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
