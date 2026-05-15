from __future__ import annotations

import pytest

from app.main import _validate_production_public_url


def test_production_public_url_guard_rejects_missing_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENV", "production")
    monkeypatch.delenv("GROWTH_OS_PUBLIC_URL", raising=False)

    with pytest.raises(RuntimeError, match="GROWTH_OS_PUBLIC_URL must be set"):
        _validate_production_public_url()


def test_production_public_url_guard_rejects_localhost(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("GROWTH_OS_PUBLIC_URL", "http://localhost:3000")

    with pytest.raises(RuntimeError, match="localhost"):
        _validate_production_public_url()


def test_production_public_url_guard_accepts_public_origin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("GROWTH_OS_PUBLIC_URL", "https://sentinelai.com")

    _validate_production_public_url()
