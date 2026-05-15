from __future__ import annotations

from pathlib import Path

from app.marketing.short_video_renderer import ShortVideoSpec, render_svg, write_preview_svg


def _spec() -> ShortVideoSpec:
    return ShortVideoSpec(
        ticker="nvda",
        state="HEATED",
        hook="$NVDA has three signals firing right now.",
        why_now="AI-chip attention and earnings expectations are moving together.",
        risk_flags=("Expectation crowding", "Margin sensitivity", "Valuation compression"),
        cta_url="https://app.jilo.ai/stocks/NVDA",
    )


def test_render_svg_contains_vertical_canvas_and_core_copy() -> None:
    svg = render_svg(_spec(), progress=0.5)
    assert 'width="1080" height="1920"' in svg
    assert "$NVDA" in svg
    assert "HEATED" in svg
    assert "Expectation crowding" in svg
    assert "app.jilo.ai/stocks/NVDA" in svg
    assert "Context, not financial advice." in svg


def test_write_preview_svg_creates_parent_dirs(tmp_path: Path) -> None:
    out = tmp_path / "nested" / "preview.svg"
    write_preview_svg(_spec(), out)
    assert out.exists()
    assert "$NVDA" in out.read_text(encoding="utf-8")
