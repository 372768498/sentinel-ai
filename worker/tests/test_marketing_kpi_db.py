"""Tests for kpi_db.py utility functions (no real DB)."""

from __future__ import annotations

from app.marketing.kpi_db import _strip_prisma_query_params


def test_strip_schema_param() -> None:
    url = "postgresql://u:p@h:5432/db?schema=public"
    assert _strip_prisma_query_params(url) == "postgresql://u:p@h:5432/db"


def test_strip_multiple_prisma_params_keeps_real_ones() -> None:
    url = "postgresql://u:p@h:5432/db?schema=public&sslmode=require&connection_limit=5"
    out = _strip_prisma_query_params(url)
    assert "sslmode=require" in out
    assert "schema" not in out
    assert "connection_limit" not in out


def test_strip_with_no_query_returns_unchanged() -> None:
    url = "postgresql://u:p@h:5432/db"
    assert _strip_prisma_query_params(url) == url


def test_strip_pgbouncer_and_pool_timeout() -> None:
    url = "postgresql://u:p@h:5432/db?pgbouncer=true&pool_timeout=10"
    out = _strip_prisma_query_params(url)
    assert "?" not in out or out.endswith("?")
    assert "pgbouncer" not in out
    assert "pool_timeout" not in out
