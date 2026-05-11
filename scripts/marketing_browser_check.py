"""Browser QA harness — verify CTA landing pages BEFORE flipping Telegram live.

Three modes:

  # Single URL
  worker/.venv/Scripts/python.exe scripts/marketing_browser_check.py \\
      --url https://sentinel.example.com/stocks/NVDA

  # Pull recent Feishu Content Queue rows and check each cta_url
  worker/.venv/Scripts/python.exe scripts/marketing_browser_check.py \\
      --from-feishu --limit 10

  # Same, then push a summary card to the review chat
  worker/.venv/Scripts/python.exe scripts/marketing_browser_check.py \\
      --from-feishu --limit 10 --notify-feishu

Screenshots default to:
    D:/code2026/sentinel-ai/获客系统/automation/browser-qa/screenshots/

Use --no-screenshot to skip screenshot capture.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKER_DIR = REPO_ROOT / "worker"
DEFAULT_SCREENSHOT_DIR = REPO_ROOT / "获客系统" / "automation" / "browser-qa" / "screenshots"


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


def _build_summary_card(
    results: list, total: int, passed: int, failed: int
) -> dict:
    failed_blocks = []
    for r in results:
        if r.ok:
            continue
        reason_bits = []
        if r.error:
            reason_bits.append(r.error)
        for name, value in r.checks.items():
            if not value and name in ("email_gate", "disclaimer", "ticker_reference", "http_ok"):
                reason_bits.append(f"missing {name}")
        reason = "; ".join(reason_bits) or "unknown"
        failed_blocks.append(
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**Failed**: `{r.url}`\nReason: {reason}",
                },
            }
        )
    if not failed_blocks:
        failed_blocks = [
            {
                "tag": "div",
                "text": {"tag": "lark_md", "content": "_All checked pages passed ✅_"},
            }
        ]

    elements = [
        {
            "tag": "div",
            "fields": [
                {"is_short": True, "text": {"tag": "lark_md", "content": f"**Checked**\n{total}"}},
                {"is_short": True, "text": {"tag": "lark_md", "content": f"**Passed**\n{passed}"}},
                {"is_short": True, "text": {"tag": "lark_md", "content": f"**Failed**\n{failed}"}},
                {"is_short": True, "text": {"tag": "lark_md", "content": f"**Run**\n`marketing_browser_check.py`"}},
            ],
        },
        {"tag": "hr"},
    ] + failed_blocks

    template = "green" if failed == 0 else "orange" if failed < total else "red"
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": "Sentinel AI · Browser QA"},
            "template": template,
        },
        "elements": elements,
    }


async def _run_checks(
    urls: list[tuple[str, str | None]],  # (url, expected_ticker)
    *,
    screenshot_dir: Path | None,
    require_telegram_cta: bool,
):
    from app.marketing.browser_qa import check_landing_url

    results = []
    for url, ticker in urls:
        result = await check_landing_url(
            url,
            screenshot_dir=str(screenshot_dir) if screenshot_dir else None,
            require_telegram_cta=require_telegram_cta,
            expected_ticker=ticker,
        )
        results.append(result)
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--url", help="Single URL to check")
    src.add_argument(
        "--from-feishu",
        action="store_true",
        help="Pull recent Content Queue rows and check each cta_url",
    )
    parser.add_argument("--limit", type=int, default=10, help="Max Feishu rows to check")
    parser.add_argument(
        "--notify-feishu",
        action="store_true",
        help="Push QA summary card to the review chat",
    )
    parser.add_argument("--screenshot-dir", default=str(DEFAULT_SCREENSHOT_DIR))
    parser.add_argument("--no-screenshot", action="store_true")
    parser.add_argument("--require-telegram-cta", action="store_true")
    parser.add_argument("--ticker", help="Expected ticker for --url mode")
    args = parser.parse_args()

    _load_env_local(REPO_ROOT / ".env.local")
    sys.path.insert(0, str(WORKER_DIR))

    from app.marketing.browser_qa import (
        PLAYWRIGHT_AVAILABLE,
        extract_cta_rows,
    )

    if not PLAYWRIGHT_AVAILABLE:
        print("[error] playwright not installed in this Python env.", file=sys.stderr)
        print("        Install via worker requirements: `uv pip install playwright`", file=sys.stderr)
        return 2

    screenshot_dir: Path | None = None
    if not args.no_screenshot:
        screenshot_dir = Path(args.screenshot_dir)
        screenshot_dir.mkdir(parents=True, exist_ok=True)

    if args.url:
        urls: list[tuple[str, str | None]] = [(args.url, args.ticker)]
    else:
        from app.marketing.feishu_client import FeishuAPIError, FeishuClient, FeishuConfigError

        app_token = os.environ.get("FEISHU_BITABLE_APP_TOKEN", "").strip()
        queue_table = os.environ.get("FEISHU_CONTENT_QUEUE_TABLE_ID", "").strip()
        if not app_token or not queue_table:
            print(
                "[error] FEISHU_BITABLE_APP_TOKEN + FEISHU_CONTENT_QUEUE_TABLE_ID required for --from-feishu",
                file=sys.stderr,
            )
            return 2

        try:
            client = FeishuClient()
            page = client.bitable_list_records(app_token, queue_table, page_size=100)
        except (FeishuConfigError, FeishuAPIError) as exc:
            print(f"[error] Feishu fetch failed: {exc}", file=sys.stderr)
            return 1

        rows = extract_cta_rows(page.get("items", []), limit=args.limit)
        if not rows:
            print("[browser-qa] no Content Queue rows with cta_url — nothing to check.")
            return 0
        urls = [(row.cta_url, row.ticker or None) for row in rows]
        print(f"[browser-qa] pulled {len(rows)} cta_url(s) from Feishu Content Queue")

    print(f"[browser-qa] checking {len(urls)} URL(s)...")
    results = asyncio.run(
        _run_checks(
            urls,
            screenshot_dir=screenshot_dir,
            require_telegram_cta=args.require_telegram_cta,
        )
    )

    passed = sum(1 for r in results if r.ok)
    failed = len(results) - passed
    print()
    print("─" * 60)
    for r in results:
        marker = "PASS" if r.ok else "FAIL"
        status_str = str(r.status_code) if r.status_code else "—"
        print(f"[{marker}] HTTP {status_str:>3s}  {r.url}")
        if not r.ok:
            if r.error:
                print(f"        error: {r.error}")
            for name, value in r.checks.items():
                if not value:
                    print(f"        missing: {name}")
        if r.screenshot_path:
            print(f"        screenshot: {r.screenshot_path}")
    print("─" * 60)
    print(f"Total: {len(results)} · Passed: {passed} · Failed: {failed}")

    if args.notify_feishu:
        try:
            from app.marketing.feishu_client import FeishuClient

            FeishuClient().send_card(_build_summary_card(results, len(results), passed, failed))
            print("[browser-qa] summary card posted to Feishu review chat")
        except Exception as exc:
            print(f"[warn] notify-feishu failed: {exc}", file=sys.stderr)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
