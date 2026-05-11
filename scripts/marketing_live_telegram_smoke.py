"""End-to-end Telegram publish smoke.

Walks one mock NVDA opportunity through:
    Content Factory → Feishu Review → auto-Approve → poller → Telegram publish

By default everything is dry-run safe — pass --live with explicit
MARKETING_PUBLISH_DRY_RUN=false AND a typed confirmation string to actually
post to the Telegram channel.

Usage:
    # Default — dry-run, no real Telegram traffic
    worker/.venv/Scripts/python.exe scripts/marketing_live_telegram_smoke.py

    # Real Telegram post (requires kill-switch + interactive confirmation)
    MARKETING_PUBLISH_DRY_RUN=false \\
    worker/.venv/Scripts/python.exe scripts/marketing_live_telegram_smoke.py --live
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKER_DIR = REPO_ROOT / "worker"

CONFIRM_PHRASE = "yes-publish-to-telegram"


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


def _is_dry_run() -> bool:
    raw = os.environ.get("MARKETING_PUBLISH_DRY_RUN", "true").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def _gate_live(args) -> str | None:
    if not args.live:
        return None
    if _is_dry_run():
        return (
            "--live requires MARKETING_PUBLISH_DRY_RUN=false. "
            "Currently DRY-RUN, aborting before any network call."
        )
    if args.assume_yes:
        return None
    print(
        f"You are about to publish a REAL Telegram post.\n"
        f"Type '{CONFIRM_PHRASE}' to continue, anything else to abort: ",
        end="",
        flush=True,
    )
    try:
        answer = input().strip()
    except EOFError:
        return "no tty available — pass --assume-yes if running unattended"
    if answer != CONFIRM_PHRASE:
        return "confirmation phrase did not match — aborted"
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="Allow real Telegram publish")
    parser.add_argument("--assume-yes", action="store_true", help="Skip interactive confirm")
    parser.add_argument("--ticker", default="NVDA")
    args = parser.parse_args()

    _load_env_local(REPO_ROOT / ".env.local")
    sys.path.insert(0, str(WORKER_DIR))

    gate_err = _gate_live(args)
    if gate_err:
        print(f"[error] {gate_err}", file=sys.stderr)
        return 2

    from app.marketing.jobs import generate_daily_review_drafts
    from app.marketing.opportunities import (
        ACTION_CREATE_CONTENT,
        INTENT_TICKER_BUZZ,
        Opportunity,
    )
    from app.marketing.review_queue import submit_draft_to_review
    from app.marketing.review_poller import run_once_sync

    today = datetime.now(timezone.utc).strftime("%Y%m%d")

    async def smoke_scanner(_unused, *, min_score: int = 70):
        return [
            Opportunity(
                opportunity_id=f"OP-SMOKE-{today}-{args.ticker}",
                source="manual",
                ticker=args.ticker,
                intent=INTENT_TICKER_BUZZ,
                raw_text=f"${args.ticker} live telegram smoke test",
                url=None,
                author_id=None,
                opportunity_score=85,
                compliance_risk=5,
                suggested_action=ACTION_CREATE_CONTENT,
                evidence={"smoke": True},
            )
        ]

    mode = "DRY-RUN" if _is_dry_run() else "LIVE"
    print(f"[smoke] mode={mode} ticker={args.ticker}")

    print("[smoke] step 1/3 — generating drafts via Content Factory…")
    result = asyncio.run(
        generate_daily_review_drafts(
            session_label=f"telegram_smoke_{today}",
            scanner=smoke_scanner,
            submit_fn=submit_draft_to_review,
        )
    )
    print(
        f"        opportunities={result['opportunities']} "
        f"drafts={result['drafts_created']} submitted={result['submitted_to_review']}"
    )
    if result["errors"]:
        for e in result["errors"]:
            print(f"        [error] {e}", file=sys.stderr)
        return 1

    print("[smoke] step 2/3 — auto-Approving the Telegram draft…")
    content_id = f"CT-{today}-{args.ticker.upper()}-tg"
    from app.marketing.feishu_client import FeishuClient

    fb = FeishuClient()
    app_token = os.environ["FEISHU_BITABLE_APP_TOKEN"]
    queue_id = os.environ["FEISHU_CONTENT_QUEUE_TABLE_ID"]
    page = fb.bitable_list_records(app_token, queue_id, page_size=100)
    target = None
    for record in page.get("items", []):
        rec_cid = record.get("fields", {}).get("content_id")
        if isinstance(rec_cid, list):
            rec_cid = "".join(s.get("text", "") for s in rec_cid if isinstance(s, dict))
        if rec_cid == content_id:
            target = record
    if target is None:
        print(
            f"[error] could not find Telegram draft {content_id} in Bitable",
            file=sys.stderr,
        )
        return 1
    fb.bitable_update_record(app_token, queue_id, target["record_id"], {"review_status": "Approved"})
    print(f"        {target['record_id']} review_status=Approved")

    print("[smoke] step 3/3 — running review_poller (Telegram publish path)…")
    poll_result = run_once_sync()
    print(
        f"        scanned={poll_result.scanned} "
        f"processed={len(poll_result.processed)} failed={len(poll_result.failed)}"
    )
    for o in poll_result.processed:
        print(f"        [{o['outcome']}] {o['content_id']} → {o.get('published_url')}")
    for f in poll_result.failed:
        print(f"        [failed] {f['content_id']}: {f.get('reason')}", file=sys.stderr)

    if poll_result.failed:
        return 1
    print(f"[smoke] OK — mode={mode} run complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
