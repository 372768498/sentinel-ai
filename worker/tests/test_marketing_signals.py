from dataclasses import dataclass

from app.marketing.signals import passes_gate, score_from_move


@dataclass
class _Move:
    ticker: str
    change_pct: float


def test_score_zero_at_no_move():
    assert score_from_move(_Move("X", 0.0)) == 0


def test_score_monotonic():
    s1 = score_from_move(_Move("X", 1.0))
    s3 = score_from_move(_Move("X", 3.0))
    s5 = score_from_move(_Move("X", 5.0))
    s10 = score_from_move(_Move("X", 10.0))
    assert s1 < s3 < s5 < s10


def test_score_symmetric_for_negative():
    assert score_from_move(_Move("X", 5.0)) == score_from_move(_Move("X", -5.0))


def test_score_capped_at_100():
    assert score_from_move(_Move("X", 100.0)) <= 100


def test_score_3pct_above_75():
    assert score_from_move(_Move("X", 3.0)) >= 70


def test_score_5pct_above_80():
    assert score_from_move(_Move("X", 5.0)) >= 80


def test_gate_default_threshold():
    assert passes_gate(85) is True
    assert passes_gate(79) is False
    assert passes_gate(80) is True


def test_gate_custom_threshold():
    assert passes_gate(75, threshold=70) is True
    assert passes_gate(75, threshold=90) is False
