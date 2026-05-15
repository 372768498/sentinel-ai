"""Unit tests for scripts/marketing_deploy_preflight.py (import as module)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "marketing_deploy_preflight.py"


@pytest.fixture
def preflight_module(monkeypatch: pytest.MonkeyPatch):
    """Import the CLI script as a module under a stable name."""
    # Reset env on each test
    for var in (
        "DATABASE_URL",
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_BASE_URL",
        "MARKETING_COMPOSER_MODEL",
        "FMP_API_KEY",
        "SEC_API_KEY",
        "SEC_USER_AGENT",
        "DATAFORSEO_LOGIN",
        "DATAFORSEO_PASSWORD",
        "TAVILY_API_KEY",
        "YOUTUBE_DATA_API_KEY",
        "FEISHU_APP_ID",
        "FEISHU_APP_SECRET",
        "FEISHU_REVIEW_CHAT_ID",
        "FEISHU_BITABLE_APP_TOKEN",
        "FEISHU_CONTENT_QUEUE_TABLE_ID",
        "FEISHU_PERFORMANCE_TABLE_ID",
        "MARKETING_PUBLISH_DRY_RUN",
        "X_DRY_RUN",
        "X_BEARER_TOKEN",
        "X_API_KEY",
        "X_API_SECRET",
        "X_ACCESS_TOKEN",
        "X_ACCESS_TOKEN_SECRET",
        "MARKETING_DAILY_DRAFT_ENABLED",
        "MARKETING_ALWAYS_ON_DRAFT_ENABLED",
        "MARKETING_ALWAYS_ON_DRAFT_INTERVAL_MINUTES",
        "MARKETING_QUEUE_POLL_ENABLED",
        "MARKETING_QUEUE_POLL_INTERVAL_SECONDS",
        "MARKETING_DAILY_DIGEST_ENABLED",
        "MARKETING_DAILY_DIGEST_HOUR_ET",
        "MARKETING_DAILY_DIGEST_MINUTE_ET",
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CHANNEL_ID_PUBLIC",
        "TELEGRAM_CHANNEL_HANDLE",
        "GROWTH_OS_PUBLIC_URL",
    ):
        monkeypatch.delenv(var, raising=False)

    spec = importlib.util.spec_from_file_location("preflight_under_test", _SCRIPT_PATH)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    # Must be in sys.modules BEFORE exec_module so @dataclass annotations resolve
    sys.modules["preflight_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


def _by_name(report, name: str):
    for c in report.checks:
        if c.name == name:
            return c
    raise AssertionError(f"check '{name}' missing from report")


def test_all_missing_fails_feishu_anthropic_database(preflight_module) -> None:
    report = preflight_module.Report()
    preflight_module._check_database(report)
    preflight_module._check_anthropic(report)
    preflight_module._check_feishu(report)
    assert _by_name(report, "database_url").status == "FAIL"
    assert _by_name(report, "anthropic_composer").status == "FAIL"
    assert _by_name(report, "feishu_review_hub").status == "FAIL"


def test_feishu_pass_when_all_present(preflight_module, monkeypatch: pytest.MonkeyPatch) -> None:
    for var in (
        "FEISHU_APP_ID",
        "FEISHU_APP_SECRET",
        "FEISHU_REVIEW_CHAT_ID",
        "FEISHU_BITABLE_APP_TOKEN",
        "FEISHU_CONTENT_QUEUE_TABLE_ID",
        "FEISHU_PERFORMANCE_TABLE_ID",
    ):
        monkeypatch.setenv(var, "x")
    report = preflight_module.Report()
    preflight_module._check_feishu(report)
    assert _by_name(report, "feishu_review_hub").status == "PASS"


def test_dry_run_default_is_pass(preflight_module) -> None:
    report = preflight_module.Report()
    preflight_module._check_publish_kill_switch(report)
    chk = _by_name(report, "publish_kill_switch")
    assert chk.status == "PASS"
    assert "DRY-RUN" in chk.detail


def test_live_kill_switch_warns(preflight_module, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MARKETING_PUBLISH_DRY_RUN", "false")
    report = preflight_module.Report()
    preflight_module._check_publish_kill_switch(report)
    chk = _by_name(report, "publish_kill_switch")
    assert chk.status == "WARN"
    assert "LIVE" in chk.detail


def test_telegram_dry_run_with_no_target_warns(preflight_module) -> None:
    # MARKETING_PUBLISH_DRY_RUN defaults to true; no token / channel set
    report = preflight_module.Report()
    preflight_module._check_telegram(report)
    chk = _by_name(report, "telegram_target")
    assert chk.status in ("PASS", "WARN")  # PASS or WARN are acceptable for dry-run


def test_telegram_live_missing_token_fails(preflight_module, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MARKETING_PUBLISH_DRY_RUN", "false")
    # No token, no channel
    report = preflight_module.Report()
    preflight_module._check_telegram(report)
    chk = _by_name(report, "telegram_target")
    assert chk.status == "FAIL"
    assert "TELEGRAM_BOT_TOKEN" in chk.detail
    assert "TELEGRAM_CHANNEL_ID_PUBLIC" in chk.detail


def test_telegram_live_with_full_config_passes(preflight_module, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MARKETING_PUBLISH_DRY_RUN", "false")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.setenv("TELEGRAM_CHANNEL_ID_PUBLIC", "-1001234567890")
    monkeypatch.setenv("TELEGRAM_CHANNEL_HANDLE", "@SentinelAI_signals")
    report = preflight_module.Report()
    preflight_module._check_telegram(report)
    chk = _by_name(report, "telegram_target")
    assert chk.status == "PASS"
    assert "LIVE" in chk.detail


def test_scheduler_flags_default_warns(preflight_module) -> None:
    report = preflight_module.Report()
    preflight_module._check_scheduler_flags(report)
    chk = _by_name(report, "scheduler_flags")
    assert chk.status == "WARN"  # both off
    assert "both off" in chk.detail


def test_scheduler_flags_with_always_on_passes(preflight_module, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MARKETING_ALWAYS_ON_DRAFT_ENABLED", "true")
    report = preflight_module.Report()
    preflight_module._check_scheduler_flags(report)
    chk = _by_name(report, "scheduler_flags")
    assert chk.status == "PASS"
    assert "always_on=on" in chk.detail


def test_scheduler_flags_with_queue_poll_passes(preflight_module, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MARKETING_QUEUE_POLL_ENABLED", "true")
    report = preflight_module.Report()
    preflight_module._check_scheduler_flags(report)
    chk = _by_name(report, "scheduler_flags")
    assert chk.status == "PASS"
    assert "queue_poll=on" in chk.detail


def test_growth_os_public_url_localhost_warns(preflight_module, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROWTH_OS_PUBLIC_URL", "http://localhost:3000")
    report = preflight_module.Report()
    preflight_module._check_growth_os_public_url(report)
    chk = _by_name(report, "growth_os_public_url")
    assert chk.status == "WARN"


def test_growth_os_public_url_production_passes(preflight_module, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROWTH_OS_PUBLIC_URL", "https://sentinel.example.com")
    report = preflight_module.Report()
    preflight_module._check_growth_os_public_url(report)
    chk = _by_name(report, "growth_os_public_url")
    assert chk.status == "PASS"


def test_x_publish_live_missing_oauth_fails(preflight_module, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MARKETING_PUBLISH_DRY_RUN", "false")
    monkeypatch.setenv("X_DRY_RUN", "false")
    report = preflight_module.Report()
    preflight_module._check_x(report)
    chk = _by_name(report, "x_publish")
    assert chk.status == "FAIL"
    assert "X_API_KEY" in chk.detail


def test_x_publish_dry_run_with_missing_oauth_passes(preflight_module) -> None:
    report = preflight_module.Report()
    preflight_module._check_x(report)
    chk = _by_name(report, "x_publish")
    assert chk.status == "PASS"
    assert "live blocked" in chk.detail


def test_intelligence_sources_pass_with_three_p0_sources(preflight_module, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FMP_API_KEY", "fmp")
    monkeypatch.setenv("SEC_USER_AGENT", "Sentinel AI ops@example.com")
    monkeypatch.setenv("YOUTUBE_DATA_API_KEY", "yt")
    report = preflight_module.Report()
    preflight_module._check_intelligence_sources(report)
    chk = _by_name(report, "intelligence_sources")
    assert chk.status == "PASS"


def test_anthropic_proxy_detail_includes_base_url(preflight_module, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-xxx")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://code.newcli.com/claude/aws")
    monkeypatch.setenv("MARKETING_COMPOSER_MODEL", "claude-sonnet-4-5")
    report = preflight_module.Report()
    preflight_module._check_anthropic(report)
    chk = _by_name(report, "anthropic_composer")
    assert chk.status == "PASS"
    assert "proxy=" in chk.detail
    assert "model=claude-sonnet-4-5" in chk.detail


def test_secrets_never_appear_in_report_detail(preflight_module, monkeypatch: pytest.MonkeyPatch) -> None:
    """No matter what we set, the actual secret value should never be printed
    (we only print `present` / `missing` / scheme)."""
    monkeypatch.setenv("FEISHU_APP_SECRET", "TOPSECRET12345")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-SECRET-MATERIAL")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "999:LIVEBOTTOKEN")
    monkeypatch.setenv("DATABASE_URL", "postgres://user:LEAKEDPASS@host:5432/db")

    report = preflight_module.Report()
    preflight_module._check_database(report)
    preflight_module._check_anthropic(report)
    preflight_module._check_feishu(report)
    preflight_module._check_telegram(report)

    full_dump = " ".join(c.detail for c in report.checks)
    for needle in ("TOPSECRET12345", "SECRET-MATERIAL", "LIVEBOTTOKEN", "LEAKEDPASS"):
        assert needle not in full_dump, f"secret leaked into detail: {needle}"
