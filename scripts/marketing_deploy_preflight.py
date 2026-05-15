"""Pre-deployment safety checks for the Sentinel AI Growth OS worker.

Runs locally with the same .env.local you intend to copy to Railway.
Reports PASS / WARN / FAIL for each subsystem and exits non-zero on any FAIL.

Usage:
    worker/.venv/Scripts/python.exe scripts/marketing_deploy_preflight.py
    worker/.venv/Scripts/python.exe scripts/marketing_deploy_preflight.py --send-feishu-test
    worker/.venv/Scripts/python.exe scripts/marketing_deploy_preflight.py --send-telegram-test

No real network call is made unless --send-* is passed. Secrets are never
printed — env values are reported only as `present` / `missing`.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKER_DIR = REPO_ROOT / "worker"

OK = "PASS"
WARN = "WARN"
FAIL = "FAIL"


@dataclass
class Check:
    name: str
    status: str
    detail: str = ""


@dataclass
class Report:
    checks: list[Check] = field(default_factory=list)

    def add(self, name: str, status: str, detail: str = "") -> None:
        self.checks.append(Check(name=name, status=status, detail=detail))

    @property
    def failed(self) -> bool:
        return any(c.status == FAIL for c in self.checks)

    def print_report(self) -> None:
        col_status_w = max(len(OK), len(WARN), len(FAIL))
        col_name_w = max((len(c.name) for c in self.checks), default=20)
        for c in self.checks:
            marker = c.status.ljust(col_status_w)
            line = f"[{marker}] {c.name.ljust(col_name_w)}  {c.detail}".rstrip()
            print(line)


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


def _present(var: str) -> bool:
    return bool(os.environ.get(var, "").strip())


def _bool_env(var: str, default: bool) -> bool:
    raw = os.environ.get(var, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _check_feishu(report: Report) -> None:
    required = (
        "FEISHU_APP_ID",
        "FEISHU_APP_SECRET",
        "FEISHU_REVIEW_CHAT_ID",
        "FEISHU_BITABLE_APP_TOKEN",
        "FEISHU_CONTENT_QUEUE_TABLE_ID",
        "FEISHU_PERFORMANCE_TABLE_ID",
    )
    missing = [v for v in required if not _present(v)]
    if missing:
        report.add(
            "feishu_review_hub",
            FAIL,
            f"missing: {', '.join(missing)} — review queue + digest will fail",
        )
    else:
        report.add("feishu_review_hub", OK, "all Feishu env present")


def _check_anthropic(report: Report) -> None:
    if not _present("ANTHROPIC_API_KEY"):
        report.add(
            "anthropic_composer",
            FAIL,
            "ANTHROPIC_API_KEY missing — content factory will refuse to run",
        )
        return
    extras = []
    if _present("ANTHROPIC_BASE_URL"):
        extras.append(f"proxy={os.environ['ANTHROPIC_BASE_URL']}")
    if _present("MARKETING_COMPOSER_MODEL"):
        extras.append(f"model={os.environ['MARKETING_COMPOSER_MODEL']}")
    detail = "key present" + (f" ({', '.join(extras)})" if extras else "")
    report.add("anthropic_composer", OK, detail)


def _check_database(report: Report) -> None:
    if _present("DATABASE_URL"):
        # don't reveal it; just show driver scheme
        url = os.environ["DATABASE_URL"]
        scheme = url.split("://", 1)[0] if "://" in url else "unknown"
        report.add("database_url", OK, f"scheme={scheme}")
    else:
        report.add(
            "database_url",
            FAIL,
            "DATABASE_URL missing — KPI aggregator cannot read Postgres",
        )


def _check_publish_kill_switch(report: Report) -> None:
    dry_run = _bool_env("MARKETING_PUBLISH_DRY_RUN", True)
    mode = "DRY-RUN" if dry_run else "LIVE"
    severity = OK if dry_run else WARN
    detail = f"MARKETING_PUBLISH_DRY_RUN={'true' if dry_run else 'false'} ({mode})"
    if not dry_run:
        detail += " — real Telegram posts WILL be sent"
    report.add("publish_kill_switch", severity, detail)


def _check_telegram(report: Report) -> None:
    dry_run = _bool_env("MARKETING_PUBLISH_DRY_RUN", True)

    token = _present("TELEGRAM_BOT_TOKEN")
    chat_id = _present("TELEGRAM_CHANNEL_ID_PUBLIC")
    handle = _present("TELEGRAM_CHANNEL_HANDLE")
    target = chat_id or handle

    if dry_run:
        if not token and not target:
            report.add(
                "telegram_target",
                WARN,
                "no token/channel — dry-run still works but live cutover blocked",
            )
        else:
            bits = []
            if token:
                bits.append("token=present")
            if chat_id:
                bits.append("chat_id=present")
            if handle:
                bits.append(f"handle={os.environ['TELEGRAM_CHANNEL_HANDLE']}")
            report.add("telegram_target", OK, ", ".join(bits) if bits else "dry-run only")
        return

    # LIVE mode — both pieces required
    missing = []
    if not token:
        missing.append("TELEGRAM_BOT_TOKEN")
    if not target:
        missing.append("TELEGRAM_CHANNEL_ID_PUBLIC or TELEGRAM_CHANNEL_HANDLE")
    if missing:
        report.add(
            "telegram_target",
            FAIL,
            f"LIVE mode requires: {', '.join(missing)}",
        )
    else:
        bits = ["token=present"]
        if chat_id:
            bits.append("chat_id=present")
        if handle:
            bits.append(f"handle={os.environ['TELEGRAM_CHANNEL_HANDLE']}")
        report.add("telegram_target", OK, ", ".join(bits) + " — LIVE")


def _check_x(report: Report) -> None:
    global_dry_run = _bool_env("MARKETING_PUBLISH_DRY_RUN", True)
    x_dry_run = _bool_env("X_DRY_RUN", True)
    bearer = _present("X_BEARER_TOKEN")
    oauth_vars = (
        "X_API_KEY",
        "X_API_SECRET",
        "X_ACCESS_TOKEN",
        "X_ACCESS_TOKEN_SECRET",
    )
    missing_oauth = [v for v in oauth_vars if not _present(v)]

    if bearer:
        report.add("x_read_signal", OK, "X_BEARER_TOKEN present")
    else:
        report.add(
            "x_read_signal",
            WARN,
            "X_BEARER_TOKEN missing - official X search adapter cannot read signals",
        )

    if global_dry_run or x_dry_run:
        bits = [
            f"MARKETING_PUBLISH_DRY_RUN={'true' if global_dry_run else 'false'}",
            f"X_DRY_RUN={'true' if x_dry_run else 'false'}",
        ]
        if missing_oauth:
            bits.append(f"live blocked by missing: {', '.join(missing_oauth)}")
        else:
            bits.append("OAuth keys present")
        report.add("x_publish", OK, ", ".join(bits))
        return

    if missing_oauth:
        report.add("x_publish", FAIL, f"LIVE X requires: {', '.join(missing_oauth)}")
    else:
        report.add("x_publish", OK, "LIVE X enabled; OAuth keys present")


def _check_intelligence_sources(report: Report) -> None:
    p0_sources = {
        "fmp": _present("FMP_API_KEY"),
        "sec": _present("SEC_API_KEY") or _present("SEC_USER_AGENT"),
        "x_serp": _present("DATAFORSEO_LOGIN") and _present("DATAFORSEO_PASSWORD"),
        "tavily": _present("TAVILY_API_KEY"),
        "youtube": _present("YOUTUBE_DATA_API_KEY"),
    }
    present = [name for name, ok in p0_sources.items() if ok]
    missing = [name for name, ok in p0_sources.items() if not ok]
    if len(present) >= 3:
        report.add(
            "intelligence_sources",
            OK,
            f"present: {', '.join(present)}; missing optional: {', '.join(missing) or 'none'}",
        )
        return
    report.add(
        "intelligence_sources",
        WARN,
        f"only {len(present)} P0 source(s) present: {', '.join(present) or 'none'}; add: {', '.join(missing)}",
    )


def _check_scheduler_flags(report: Report) -> None:
    queue_enabled = _bool_env("MARKETING_QUEUE_POLL_ENABLED", False)
    digest_enabled = _bool_env("MARKETING_DAILY_DIGEST_ENABLED", False)
    daily_drafts = _bool_env("MARKETING_DAILY_DRAFT_ENABLED", False)
    always_on = _bool_env("MARKETING_ALWAYS_ON_DRAFT_ENABLED", False)
    interval = os.environ.get("MARKETING_QUEUE_POLL_INTERVAL_SECONDS", "300")
    digest_hour = os.environ.get("MARKETING_DAILY_DIGEST_HOUR_ET", "16")
    digest_minute = os.environ.get("MARKETING_DAILY_DIGEST_MINUTE_ET", "30")
    always_on_interval = os.environ.get("MARKETING_ALWAYS_ON_DRAFT_INTERVAL_MINUTES", "180")

    parts = [
        f"daily_drafts={'on' if daily_drafts else 'off'}",
        f"always_on={'on' if always_on else 'off'}({always_on_interval}m)",
        f"queue_poll={'on' if queue_enabled else 'off'}({interval}s)",
        f"daily_digest={'on' if digest_enabled else 'off'}({digest_hour}:{digest_minute} ET)",
    ]
    severity = OK
    if not any((queue_enabled, digest_enabled, daily_drafts, always_on)):
        severity = WARN
        parts.append("(both off — scheduler will have no marketing jobs)")
    report.add("scheduler_flags", severity, ", ".join(parts))


def _check_growth_os_public_url(report: Report) -> None:
    url = os.environ.get("GROWTH_OS_PUBLIC_URL", "").strip()
    if not url:
        report.add(
            "growth_os_public_url",
            WARN,
            "GROWTH_OS_PUBLIC_URL unset — CTA links default to http://localhost:3000",
        )
    elif url.startswith("http://localhost"):
        report.add(
            "growth_os_public_url",
            WARN,
            f"{url} — looks like local override; production should point to Vercel domain",
        )
    else:
        report.add("growth_os_public_url", OK, url)


async def _send_feishu_test(report: Report) -> None:
    sys.path.insert(0, str(WORKER_DIR))
    try:
        from app.marketing.feishu_client import FeishuAPIError, FeishuClient, FeishuConfigError
    except ImportError as exc:
        report.add("feishu_test_message", FAIL, f"import failed: {exc}")
        return

    try:
        client = FeishuClient()
        client.send_text("Sentinel AI · preflight smoke (no-op test)")
    except FeishuConfigError as exc:
        report.add("feishu_test_message", FAIL, str(exc))
    except FeishuAPIError as exc:
        report.add("feishu_test_message", FAIL, f"Feishu API error: {exc}")
    except Exception as exc:
        report.add("feishu_test_message", FAIL, f"unexpected: {exc}")
    else:
        report.add("feishu_test_message", OK, "sent successfully")


async def _send_telegram_test(report: Report) -> None:
    if _bool_env("MARKETING_PUBLISH_DRY_RUN", True):
        report.add(
            "telegram_test_message",
            FAIL,
            "blocked: MARKETING_PUBLISH_DRY_RUN=true. Set it to false to test live.",
        )
        return
    sys.path.insert(0, str(WORKER_DIR))
    try:
        from app.telegram import TelegramConfigError, send_channel_message
    except ImportError as exc:
        report.add("telegram_test_message", FAIL, f"import failed: {exc}")
        return

    try:
        await send_channel_message(
            "<b>Sentinel AI · preflight smoke</b>\nIgnore — this is a deploy preflight test.",
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
    except TelegramConfigError as exc:
        report.add("telegram_test_message", FAIL, str(exc))
    except Exception as exc:
        report.add("telegram_test_message", FAIL, f"send failed: {exc}")
    else:
        report.add("telegram_test_message", OK, "posted to channel")


def main() -> int:
    parser = argparse.ArgumentParser(description="Sentinel AI deployment preflight")
    parser.add_argument(
        "--send-feishu-test",
        action="store_true",
        help="Send a single test message to the Feishu review chat (real network call)",
    )
    parser.add_argument(
        "--send-telegram-test",
        action="store_true",
        help="Send a single test message to the Telegram channel (requires LIVE mode)",
    )
    args = parser.parse_args()

    _load_env_local(REPO_ROOT / ".env.local")

    report = Report()
    _check_database(report)
    _check_anthropic(report)
    _check_feishu(report)
    _check_publish_kill_switch(report)
    _check_telegram(report)
    _check_x(report)
    _check_intelligence_sources(report)
    _check_scheduler_flags(report)
    _check_growth_os_public_url(report)

    if args.send_feishu_test:
        asyncio.run(_send_feishu_test(report))
    if args.send_telegram_test:
        asyncio.run(_send_telegram_test(report))

    print()
    report.print_report()
    print()
    if report.failed:
        print("Preflight FAILED — fix the FAIL items before deploying.", file=sys.stderr)
        return 1
    warns = [c for c in report.checks if c.status == WARN]
    if warns:
        print(f"Preflight passed with {len(warns)} warning(s).")
    else:
        print("Preflight PASSED — safe to deploy.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
