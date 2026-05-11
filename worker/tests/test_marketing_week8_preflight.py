"""Unit tests for scripts/marketing_week8_preflight.py + companion docs."""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "marketing_week8_preflight.py"
ENV_TEMPLATE_PATH = REPO_ROOT / "获客系统" / "automation" / "specs" / "railway-env-template.md"
POST_DEPLOY_SMOKE_PATH = REPO_ROOT / "获客系统" / "automation" / "specs" / "railway-post-deploy-smoke.md"


@pytest.fixture
def w8_module(monkeypatch: pytest.MonkeyPatch):
    """Import the Week 8 preflight script as a module under a stable name."""
    # Clear environment so each test starts from a known state
    for var in (
        "DATABASE_URL",
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_BASE_URL",
        "MARKETING_COMPOSER_MODEL",
        "FEISHU_APP_ID",
        "FEISHU_APP_SECRET",
        "FEISHU_REVIEW_CHAT_ID",
        "FEISHU_BITABLE_APP_TOKEN",
        "FEISHU_CONTENT_QUEUE_TABLE_ID",
        "FEISHU_PERFORMANCE_TABLE_ID",
        "MARKETING_PUBLISH_DRY_RUN",
        "MARKETING_QUEUE_POLL_ENABLED",
        "MARKETING_DAILY_DIGEST_ENABLED",
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CHANNEL_ID_PUBLIC",
        "TELEGRAM_CHANNEL_HANDLE",
        "GROWTH_OS_PUBLIC_URL",
        "FMP_API_KEY",
        "SEC_API_KEY",
        "DATAFORSEO_LOGIN",
        "DATAFORSEO_PASSWORD",
        "TAVILY_API_KEY",
        "YOUTUBE_DATA_API_KEY",
    ):
        monkeypatch.delenv(var, raising=False)

    spec = importlib.util.spec_from_file_location("week8_preflight_under_test", SCRIPT_PATH)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["week8_preflight_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


def _by_name(report, prefix: str):
    for s in report.sections:
        if s.name.startswith(prefix):
            return s
    raise AssertionError(f"section starting with '{prefix}' not in report")


# ---------------------------------------------------------------------------
# Documents must exist + contain key markers (catches accidental deletion)
# ---------------------------------------------------------------------------


def test_env_template_doc_exists_and_lists_required_vars() -> None:
    assert ENV_TEMPLATE_PATH.is_file()
    text = ENV_TEMPLATE_PATH.read_text(encoding="utf-8")
    # Spot-check the critical env vars are documented
    for needle in (
        "DATABASE_URL",
        "WORKER_INTERNAL_TOKEN",
        "FEISHU_APP_ID",
        "FEISHU_REVIEW_CHAT_ID",
        "ANTHROPIC_API_KEY",
        "TELEGRAM_BOT_TOKEN",
        "MARKETING_PUBLISH_DRY_RUN",
        "MARKETING_QUEUE_POLL_ENABLED",
        "MARKETING_DAILY_DIGEST_ENABLED",
        "GROWTH_OS_PUBLIC_URL",
    ):
        assert needle in text, f"env template missing {needle}"


def test_post_deploy_smoke_doc_exists_and_has_six_steps() -> None:
    assert POST_DEPLOY_SMOKE_PATH.is_file()
    text = POST_DEPLOY_SMOKE_PATH.read_text(encoding="utf-8")
    for needle in (
        "## Step 1 ·",
        "## Step 2 ·",
        "## Step 3 ·",
        "## Step 4 ·",
        "## Step 5 ·",
        "## Step 6 ·",
        "manual_brief.py",
        "set_record_status.py",
        "poll_review_status.py",
        "marketing_browser_check.py",
        "push_daily_growth_digest.py",
        "MARKETING_PUBLISH_DRY_RUN",
    ):
        assert needle in text, f"post-deploy smoke missing {needle}"


# ---------------------------------------------------------------------------
# Section 1 · deploy_preflight wrapping
# ---------------------------------------------------------------------------


def test_section1_fails_when_all_env_missing(w8_module) -> None:
    report = w8_module.Week8Report()
    w8_module._run_deploy_preflight(report, notify_feishu=False)
    s = _by_name(report, "1. Deploy preflight")
    assert s.status == w8_module.FAIL
    sub_names = [c["name"] for c in s.sub_checks]
    assert "database_url" in sub_names
    assert "feishu_review_hub" in sub_names


def test_section1_passes_when_env_complete(w8_module, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgres://u:p@h/d")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-x")
    for var in (
        "FEISHU_APP_ID",
        "FEISHU_APP_SECRET",
        "FEISHU_REVIEW_CHAT_ID",
        "FEISHU_BITABLE_APP_TOKEN",
        "FEISHU_CONTENT_QUEUE_TABLE_ID",
        "FEISHU_PERFORMANCE_TABLE_ID",
    ):
        monkeypatch.setenv(var, "present")
    monkeypatch.setenv("MARKETING_QUEUE_POLL_ENABLED", "true")
    monkeypatch.setenv("GROWTH_OS_PUBLIC_URL", "https://sentinel.example.com")
    report = w8_module.Week8Report()
    w8_module._run_deploy_preflight(report, notify_feishu=False)
    s = _by_name(report, "1. Deploy preflight")
    assert s.status in (w8_module.PASS, w8_module.WARN)
    # No FAIL sub-checks
    assert not any(c["status"] == w8_module.FAIL for c in s.sub_checks)


def test_section1_does_not_call_feishu_when_notify_false(w8_module, monkeypatch: pytest.MonkeyPatch) -> None:
    """Default behavior: --notify-feishu absent → no Feishu network call."""
    network_calls: list = []

    async def boom(*args, **kwargs):
        network_calls.append(args)

    # Patch the Feishu test sender so any accidental call raises immediately.
    deploy_mod = w8_module._load_deploy_preflight_module()
    monkeypatch.setattr(deploy_mod, "_send_feishu_test", boom)

    report = w8_module.Week8Report()
    w8_module._run_deploy_preflight(report, notify_feishu=False)
    assert network_calls == []


def test_section1_calls_feishu_when_notify_true(w8_module, monkeypatch: pytest.MonkeyPatch) -> None:
    called: list = []

    async def fake_send(report_in):
        called.append(True)
        report_in.add("feishu_test_message", w8_module.PASS, "sent successfully")

    deploy_mod = w8_module._load_deploy_preflight_module()
    monkeypatch.setattr(deploy_mod, "_send_feishu_test", fake_send)

    report = w8_module.Week8Report()
    w8_module._run_deploy_preflight(report, notify_feishu=True)
    assert called == [True]
    s = _by_name(report, "1. Deploy preflight")
    sub_names = [c["name"] for c in s.sub_checks]
    assert "feishu_test_message" in sub_names


# ---------------------------------------------------------------------------
# Section 2 · browser QA gating
# ---------------------------------------------------------------------------


def test_section2_skipped_with_warn_when_landing_url_missing(w8_module) -> None:
    report = w8_module.Week8Report()
    asyncio.run(w8_module._run_browser_check(report, landing_url=None))
    s = _by_name(report, "2. Browser QA")
    assert s.status == w8_module.WARN
    assert "skipped" in s.detail.lower()


def test_section2_fails_when_check_raises(w8_module, monkeypatch: pytest.MonkeyPatch) -> None:
    sys.path.insert(0, str(REPO_ROOT / "worker"))
    import app.marketing.browser_qa as bq

    async def boom(url, **kwargs):
        raise RuntimeError("forced failure for test")

    monkeypatch.setattr(bq, "PLAYWRIGHT_AVAILABLE", True)
    monkeypatch.setattr(bq, "check_landing_url", boom)

    report = w8_module.Week8Report()
    asyncio.run(w8_module._run_browser_check(report, landing_url="https://example.com"))
    s = _by_name(report, "2. Browser QA")
    assert s.status == w8_module.FAIL
    assert "forced failure" in s.detail


def test_section2_warns_when_localhost_unreachable(w8_module, monkeypatch: pytest.MonkeyPatch) -> None:
    sys.path.insert(0, str(REPO_ROOT / "worker"))
    import app.marketing.browser_qa as bq

    fake_result = bq.BrowserCheckResult(
        url="http://localhost:3000/stocks/NVDA",
        ok=False,
        status_code=None,
        title=None,
        checks={},
        screenshot_path=None,
        error="fetch_failed:connection refused",
    )

    async def fake_check(url, **kwargs):
        return fake_result

    monkeypatch.setattr(bq, "PLAYWRIGHT_AVAILABLE", True)
    monkeypatch.setattr(bq, "check_landing_url", fake_check)

    report = w8_module.Week8Report()
    asyncio.run(
        w8_module._run_browser_check(report, landing_url="http://localhost:3000/stocks/NVDA")
    )
    s = _by_name(report, "2. Browser QA")
    assert s.status == w8_module.WARN  # localhost unreachable → WARN not FAIL


def test_section2_passes_on_clean_result(w8_module, monkeypatch: pytest.MonkeyPatch) -> None:
    sys.path.insert(0, str(REPO_ROOT / "worker"))
    import app.marketing.browser_qa as bq

    fake_result = bq.BrowserCheckResult(
        url="https://sentinel.example.com/stocks/NVDA",
        ok=True,
        status_code=200,
        title="Sentinel AI — $NVDA",
        checks={
            "http_ok": True,
            "has_title": True,
            "ticker_reference": True,
            "email_gate": True,
            "disclaimer": True,
            "telegram_cta": True,
        },
        screenshot_path=None,
        error=None,
    )

    async def fake_check(url, **kwargs):
        return fake_result

    monkeypatch.setattr(bq, "PLAYWRIGHT_AVAILABLE", True)
    monkeypatch.setattr(bq, "check_landing_url", fake_check)

    report = w8_module.Week8Report()
    asyncio.run(
        w8_module._run_browser_check(report, landing_url="https://sentinel.example.com/stocks/NVDA")
    )
    s = _by_name(report, "2. Browser QA")
    assert s.status == w8_module.PASS


# ---------------------------------------------------------------------------
# Section 3 · intelligence smoke
# ---------------------------------------------------------------------------


def test_section3_passes_with_no_external_keys(w8_module) -> None:
    """No external API keys → all adapters return [] → orchestrator should
    still synthesize empty profiles without raising."""
    report = w8_module.Week8Report()
    asyncio.run(w8_module._run_intelligence_smoke(report))
    s = _by_name(report, "3. Intelligence smoke")
    assert s.status == w8_module.PASS
    assert "orchestrator OK" in s.detail


def test_section3_restores_keys_after_run(w8_module, monkeypatch: pytest.MonkeyPatch) -> None:
    """The smoke section temporarily strips paid-API keys; verify they're
    restored afterwards so subsequent sections aren't affected."""
    monkeypatch.setenv("FMP_API_KEY", "preserved")
    monkeypatch.setenv("TAVILY_API_KEY", "also-preserved")

    report = w8_module.Week8Report()
    import os
    asyncio.run(w8_module._run_intelligence_smoke(report))

    assert os.environ.get("FMP_API_KEY") == "preserved"
    assert os.environ.get("TAVILY_API_KEY") == "also-preserved"


# ---------------------------------------------------------------------------
# Overall report behavior
# ---------------------------------------------------------------------------


def test_overall_status_fails_if_any_section_fails(w8_module) -> None:
    report = w8_module.Week8Report()
    report.add(w8_module.SectionResult(name="A", status=w8_module.PASS))
    report.add(w8_module.SectionResult(name="B", status=w8_module.FAIL))
    report.add(w8_module.SectionResult(name="C", status=w8_module.WARN))
    assert report.overall_status == w8_module.FAIL
    assert report.failed is True


def test_overall_status_warns_if_no_fail(w8_module) -> None:
    report = w8_module.Week8Report()
    report.add(w8_module.SectionResult(name="A", status=w8_module.PASS))
    report.add(w8_module.SectionResult(name="B", status=w8_module.WARN))
    assert report.overall_status == w8_module.WARN
    assert report.failed is False


def test_overall_status_passes_when_all_pass(w8_module) -> None:
    report = w8_module.Week8Report()
    report.add(w8_module.SectionResult(name="A", status=w8_module.PASS))
    report.add(w8_module.SectionResult(name="B", status=w8_module.PASS))
    assert report.overall_status == w8_module.PASS


def test_secrets_never_appear_in_report(w8_module, monkeypatch: pytest.MonkeyPatch) -> None:
    """Even with secret-looking env values, the rendered report sub-details
    must never contain them — only `present`/`missing`/scheme markers."""
    monkeypatch.setenv("FEISHU_APP_SECRET", "TOP-SECRET-SECRET-MATERIAL")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-LEAKED")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:LIVE-BOT-TOKEN")
    monkeypatch.setenv("DATABASE_URL", "postgres://user:LEAKED-DB-PASSWORD@h:5432/db")
    for var in (
        "FEISHU_APP_ID",
        "FEISHU_REVIEW_CHAT_ID",
        "FEISHU_BITABLE_APP_TOKEN",
        "FEISHU_CONTENT_QUEUE_TABLE_ID",
        "FEISHU_PERFORMANCE_TABLE_ID",
    ):
        monkeypatch.setenv(var, "present")

    report = w8_module.Week8Report()
    w8_module._run_deploy_preflight(report, notify_feishu=False)

    full_dump = " ".join(s.detail for s in report.sections)
    for section in report.sections:
        for sub in section.sub_checks:
            full_dump += " " + sub.get("detail", "")
    for needle in (
        "TOP-SECRET-SECRET-MATERIAL",
        "LEAKED",
        "LIVE-BOT-TOKEN",
        "LEAKED-DB-PASSWORD",
    ):
        assert needle not in full_dump, f"secret leaked: {needle}"
