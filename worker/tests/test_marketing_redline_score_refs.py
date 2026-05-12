"""Tests for opt-in score-reference detector (Sprint 1)."""
from __future__ import annotations

import pytest

from app.marketing.redline import check_no_score_references


def test_clean_text_has_no_violations() -> None:
    text = "$NVDA — state changed to Heated. Multi-signal firing. https://x.com Not financial advice."
    assert check_no_score_references(text) == ()


@pytest.mark.parametrize(
    "phrase",
    [
        "Our Sentinel score is 72",
        "score: 85",
        "internal Score of 60",
    ],
)
def test_score_word_caught(phrase: str) -> None:
    violations = check_no_score_references(phrase)
    assert any(v.startswith("score_reference:score") for v in violations)


@pytest.mark.parametrize(
    "phrase",
    [
        "rating: Strong",
        "Sentinel rating upgraded",
        "RATING dropped to neutral",
    ],
)
def test_rating_word_caught(phrase: str) -> None:
    violations = check_no_score_references(phrase)
    assert any(v.startswith("score_reference:rating") for v in violations)


@pytest.mark.parametrize(
    "phrase",
    [
        "72/100",
        "85 / 100",
        "Sentinel: 60/100 today",
    ],
)
def test_x_over_100_caught(phrase: str) -> None:
    violations = check_no_score_references(phrase)
    assert any("/100" in v or "/ 100" in v for v in violations)


@pytest.mark.parametrize(
    "phrase",
    [
        "85 out of 100",
        "scored 72 out of 100",
        "9 out of 10 metrics positive",
    ],
)
def test_out_of_100_or_10_caught(phrase: str) -> None:
    violations = check_no_score_references(phrase)
    assert any("out of" in v for v in violations)


def test_substring_within_other_word_not_false_positive() -> None:
    # "score" is a word, not "scoreboard" or "underscore"
    text = "Underscore the anomaly. Scoreboard not relevant."
    # These DO contain 'score' as substring inside other words; current
    # regex uses \b which should NOT match these.
    violations = check_no_score_references(text)
    # 'Scoreboard' starts with Score followed by 'board' (no word boundary
    # between e and b), so \bscore\b does not match here.
    # However "Underscore the" — "Underscore" is one word, no boundary.
    # And "Scoreboard" — also one word, no boundary.
    # Asserting both forms are NOT caught.
    assert violations == ()


def test_multiple_violations_all_reported() -> None:
    text = "Score 72/100, rating Heated"
    violations = check_no_score_references(text)
    # At minimum: "score", "/100", "rating"
    assert len(violations) >= 3
