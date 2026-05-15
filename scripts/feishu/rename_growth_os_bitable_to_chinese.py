"""把 Sentinel AI Growth OS 飞书多维表格改成中文，并审计字段结构。

覆盖三张表：

1. Campaigns -> 活动
2. Content Queue -> 内容队列
3. Performance -> 表现数据

字段重命名是原地更新：field_id 不变，历史数据不丢。worker 代码通过
bitable_fields.normalize_fields() 同时兼容英文旧字段和中文新字段。

注意：飞书当前 Bitable OpenAPI 在本项目权限下不支持数据表表名重命名
（REST 更新表名返回 404）。本脚本可靠处理字段中文化，并在审计报告里
提示表名是否仍需在飞书 UI 手动改名。
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
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


@dataclass(frozen=True)
class TablePlan:
    legacy_name: str
    chinese_name: str
    env_var: str
    field_map: dict[str, str]


def _resolve_table_id(client, app_token: str, plan: TablePlan) -> str | None:
    env_value = os.environ.get(plan.env_var, "").strip()
    if env_value:
        return env_value

    tables = client.bitable_list_tables(app_token)
    for table in tables:
        if table.get("name") in {plan.legacy_name, plan.chinese_name}:
            return table.get("table_id")
    return None


def _audit_fields(existing: list[dict], field_map: dict[str, str]) -> tuple[list[str], list[str], list[str]]:
    names = {item.get("field_name") for item in existing}
    ok: list[str] = []
    missing: list[str] = []
    legacy: list[str] = []
    for english, chinese in field_map.items():
        if chinese in names:
            ok.append(chinese)
        elif english in names:
            legacy.append(english)
        else:
            missing.append(f"{english} -> {chinese}")
    return ok, legacy, missing


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Rename Sentinel AI Growth OS Feishu Bitable tables/fields to Chinese"
    )
    parser.add_argument("--dry-run", action="store_true", help="只打印计划，不调用飞书写接口")
    parser.add_argument("--audit-only", action="store_true", help="只审计结构，不做重命名")
    args = parser.parse_args()

    _load_env_local()
    sys.path.insert(0, str(WORKER_DIR))

    app_token = os.environ.get("FEISHU_BITABLE_APP_TOKEN", "").strip()
    if not app_token:
        print("[error] 需要 FEISHU_BITABLE_APP_TOKEN", file=sys.stderr)
        return 2

    from app.marketing import bitable_fields as bf
    from app.marketing.feishu_client import FeishuClient

    plans = [
        TablePlan(
            legacy_name="Campaigns",
            chinese_name=bf.TABLE_CAMPAIGNS,
            env_var="FEISHU_CAMPAIGNS_TABLE_ID",
            field_map=bf.CAMPAIGNS_LEGACY_TO_NEW,
        ),
        TablePlan(
            legacy_name="Content Queue",
            chinese_name=bf.TABLE_CONTENT_QUEUE,
            env_var="FEISHU_CONTENT_QUEUE_TABLE_ID",
            field_map=bf.CONTENT_QUEUE_LEGACY_TO_NEW,
        ),
        TablePlan(
            legacy_name="Performance",
            chinese_name=bf.TABLE_PERFORMANCE,
            env_var="FEISHU_PERFORMANCE_TABLE_ID",
            field_map=bf.PERFORMANCE_LEGACY_TO_NEW,
        ),
    ]

    client = FeishuClient()
    renamed_fields = 0
    missing_fields_total = 0
    failed = 0

    print(f"[飞书中文化] app_token={app_token[:8]}… dry_run={args.dry_run} audit_only={args.audit_only}")
    print()

    for plan in plans:
        table_id = _resolve_table_id(client, app_token, plan)
        if not table_id:
            print(f"[缺失] {plan.legacy_name} / {plan.chinese_name}: 找不到表，env={plan.env_var}")
            failed += 1
            continue

        print(f"## {plan.legacy_name} -> {plan.chinese_name} ({table_id})")

        tables = client.bitable_list_tables(app_token)
        current = next((t for t in tables if t.get("table_id") == table_id), {})
        current_name = current.get("name") or plan.legacy_name
        if current_name == plan.chinese_name:
            print(f"  [表名] 已是中文：{plan.chinese_name}")
        else:
            print(f"  [表名] 当前：{current_name}；建议在飞书 UI 手动改为：{plan.chinese_name}")

        fields = client.bitable_list_fields(app_token, table_id)
        by_name = {field.get("field_name"): field for field in fields}
        ok, legacy, missing = _audit_fields(fields, plan.field_map)
        missing_fields_total += len(missing)

        print(f"  [字段审计] 中文={len(ok)} 待重命名={len(legacy)} 缺失={len(missing)}")
        for item in missing:
            print(f"    [缺字段] {item}")

        if args.audit_only:
            continue

        for english in legacy:
            chinese = plan.field_map[english]
            field = by_name[english]
            field_id = field.get("field_id")
            field_type = field.get("type")
            if not field_id:
                failed += 1
                print(f"    [跳过] {english}: 缺 field_id")
                continue
            if args.dry_run:
                print(f"    [字段计划] {english} -> {chinese}")
                continue
            try:
                client.bitable_update_field(
                    app_token,
                    table_id,
                    field_id,
                    field_name=chinese,
                    field_type=field_type,
                )
                renamed_fields += 1
                print(f"    [字段已改] {english} -> {chinese}")
            except Exception as exc:
                failed += 1
                print(f"    [字段失败] {english}: {exc}")
        print()

    print(
        f"[汇总] renamed_fields={renamed_fields} "
        f"missing_fields={missing_fields_total} failed={failed}"
    )
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
