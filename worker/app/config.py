from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    worker_internal_token: str
    worker_public_url: str
    project_root: str
    python_skill_dir: str
    python_executable: str
    resend_api_key: str
    resend_from_email: str
    playwright_chromium_executable: str


def _resolve_project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _resolve_skill_dir(project_root: Path) -> str:
    raw_value = os.environ.get(
        "PYTHON_SKILL_DIR",
        "./skills/xiangyu-finance-stock-analyzing/scripts/python",
    )
    candidate = Path(raw_value)
    if not candidate.is_absolute():
        candidate = (project_root / candidate).resolve()
    return str(candidate)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    project_root = _resolve_project_root()
    return Settings(
        worker_internal_token=os.environ.get("WORKER_INTERNAL_TOKEN", ""),
        worker_public_url=os.environ.get(
            "WORKER_PUBLIC_URL",
            os.environ.get("NEXT_PUBLIC_WORKER_URL", "http://localhost:8000"),
        ).rstrip("/"),
        project_root=str(project_root),
        python_skill_dir=_resolve_skill_dir(project_root),
        python_executable=os.environ.get("PYTHON_EXECUTABLE", "python"),
        resend_api_key=os.environ.get("RESEND_API_KEY", ""),
        resend_from_email=os.environ.get(
            "RESEND_FROM_EMAIL", "Sentinel AI <briefing@example.com>"
        ),
        playwright_chromium_executable=os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE", ""),
    )
