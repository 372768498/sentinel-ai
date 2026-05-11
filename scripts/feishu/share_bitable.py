"""Share the Sentinel AI Growth OS Bitable with a Feishu user (by email or mobile).

Usage:

    # by email
    worker/.venv/Scripts/python.exe scripts/feishu/share_bitable.py --email you@example.com

    # by mobile (international format, e.g. +8613800138000)
    worker/.venv/Scripts/python.exe scripts/feishu/share_bitable.py --mobile +8613800138000

Requires Feishu app scopes:
  - contact:user.email:readonly       (resolve email → open_id)   OR
  - contact:user.phone:readonly       (resolve mobile → open_id)
  - drive:drive  OR  drive:permission_member:set                  (add collaborator)

Optional flags:
  --perm view|edit|full_access   default: edit
  --app-token <token>            override FEISHU_BITABLE_APP_TOKEN
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
    parser = argparse.ArgumentParser(description="Share Sentinel AI Bitable with a Feishu user")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--email", help="Feishu user email")
    group.add_argument("--mobile", help="Feishu user mobile (e.g. +8613800138000)")
    parser.add_argument("--perm", default="edit", choices=["view", "edit", "full_access"])
    parser.add_argument("--app-token", help="Override FEISHU_BITABLE_APP_TOKEN")
    args = parser.parse_args()

    _load_env_local(REPO_ROOT / ".env.local")
    sys.path.insert(0, str(WORKER_DIR))
    try:
        from app.marketing.feishu_client import FeishuAPIError, FeishuClient, FeishuConfigError
    except ImportError as exc:
        print(f"[error] Cannot import feishu_client: {exc}", file=sys.stderr)
        return 2

    app_token = (args.app_token or os.environ.get("FEISHU_BITABLE_APP_TOKEN", "")).strip()
    if not app_token:
        print("[error] FEISHU_BITABLE_APP_TOKEN not set (and --app-token not given)", file=sys.stderr)
        return 2

    try:
        client = FeishuClient()
    except FeishuConfigError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 2

    identifier = args.email or args.mobile or ""
    print(f"[1/2] Looking up open_id for {identifier}...")
    try:
        if args.email:
            open_id = client.lookup_user_id_by_email(args.email)
        else:
            open_id = client.lookup_user_id_by_mobile(args.mobile)
    except FeishuAPIError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 1
    if not open_id:
        print(f"[error] No Feishu user found for {identifier}", file=sys.stderr)
        return 1
    print(f"       open_id={open_id}")

    print(f"[2/2] Adding as {args.perm} collaborator on app_token={app_token[:12]}...")
    try:
        client.drive_add_member(
            token=app_token,
            member_type="openid",
            member_id=open_id,
            perm=args.perm,
            file_type="bitable",
        )
    except FeishuAPIError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 1

    print(f"[ok] Bitable shared with {identifier} ({args.perm} permission)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
