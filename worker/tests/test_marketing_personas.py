from app.marketing.personas import (
    ALL_PERSONAS,
    MARKET_CALENDAR,
    RISK_WATCHDOG,
    SEC_FILING_REPORTER,
    by_key,
)
from app.marketing.redline import scan


def test_all_personas_unique_keys():
    keys = [p.key for p in ALL_PERSONAS]
    assert len(keys) == len(set(keys))


def test_persona_lookup():
    assert by_key("sec_filing_reporter") is SEC_FILING_REPORTER
    assert by_key("risk_watchdog") is RISK_WATCHDOG
    assert by_key("market_calendar") is MARKET_CALENDAR


def test_persona_voice_examples_pass_redline():
    for persona in ALL_PERSONAS:
        for example in persona.voice_examples:
            result = scan(example)
            assert result.ok, (persona.name, example, result.violations)


def test_unknown_persona_raises():
    import pytest

    with pytest.raises(KeyError):
        by_key("nonexistent")
