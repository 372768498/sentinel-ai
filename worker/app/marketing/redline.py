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
