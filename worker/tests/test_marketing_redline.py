from app.marketing.redline import scan


CLEAN = (
    "$NVDA filed an 8-K disclosing a $3.4B Q3 buyback authorization. "
    "Source: https://www.sec.gov/Archives/edgar/data/1045810/000104581026000123/0001045810.htm\n\n"
    "Context, not advice."
)


def test_clean_post_passes():
    result = scan(CLEAN)
    assert result.ok, result.violations
    assert result.has_source
    assert result.has_disclaimer


def test_buy_word_caught():
    text = CLEAN.replace("filed", "buy now")
    result = scan(text)
    assert not result.ok
    assert "forbidden:buy" in result.violations


def test_sell_word_caught():
    text = "$AAPL sell signal triggered. https://x.com\n\nContext, not advice."
    result = scan(text)
    assert not result.ok
    assert "forbidden:sell" in result.violations


def test_substring_buyback_passes():
    # "buyback" must NOT trigger the "buy" rule (word-boundary).
    assert scan(CLEAN).ok


def test_price_target_caught():
    text = "$TSLA price target $300 per analyst note. https://x.com\n\nContext, not advice."
    result = scan(text)
    assert not result.ok
    assert "forbidden:price target" in result.violations


def test_predict_caught():
    text = "$META I predict 20% upside. https://x.com\n\nContext, not advice."
    result = scan(text)
    assert not result.ok
    assert "forbidden:predict" in result.violations


def test_missing_disclaimer():
    text = "$NVDA filed an 8-K. Source: https://www.sec.gov/x"
    result = scan(text)
    assert not result.ok
    assert "missing_disclaimer" in result.violations


def test_missing_source():
    text = "$NVDA filed an 8-K. Context, not advice."
    result = scan(text)
    assert not result.ok
    assert "missing_source" in result.violations


def test_alternative_disclaimer_phrase():
    text = "$NVDA filed an 8-K. https://www.sec.gov/x\n\nNot financial advice."
    result = scan(text)
    assert result.ok, result.violations


def test_hype_word_caught():
    text = "$DOGE to the moon! https://x.com\n\nContext, not advice."
    result = scan(text)
    assert not result.ok
    assert any("to the moon" in v for v in result.violations)


def test_yolo_caught():
    text = "$GME yolo entry, 100% conviction. https://x.com\n\nContext, not advice."
    result = scan(text)
    assert not result.ok
    assert "forbidden:yolo" in result.violations
