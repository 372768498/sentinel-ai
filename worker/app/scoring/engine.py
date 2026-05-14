"""
Subprocess wrapper around skills/xiangyu-finance-stock-analyzing.

Uses the same path resolution as worker/app/runner.py (settings.python_skill_dir)
so a single env var (PYTHON_SKILL_DIR) controls where the skill lives.

Why subprocess instead of `import shared`:
  - the skill ships with PEP-723 inline metadata and is exercised via
    `uv run` in dev; matching that surface keeps the runtime story uniform.
  - the skill spawns its own asyncio.run() inside sentiment analysis;
    nesting that inside the worker's running loop is hostile.
  - subprocess gives us a hard timeout, so a flaky Yahoo call can't wedge
    the scheduler thread.
"""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from ..config import get_settings

logger = logging.getLogger(__name__)

# Score → label mapping. xiangyu emits CN-flavored "Strong/Constructive/Neutral/
# Fragile/HighRisk" — for the English-speaking public channel we surface the
# more familiar "Strong Buy / Buy / Hold / Reduce / Sell" rendering.
_RATING_BANDS: tuple[tuple[int, str], ...] = (
    (80, "Strong Buy"),
    (65, "Buy"),
    (50, "Hold"),
    (35, "Reduce"),
    (0, "Sell"),
)


def rating_label_for(score_100: int) -> str:
    for threshold, label in _RATING_BANDS:
        if score_100 >= threshold:
            return label
    return "Sell"


# Single-ticker fast mode is ~3-8s on a warm cache, ~15s cold. Watchlist
# of 5 tickers parallelized stays well under a minute. Cap each subprocess
# so a hung yfinance call (we've seen 60s tails) doesn't block the cron.
_SCORE_TIMEOUT_SECONDS = 90


@dataclass(frozen=True)
class ScoreSnapshot:
    ticker: str
    score_100: int
    rating: str          # English label derived from score_100
    recommendation: str  # xiangyu's STRONG/CONSTRUCTIVE/...
    state: str
    confidence: float
    supporting_points: list[str]
    caveats: list[str]
    components: dict
    timestamp: str       # ISO from xiangyu, "we computed this at"


async def score_one(ticker: str) -> ScoreSnapshot | None:
    """
    Run `analyze_stock.py TICKER --fast --output json` and parse the result.

    Returns None on timeout / non-zero exit / unparseable output. Callers
    should treat None as "skip this ticker for this cycle" rather than fatal.
    """
    settings = get_settings()
    skill_dir = Path(settings.python_skill_dir).resolve()
    if not skill_dir.exists():
        logger.error("scoring: skill dir missing at %s", skill_dir)
        return None

    cmd = [
        settings.python_executable,
        "analyze_stock.py",
        ticker.upper(),
        "--fast",
        "--output",
        "json",
    ]

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(skill_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        logger.error("scoring: python executable not found (%s): %s",
                     settings.python_executable, exc)
        return None

    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(), timeout=_SCORE_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.warning("scoring: %s timed out after %ss", ticker, _SCORE_TIMEOUT_SECONDS)
        process.kill()
        await process.wait()
        return None

    if process.returncode != 0:
        # xiangyu writes diagnostics to stderr; keep the tail for triage.
        tail = stderr.decode("utf-8", errors="replace").strip().splitlines()[-3:]
        logger.warning("scoring: %s exited %s (tail=%s)", ticker, process.returncode, tail)
        return None

    try:
        payload = json.loads(stdout.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as exc:
        logger.warning("scoring: %s produced unparseable JSON: %s", ticker, exc)
        return None

    try:
        score_100 = int(payload["score_100"])
        return ScoreSnapshot(
            ticker=payload["ticker"],
            score_100=score_100,
            rating=rating_label_for(score_100),
            recommendation=str(payload.get("recommendation", "")),
            state=str(payload.get("state", "")),
            confidence=float(payload.get("confidence", 0.0)),
            supporting_points=list(payload.get("supporting_points") or []),
            caveats=list(payload.get("caveats") or []),
            components=dict(payload.get("components") or {}),
            timestamp=str(payload.get("timestamp", "")),
        )
    except (KeyError, TypeError, ValueError) as exc:
        logger.warning("scoring: %s missing expected fields: %s", ticker, exc)
        return None


async def score_watchlist(tickers: Iterable[str]) -> list[ScoreSnapshot]:
    """Parallel score across a watchlist. Drops Nones (failed tickers)."""
    results = await asyncio.gather(*[score_one(t) for t in tickers])
    return [r for r in results if r is not None]
