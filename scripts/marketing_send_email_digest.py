"""Manually trigger the Sentinel Daily Market Radar email job.

Defaults are paranoid by design:
  * dry-run unless ``--live`` is passed
  * single recipient unless ``--allow-bulk`` is also passed
  * Resend HTTP call is suppressed in dry-run

Usage::

    # Dry-run for a single recipient — prints subject/preview only.
    worker/.venv/Scripts/python.exe scripts/marketing_send_email_digest.py \\
        --only-email 372768498@qq.com

    # Live send to one recipient only — the production smoke shape.
    worker/.venv/Scripts/python.exe scripts/marketing_send_email_digest.py \\
        --live --only-email 372768498@qq.com

    # Dry-run over the next 50 verified leads (no Resend traffic).
    worker/.venv/Scripts/python.exe scripts/marketing_send_email_digest.py \\
        --limit 50

    # Bulk live — guarded behind two explicit flags AND a hard confirmation.
    worker/.venv/Scripts/python.exe scripts/marketing_send_email_digest.py \\
        --live --allow-bulk --limit 50 --confirm-bulk

The script never reads ``MARKETING_PUBLISH_DRY_RUN`` (Telegram kill-switch)
and never publishes to Telegram, X, or Feishu review.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
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


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--only-email",
        default=None,
        help="Restrict the send to a single verified email (recommended for smoke).",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--live",
        action="store_true",
        help="Actually POST to Resend. Default is dry-run.",
    )
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Explicit dry-run. This is the default already; provided for clarity.",
    )
    parser.add_argument(
        "--allow-bulk",
        action="store_true",
        help="Permit live send without --only-email. Required for cron-style fan-out.",
    )
    parser.add_argument(
        "--confirm-bulk",
        action="store_true",
        help="Required (along with --live --allow-bulk) for bulk live sends.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Max verified leads to scan when --only-email is not set (default 50).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the result dict as JSON instead of a human summary.",
    )
    return parser.parse_args()


def _enforce_live_guards(args: argparse.Namespace) -> Optional[str]:
    if not args.live:
        return None
    if args.only_email:
        return None
    if not args.allow_bulk:
        return (
            "Refusing live bulk send: pass --allow-bulk to confirm intent, "
            "or restrict via --only-email."
        )
    if not args.confirm_bulk:
        return (
            "Refusing live bulk send: pass --confirm-bulk to acknowledge "
            "this will email every verified EmailLead."
        )
    return None


def _print_human_summary(stats: dict) -> None:
    print()
    print("─" * 60)
    print(f"  session            : {stats['session']}")
    print(f"  mode               : {stats['mode']}")
    print(f"  only_email         : {stats.get('only_email')}")
    print(f"  leads_queried      : {stats['leads_queried']}")
    print(f"  leads_eligible     : {stats['leads_eligible']}")
    print(f"  sent               : {stats['sent']}")
    print(f"  skipped_unverified : {stats['skipped_unverified']}")
    if stats["errors"]:
        print(f"  errors             :")
        for err in stats["errors"]:
            print(f"    - {err}")
    if stats["renders"]:
        print(f"  renders            :")
        for r in stats["renders"]:
            print(f"    - {r['email']} → [{r['branch']}] {r['subject']}")
    print("─" * 60)


def main() -> int:
    args = _parse_args()

    _load_env_local(REPO_ROOT / ".env.local")
    _load_env_local(WORKER_DIR / ".env.local")

    # Defensive: explicit --dry-run and no --live → dry-run wins; --live wins
    # over --dry-run via the mutually exclusive group.
    live = bool(args.live)

    refusal = _enforce_live_guards(args)
    if refusal:
        print(f"[email-digest] {refusal}", file=sys.stderr)
        return 2

    if not WORKER_DIR.exists():
        print(f"[email-digest] worker dir not found: {WORKER_DIR}", file=sys.stderr)
        return 1
    sys.path.insert(0, str(WORKER_DIR))

    from app.marketing.email_jobs import send_email_digest

    stats = asyncio.run(
        send_email_digest(
            only_email=args.only_email,
            live=live,
            allow_bulk=args.allow_bulk,
            limit=args.limit,
        )
    )

    if args.json:
        print(json.dumps(stats, indent=2, default=str))
    else:
        _print_human_summary(stats)

    return 0 if not stats["errors"] else 1


if __name__ == "__main__":
    sys.exit(main())
