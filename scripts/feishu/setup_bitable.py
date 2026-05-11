"""One-shot Bitable provisioning for Sentinel AI Growth OS review hub.

Creates one Bitable app + three tables in the bot's personal folder:

  1. Campaigns         — daily review session container
  2. Content Queue     — per-platform draft + redline + review state
  3. Performance       — KPI rollup keyed by content_id

After it runs, paste the printed env vars into `.env.local`.

Idempotency:
  - If `FEISHU_BITABLE_APP_TOKEN` is set in env, the script reuses that app
    and only creates tables that are missing (by name).
  - Otherwise it creates a fresh app.

Required scopes on the Feishu app: `bitable:app`, `im:message:send`.
(`bitable:app` is the umbrella scope; alternatively `base:app:create` +
`base:table:create` work for a minimal grant.)
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


APP_NAME = "Sentinel AI Growth OS"

CAMPAIGNS_FIELDS: list[dict] = [
    {"field_name": "campaign_id", "type": 1},
    {
        "field_name": "date",
        "type": 5,
        "property": {"date_formatter": "yyyy/MM/dd", "auto_fill": False},
    },
    {
        "field_name": "session",
        "type": 3,
        "property": {
            "options": [
                {"name": "Pre-market"},
                {"name": "Midday"},
                {"name": "Post-close"},
                {"name": "Breaking"},
            ]
        },
    },
    {"field_name": "main_ticker", "type": 1},
    {
        "field_name": "status",
        "type": 3,
        "property": {
            "options": [
                {"name": "Draft"},
                {"name": "Review"},
                {"name": "Approved"},
                {"name": "Published"},
                {"name": "Rejected"},
            ]
        },
    },
    {"field_name": "owner", "type": 1},
    {"field_name": "notes", "type": 1},
]

CONTENT_QUEUE_FIELDS: list[dict] = [
    {"field_name": "content_id", "type": 1},
    {"field_name": "campaign_id", "type": 1},
    {
        "field_name": "platform",
        "type": 3,
        "property": {
            "options": [
                {"name": "X"},
                {"name": "Telegram"},
                {"name": "TikTok"},
                {"name": "YouTube Shorts"},
                {"name": "YouTube Long"},
                {"name": "Email"},
            ]
        },
    },
    {"field_name": "ticker", "type": 1},
    {"field_name": "hook", "type": 1},
    {"field_name": "body", "type": 1},
    {"field_name": "cta_url", "type": 15},
    {
        "field_name": "risk_level",
        "type": 3,
        "property": {"options": [{"name": "Low"}, {"name": "Medium"}, {"name": "High"}]},
    },
    {
        "field_name": "redline_result",
        "type": 3,
        "property": {
            "options": [{"name": "Pass"}, {"name": "Needs Edit"}, {"name": "Blocked"}]
        },
    },
    {"field_name": "redline_hits", "type": 1},
    {
        "field_name": "review_status",
        "type": 3,
        "property": {
            "options": [
                {"name": "Pending"},
                {"name": "Approved"},
                {"name": "Rejected"},
                {"name": "Published"},
                {"name": "Failed"},
            ]
        },
    },
    {"field_name": "reviewer_comment", "type": 1},
    {
        "field_name": "publish_time",
        "type": 5,
        "property": {"date_formatter": "yyyy/MM/dd HH:mm", "auto_fill": False},
    },
    {"field_name": "published_url", "type": 15},
]

PERFORMANCE_FIELDS: list[dict] = [
    {"field_name": "content_id", "type": 1},
    {"field_name": "views", "type": 2, "property": {"formatter": "0"}},
    {"field_name": "clicks", "type": 2, "property": {"formatter": "0"}},
    {"field_name": "emails_captured", "type": 2, "property": {"formatter": "0"}},
    {"field_name": "signups", "type": 2, "property": {"formatter": "0"}},
    {"field_name": "paid_users", "type": 2, "property": {"formatter": "0"}},
    {"field_name": "click_to_email_rate", "type": 2, "property": {"formatter": "0.00%"}},
    {"field_name": "free_to_paid_rate", "type": 2, "property": {"formatter": "0.00%"}},
    {"field_name": "cac_estimate", "type": 2, "property": {"formatter": "0.00"}},
    {"field_name": "notes", "type": 1},
]


TARGET_TABLES: list[tuple[str, list[dict]]] = [
    ("Campaigns", CAMPAIGNS_FIELDS),
    ("Content Queue", CONTENT_QUEUE_FIELDS),
    ("Performance", PERFORMANCE_FIELDS),
]

ENV_VAR_FOR_TABLE: dict[str, str] = {
    "Campaigns": "FEISHU_CAMPAIGNS_TABLE_ID",
    "Content Queue": "FEISHU_CONTENT_QUEUE_TABLE_ID",
    "Performance": "FEISHU_PERFORMANCE_TABLE_ID",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Provision Feishu Bitable for Sentinel AI")
    parser.add_argument("--app-token", help="Reuse an existing Bitable app token (overrides env)")
    parser.add_argument("--keep-default", action="store_true", help="Do not delete the default empty table")
    args = parser.parse_args()

    _load_env_local(REPO_ROOT / ".env.local")
    sys.path.insert(0, str(WORKER_DIR))
    try:
        from app.marketing.feishu_client import FeishuClient, FeishuConfigError, FeishuAPIError
    except ImportError as exc:
        print(f"[error] Cannot import feishu_client: {exc}", file=sys.stderr)
        return 2

    try:
        client = FeishuClient()
    except FeishuConfigError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 2

    app_token = (args.app_token or os.environ.get("FEISHU_BITABLE_APP_TOKEN", "")).strip()
    app_url = ""

    if app_token:
        print(f"[1/5] Reusing existing Bitable app (app_token={app_token})")
    else:
        print(f"[1/5] Creating Bitable app '{APP_NAME}' in personal folder...")
        try:
            app = client.bitable_create_app(name=APP_NAME, folder_token="")
        except FeishuAPIError as exc:
            print(f"[error] {exc}", file=sys.stderr)
            return 1
        app_token = app["app_token"]
        app_url = app.get("url", "")
        print(f"       app_token={app_token}")
        print(f"       url={app_url}")

    try:
        existing_tables = client.bitable_list_tables(app_token)
    except FeishuAPIError as exc:
        print(f"[error] list_tables: {exc}", file=sys.stderr)
        return 1
    by_name = {t["name"]: t["table_id"] for t in existing_tables}

    result_ids: dict[str, str] = {}
    for idx, (table_name, fields) in enumerate(TARGET_TABLES, start=2):
        if table_name in by_name:
            result_ids[table_name] = by_name[table_name]
            print(f"[{idx}/5] Table '{table_name}' already exists ({by_name[table_name]}) — skipping")
            continue
        print(f"[{idx}/5] Creating table '{table_name}'...")
        try:
            table_id = client.bitable_create_table(app_token=app_token, name=table_name, fields=fields)
        except FeishuAPIError as exc:
            print(f"[error] {exc}", file=sys.stderr)
            return 1
        result_ids[table_name] = table_id
        print(f"       table_id={table_id}")

    if not args.keep_default:
        print("[5/5] Removing tables that aren't part of the target schema...")
        try:
            current = client.bitable_list_tables(app_token)
            keep_ids = set(result_ids.values())
            target_names = {n for n, _ in TARGET_TABLES}
            for table in current:
                if table["table_id"] not in keep_ids and table["name"] not in target_names:
                    client.bitable_delete_table(app_token, table["table_id"])
                    print(f"       deleted {table['name']} ({table['table_id']})")
        except FeishuAPIError as exc:
            print(f"[warn] cleanup skipped: {exc}", file=sys.stderr)

    print()
    print("─" * 60)
    print("✓ Done. Add these to .env.local (skip lines you already have):")
    print("─" * 60)
    print(f"FEISHU_BITABLE_APP_TOKEN={app_token}")
    for table_name, env_var in ENV_VAR_FOR_TABLE.items():
        print(f"{env_var}={result_ids[table_name]}")
    if app_url:
        print()
        print(f"Open in browser: {app_url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
