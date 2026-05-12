"""Brand red-line scanner. Mirrors README:281 enforcement.

Every marketing message MUST pass scan() before publish. Three guarantees:
1. No buy/sell/predict/price-target language.
2. At least one primary-source URL inline.
3. Trailing disclaimer phrase.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# Forbidden tokens — substring match on lowercased text.
# Source: README:281 + Sentinel brand redline doc.
FORBIDDEN_TERMS: tuple[str, ...] = (
    "buy",
    "sell",
    "price target",
    "predict",
    "trading signal",
    "guaranteed",
    "moonshot",
    "yolo",
    "tendies",
    "go long",
    "go short",
    "long this",
    "short this",
    "to the moon",
    "100x",
    "10x return",
    "easy money",
    "free money",
    "pump",
    "dump",
)

# Acceptable disclaimer phrases (any one is sufficient).
DISCLAIMER_PHRASES: tuple[str, ...] = (
    "context, not advice",
    "your call. not advice",
    "not investment advice",
    "for information only",
    "not financial advice",
)

URL_PATTERN = re.compile(r"https?://[^\s)\]]+", re.IGNORECASE)
WORD_BOUNDARY_TERMS = {"buy", "sell", "pump", "dump"}

# Sprint 1 add-on: opt-in score-reference detector.
# NOT wired into scan() by default — existing prompts intentionally
# emit "score" language. Callers (or Sprint 2 templates) call this
# explicitly after the LLM responds. Wiring into scan() flips in
# Sprint 2 after all production templates are state-based.
SCORE_REFERENCE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bscore\b", re.IGNORECASE),
    re.compile(r"\brating\b", re.IGNORECASE),
    re.compile(r"\b\d{1,3}\s*/\s*100\b"),
    re.compile(r"\b\d{1,3}\s*out\s+of\s+(?:100|ten|10)\b", re.IGNORECASE),
)


def check_no_score_references(text: str) -> tuple[str, ...]:
    """Returns tuple of violation strings if any score/rating reference
    appears. Empty tuple means clean.

    Sprint 1 wiring: opt-in; not called by scan() yet. Sprint 2 flips
    this on by default once templates are state-based.
    """
    out: list[str] = []
    for pat in SCORE_REFERENCE_PATTERNS:
        m = pat.search(text)
        if m:
            out.append(f"score_reference:{m.group(0).lower()}")
    return tuple(out)


@dataclass(frozen=True)
class RedlineResult:
    ok: bool
    violations: tuple[str, ...]
    has_source: bool
    has_disclaimer: bool

    def reason(self) -> str:
        if self.ok:
            return "ok"
        return ", ".join(self.violations)


def _has_term(text_lower: str, term: str) -> bool:
    if term in WORD_BOUNDARY_TERMS:
        return re.search(rf"\b{re.escape(term)}\b", text_lower) is not None
    return term in text_lower


def scan(
    text: str,
    *,
    require_source: bool = True,
    require_disclaimer: bool = True,
) -> RedlineResult:
    text_lower = text.lower()
    violations: list[str] = []

    for term in FORBIDDEN_TERMS:
        if _has_term(text_lower, term):
            violations.append(f"forbidden:{term}")

    has_source = bool(URL_PATTERN.search(text))
    has_disclaimer = any(phrase in text_lower for phrase in DISCLAIMER_PHRASES)

    if require_source and not has_source:
        violations.append("missing_source")
    if require_disclaimer and not has_disclaimer:
        violations.append("missing_disclaimer")

    return RedlineResult(
        ok=not violations,
        violations=tuple(violations),
        has_source=has_source,
        has_disclaimer=has_disclaimer,
    )
