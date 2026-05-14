"""
Per-ticker English narrative generator: `why_moving` + `risk_flag`.

Inputs (one call per ticker):
  - the watchlist mover (ticker / price / change_pct / volume / rel_vol)
  - the xiangyu ScoreSnapshot (score_100 / components / recommendation)

Output:
  Narrative(why_moving: str | None, risk_flag: str | None)

Why a separate LLM call instead of using xiangyu's supporting_points:
  - xiangyu emits supporting_points / caveats in CN — Sentinel AI ships
    an English surface.
  - The radar one-liner needs to fuse "what moved today" with
    "why fundamentally" — xiangyu's points are point-in-time
    fundamentals only.
  - Haiku 4.5 at ~$0.001/call × 5 tickers/day = trivial cost.

Failure mode:
  Anthropic API missing / model error / unparseable JSON → both fields
  None. Callers must treat narrative as decorative — the radar
  push still renders without it.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

MODEL_ID = "claude-haiku-4-5"

# System prompt is cacheable — it's stable across the whole watchlist run.
_SYSTEM_PROMPT = """\
You are Sentinel AI's market narrative engine. Given one US-stock's
intraday move and its 10-dimension fundamental snapshot, emit two short
English fields:

- why_moving: a single sentence (<=90 chars) explaining the likely
  catalyst for today's price move, fusing the move itself with the
  fundamental snapshot. Use concrete numbers when they're in the input.
  No advice, no predictions. Examples:
    "EPS beat 5.2%; analyst upgrades push targets higher."
    "Pre-market dip on margin concerns; volume confirms selling."

- risk_flag: a short phrase (<=40 chars) calling out the single biggest
  caveat a Sentinel user should know about right now. Pull from the
  fundamentals, technicals, or sentiment data. Examples:
    "Trading at peer P/E premium"
    "RSI overbought; pre-earnings window"
    "Narrative ahead of confirmed filings"

Hard rules:
- Output STRICTLY valid JSON: {"why_moving": "...", "risk_flag": "..."}
- No prose, no markdown, no code fences, no commentary.
- Never recommend buy/sell/hold or price targets.
- Never include source URLs (handled separately).
"""


@dataclass(frozen=True)
class Narrative:
    why_moving: str | None
    risk_flag: str | None


_EMPTY = Narrative(why_moving=None, risk_flag=None)


def _summarize_components(components: dict[str, Any]) -> dict[str, Any]:
    """Compact the 10-dim components into a token-light payload."""
    pick: dict[str, Any] = {}
    for key, comp in components.items():
        if not isinstance(comp, dict):
            continue
        compact: dict[str, Any] = {}
        # Preserve numeric/string scalars; drop nested dicts to keep prompt small
        for k, v in comp.items():
            if isinstance(v, (int, float, str, bool)) and v is not None:
                compact[k] = v
        if compact:
            pick[key] = compact
    return pick


def _truncate(text: str | None, limit: int) -> str | None:
    if text is None:
        return None
    text = text.strip()
    if not text:
        return None
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


async def generate_narrative(
    *,
    ticker: str,
    last_price: float | None,
    change_pct: float | None,
    volume: int | None,
    relative_volume: float | None,
    session_label: str,
    score_100: int | None,
    recommendation: str | None,
    components: dict[str, Any] | None,
) -> Narrative:
    """
    Returns Narrative(None, None) when:
      - ANTHROPIC_API_KEY is unset (dev / mock mode)
      - the model errors / times out / returns non-JSON
      - JSON is parseable but fields are missing
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        logger.debug("narrative: ANTHROPIC_API_KEY missing, returning empty")
        return _EMPTY

    try:
        from anthropic import AsyncAnthropic
    except ImportError as exc:
        logger.warning("narrative: anthropic SDK unavailable: %s", exc)
        return _EMPTY

    payload = {
        "ticker": ticker.upper(),
        "session": session_label,
        "last_price": last_price,
        "change_pct": change_pct,
        "volume": volume,
        "relative_volume": relative_volume,
        "sentinel_score_100": score_100,
        "sentinel_recommendation": recommendation,
        "components": _summarize_components(components or {}),
    }

    try:
        client = AsyncAnthropic(api_key=api_key)
        response = await client.messages.create(
            model=MODEL_ID,
            max_tokens=300,
            system=[
                {
                    "type": "text",
                    "text": _SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                },
            ],
            messages=[
                {
                    "role": "user",
                    "content": json.dumps(payload, ensure_ascii=False),
                },
                # Prefill forces JSON without code fences
                {"role": "assistant", "content": "{"},
            ],
        )
    except Exception as exc:
        logger.warning("narrative: anthropic call failed for %s: %s", ticker, exc)
        return _EMPTY

    try:
        body = response.content[0].text
    except (AttributeError, IndexError):
        logger.warning("narrative: empty response for %s", ticker)
        return _EMPTY

    # The prefill leaves the opening { dangling; stitch it back.
    raw = "{" + body.strip()
    # Some models still wrap in code fences despite instructions — strip both.
    if raw.startswith("{```"):
        raw = raw.replace("```", "", 1)
    if raw.endswith("```"):
        raw = raw[:-3].rstrip()

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning("narrative: bad JSON for %s: %s | raw=%r",
                       ticker, exc, raw[:200])
        return _EMPTY

    return Narrative(
        why_moving=_truncate(parsed.get("why_moving"), 95),
        risk_flag=_truncate(parsed.get("risk_flag"), 45),
    )
