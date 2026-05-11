"""Send a one-shot test message to the Feishu review chat.

Usage (from repo root):

    python scripts/feishu/push_test_message.py

Reads FEISHU_APP_ID / FEISHU_APP_SECRET / FEISHU_REVIEW_CHAT_ID (or
FEISHU_BOT_WEBHOOK_URL) from process env. If `.env.local` exists, its KEY=VALUE
lines are loaded into env without overriding values already set.
"""

from __future__ import annotations

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
    _load_env_local(REPO_ROOT / ".env.local")

    sys.path.insert(0, str(WORKER_DIR))
    try:
        from app.marketing.feishu_client import FeishuClient, FeishuConfigError, FeishuAPIError
    except ImportError as exc:
        print(f"[error] Cannot import feishu_client: {exc}", file=sys.stderr)
        print(f"        Make sure {WORKER_DIR / 'app' / 'marketing' / 'feishu_client.py'} exists.", file=sys.stderr)
        return 2

    try:
        client = FeishuClient()
    except FeishuConfigError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 2

    mode = "webhook" if client.config.webhook_url else "openapi"
    target = "webhook_url" if mode == "webhook" else f"chat_id={client.config.chat_id}"
    print(f"[feishu] sending via {mode} → {target}")

    try:
        data = client.send_text("Sentinel AI Feishu bot connected.")
    except FeishuAPIError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 1

    print(f"[ok] response: {data}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
