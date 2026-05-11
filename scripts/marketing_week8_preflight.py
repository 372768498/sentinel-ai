"""Week 8 preflight — one command to verify Railway-readiness.

Wraps three existing scripts into a single PASS/WARN/FAIL summary:

  1. marketing_deploy_preflight.py — env shape, kill-switch, target checks
  2. marketing_browser_check.py    — Sentinel landing renders correctly
  3. marketing_intelligence_smoke   — intelligence layer wires up cleanly
                                       (defaults to --no-external so it doesn't
                                       burn paid API quota)

Defaults are conservative:
  - No real network call to Feishu (use --notify-feishu to opt in)
  - No real network call to Anthropic / DataForSEO / Tavily / etc.
  - Browser QA skipped unless --landing-url is provided

Usage:
    worker/.venv/Scripts/python.exe scripts/marketing_week8_preflight.py
    worker/.venv/Scripts/python.exe scripts/marketing_week8_preflight.py --landing-url http://localhost:3000/stocks/NVDA
    worker/.venv/Scripts/python.exe scripts/marketing_week8_preflight.py --notify-feishu
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKER_DIR = REPO_ROOT / "worker"
DEPLOY_PREFLIGHT_PATH = REPO_ROOT / "scripts" / "marketing_deploy_preflight.py"


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


_DEPLOY_MODULE_CACHE = None


def _load_deploy_preflight_module():
    """Import the deploy preflight script as a callable module. Cached so tests
    can monkeypatch a single module instance and have the patch survive."""
    global _DEPLOY_MODULE_CACHE
    if _DEPLOY_MODULE_CACHE is not None:
        return _DEPLOY_MODULE_CACHE
    spec = importlib.util.spec_from_file_location("_w8_deploy_preflight", DEPLOY_PREFLIGHT_PATH)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["_w8_deploy_preflight"] = mod
    spec.loader.exec_module(mod)
    _DEPLOY_MODULE_CACHE = mod
    return mod


PASS = "PASS"
WARN = "WARN"
FAIL = "FAIL"


@dataclass
class SectionResult:
    name: str
    status: str
    detail: str = ""
    sub_checks: list[dict] = field(default_factory=list)


@dataclass
class Week8Report:
    sections: list[SectionResult] = field(default_factory=list)

    def add(self, section: SectionResult) -> None:
        self.sections.append(section)

    @property
    def overall_status(self) -> str:
        statuses = {s.status for s in self.sections}
        if FAIL in statuses:
            return FAIL
        if WARN in statuses:
            return WARN
        return PASS

    @property
    def failed(self) -> bool:
        return any(s.status == FAIL for s in self.sections)

    def print_report(self) -> None:
        print()
        print("=" * 64)
        print(" Sentinel AI · Week 8 Preflight")
        print("=" * 64)
        for section in self.sections:
            marker = f"[{section.status}]".ljust(7)
            print(f"{marker} {section.name}")
            if section.detail:
                print(f"        {section.detail}")
            for sub in section.sub_checks:
                sub_marker = f"  [{sub['status']}]".ljust(9)
                print(f"{sub_marker} {sub['name']}  {sub.get('detail', '')}")
        print("-" * 64)
        print(f" Overall: {self.overall_status}")
        print("=" * 64)


def _run_deploy_preflight(report: Week8Report, *, notify_feishu: bool) -> None:
    """Section 1 — env-shape preflight (no network unless --notify-feishu)."""
    mod = _load_deploy_preflight_module()
    inner_report = mod.Report()
    mod._check_database(inner_report)
    mod._check_anthropic(inner_report)
    mod._check_feishu(inner_report)
    mod._check_publish_kill_switch(inner_report)
    mod._check_telegram(inner_report)
    mod._check_scheduler_flags(inner_report)
    mod._check_growth_os_public_url(inner_report)

    if notify_feishu:
        asyncio.run(mod._send_feishu_test(inner_report))

    sub_checks = [{"status": c.status, "name": c.name, "detail": c.detail} for c in inner_report.checks]
    statuses = {c.status for c in inner_report.checks}
    if FAIL in statuses:
        overall = FAIL
        detail = f"{sum(1 for c in inner_report.checks if c.status == FAIL)} FAIL"
    elif WARN in statuses:
        overall = WARN
        detail = f"{sum(1 for c in inner_report.checks if c.status == WARN)} WARN"
    else:
        overall = PASS
        detail = "all checks PASS"

    report.add(SectionResult(
        name="1. Deploy preflight (env + kill-switch + scheduler flags)",
        status=overall,
        detail=detail,
        sub_checks=sub_checks,
    ))


async def _run_browser_check(report: Week8Report, *, landing_url: Optional[str]) -> None:
    """Section 2 — browser QA against the configured landing page.

    Skipped when --landing-url is not given (WARN, not FAIL, so the wrapper
    can still exit 0 in pure env-validation mode).
    """
    if not landing_url:
        report.add(SectionResult(
            name="2. Browser QA (landing page)",
            status=WARN,
            detail="skipped — pass --landing-url to enable",
        ))
        return

    sys.path.insert(0, str(WORKER_DIR))
    try:
        from app.marketing.browser_qa import PLAYWRIGHT_AVAILABLE, check_landing_url
    except ImportError as exc:
        report.add(SectionResult(
            name="2. Browser QA (landing page)",
            status=FAIL,
            detail=f"import failed: {exc}",
        ))
        return

    if not PLAYWRIGHT_AVAILABLE:
        report.add(SectionResult(
            name="2. Browser QA (landing page)",
            status=FAIL,
            detail="playwright not installed in worker venv",
        ))
        return

    try:
        result = await check_landing_url(landing_url, screenshot_dir=None)
    except Exception as exc:
        report.add(SectionResult(
            name="2. Browser QA (landing page)",
            status=FAIL,
            detail=f"check raised: {exc}",
        ))
        return

    if result.ok:
        status = PASS
        detail = f"HTTP {result.status_code} · all 6 checks passed"
    else:
        # Localhost unreachable → WARN (likely dev server not running)
        if result.error and "fetch_failed" in result.error and "localhost" in landing_url:
            status = WARN
            detail = f"localhost unreachable — start `npm run dev` first (error: {result.error})"
        else:
            status = FAIL
            failing = [k for k, v in result.checks.items() if not v]
            detail = f"failing checks: {', '.join(failing) or result.error or 'unknown'}"

    sub_checks = [
        {"status": PASS if v else FAIL, "name": k, "detail": ""}
        for k, v in result.checks.items()
    ]
    report.add(SectionResult(
        name=f"2. Browser QA · {landing_url}",
        status=status,
        detail=detail,
        sub_checks=sub_checks,
    ))


async def _run_intelligence_smoke(report: Week8Report) -> None:
    """Section 3 — intelligence layer wires up without paid API calls."""
    sys.path.insert(0, str(WORKER_DIR))
    try:
        from app.marketing.intelligence import build_daily_profiles
    except ImportError as exc:
        report.add(SectionResult(
            name="3. Intelligence smoke (--no-external)",
            status=FAIL,
            detail=f"import failed: {exc}",
        ))
        return

    # Strip every paid-API key so all adapters take the graceful-fallback path.
    saved: dict[str, Optional[str]] = {}
    for key in (
        "FMP_API_KEY",
        "SEC_API_KEY",
        "DATAFORSEO_LOGIN",
        "DATAFORSEO_PASSWORD",
        "TAVILY_API_KEY",
        "YOUTUBE_DATA_API_KEY",
    ):
        saved[key] = os.environ.pop(key, None)
    try:
        profiles = await build_daily_profiles(
            seed_tickers=["NVDA", "AAPL"],
            limit=2,
        )
    except Exception as exc:
        report.add(SectionResult(
            name="3. Intelligence smoke (--no-external)",
            status=FAIL,
            detail=f"build_daily_profiles raised: {exc}",
        ))
        return
    finally:
        # Restore
        for key, val in saved.items():
            if val is not None:
                os.environ[key] = val

    if not profiles:
        report.add(SectionResult(
            name="3. Intelligence smoke (--no-external)",
            status=FAIL,
            detail="returned 0 profiles — orchestrator broken",
        ))
        return

    detail = f"orchestrator OK · {len(profiles)} profile(s) built (all graceful-fallback)"
    sub_checks = [
        {
            "status": PASS,
            "name": p.ticker,
            "detail": f"overall={p.overall_opportunity} confidence={p.confidence}",
        }
        for p in profiles
    ]
    report.add(SectionResult(
        name="3. Intelligence smoke (--no-external)",
        status=PASS,
        detail=detail,
        sub_checks=sub_checks,
    ))


async def _run_async(report: Week8Report, *, landing_url: Optional[str]) -> None:
    await _run_browser_check(report, landing_url=landing_url)
    await _run_intelligence_smoke(report)


def main() -> int:
    parser = argparse.ArgumentParser(description="Sentinel AI Week 8 preflight wrapper")
    parser.add_argument(
        "--notify-feishu",
        action="store_true",
        help="Send a single Feishu test message (opt-in network call)",
    )
    parser.add_argument(
        "--landing-url",
        default=None,
        help="If set, run Browser QA against this URL (else skipped with WARN)",
    )
    args = parser.parse_args()

    _load_env_local(REPO_ROOT / ".env.local")

    report = Week8Report()
    # Section 1 — sync env preflight
    try:
        _run_deploy_preflight(report, notify_feishu=args.notify_feishu)
    except Exception as exc:
        report.add(SectionResult(
            name="1. Deploy preflight",
            status=FAIL,
            detail=f"raised: {exc}",
        ))

    # Sections 2 + 3 — async
    asyncio.run(_run_async(report, landing_url=args.landing_url))

    report.print_report()
    print()
    if report.failed:
        print(
            "[next] Fix FAIL items before Railway deploy. "
            "See 获客系统/automation/specs/railway-worker-deploy.md §5.",
            file=sys.stderr,
        )
        return 1
    if any(s.status == WARN for s in report.sections):
        print("[next] Preflight passed with warnings — review WARN items above.")
    else:
        print("[next] Ready for Railway deploy. Continue with railway-post-deploy-smoke.md.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
