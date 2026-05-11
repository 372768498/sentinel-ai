from app.marketing.composer import Composer
from app.marketing.personas import ALL_PERSONAS, SEC_FILING_REPORTER


def test_mock_composer_passes_redline():
    composer = Composer(dry_run=True)
    comp = composer.compose_post(
        persona=SEC_FILING_REPORTER,
        ticker="AAPL",
        change_pct=2.3,
        score=82,
        headline="filed an 8-K disclosing $5B buyback",
        source_url="https://www.sec.gov/Archives/edgar/data/0000320193/x.htm",
        deep_link="https://t.me/SentinelAIProChannelBot?start=src_xtw_score82_aapl_20260509",
    )
    assert comp.used_mock
    assert comp.redline.ok, comp.redline.violations
    assert comp.redline.has_source
    assert comp.redline.has_disclaimer
    assert "AAPL" in comp.text


def test_mock_composer_works_for_all_personas():
    composer = Composer(dry_run=True)
    for persona in ALL_PERSONAS:
        comp = composer.compose_post(
            persona=persona,
            ticker="NVDA",
            change_pct=-3.1,
            score=78,
            headline="VIX spiked to 28 ahead of FOMC",
            source_url="https://www.cboe.com/x",
            deep_link="https://t.me/SentinelAIProChannelBot?start=src_xtw_score78_nvda_20260509",
        )
        assert comp.redline.ok, (persona.name, comp.redline.violations)


def test_mock_uses_headline_verbatim():
    composer = Composer(dry_run=True)
    comp_up = composer.compose_post(
        persona=SEC_FILING_REPORTER,
        ticker="AMD",
        change_pct=4.5,
        score=88,
        headline="filed an 8-K disclosing $2B buyback",
        source_url="https://ir.amd.com/x",
        deep_link="https://t.me/x",
    )
    assert "filed an 8-K disclosing $2B buyback" in comp_up.text
    assert "AMD" in comp_up.text
