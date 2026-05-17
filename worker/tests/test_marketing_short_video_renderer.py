from __future__ import annotations

from pathlib import Path

import json

from app.marketing.short_video_renderer import (
    ShortVideoSpec,
    build_qa_report,
    build_shot_plan,
    render_captions_srt,
    render_svg,
    write_asset_pack,
    write_preview_svg,
)


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
    assert "Context, not financial advice." in svg
    cta_svg = render_svg(_spec(), progress=0.9)
    assert "app.jilo.ai/stocks/NVDA" in cta_svg


def test_write_preview_svg_creates_parent_dirs(tmp_path: Path) -> None:
    out = tmp_path / "nested" / "preview.svg"
    write_preview_svg(_spec(), out)
    assert out.exists()
    assert "$NVDA" in out.read_text(encoding="utf-8")


def test_build_shot_plan_matches_ticker_state_risk_stack_contract() -> None:
    plan = build_shot_plan(_spec())
    assert plan["canvas"] == {"width": 1080, "height": 1920, "fps": 30, "safe_area_px": 96}
    assert plan["template"] == "sentinel_product_demo_risk_stack"
    assert plan["reference_pattern"] == "tension -> product alert -> evidence stack -> CTA"
    assert plan["ticker"] == "NVDA"
    assert plan["state"] == "HEATED"
    assert plan["scenes"][0]["start"] == 0
    assert plan["scenes"][0]["end"] == 3
    assert "$NVDA" in plan["scenes"][0]["text"]
    assert "state change" in plan["scenes"][0]["text"]


def test_render_captions_srt_includes_ticker_state_and_disclaimer() -> None:
    srt = render_captions_srt(_spec())
    assert "1\n00:00:00,000 --> 00:00:03,000" in srt
    assert "Sentinel AI flags $NVDA as HEATED" in srt
    assert "Context, not financial advice." in srt


def test_build_qa_report_flags_forbidden_terms() -> None:
    bad = ShortVideoSpec(
        ticker="TSLA",
        state="WATCHING",
        hook="AI predicts a move.",
        why_now="Crowding is elevated.",
        risk_flags=("Attention spike",),
        cta_url="https://app.jilo.ai/stocks/TSLA",
    )
    report = build_qa_report(bad)
    assert not report["ok"]
    assert "ai predicts" in report["forbidden_terms"]


def test_write_asset_pack_creates_reviewable_files_without_media_render(tmp_path: Path) -> None:
    pack = write_asset_pack(_spec(), tmp_path / "pack")

    expected = {
        "creative_brief.md",
        "script.md",
        "shot_plan.json",
        "captions.srt",
        "cover.svg",
        "platform_copy.md",
        "qa_report.json",
    }
    assert expected.issubset({path.name for path in pack.output_dir.iterdir()})
    assert pack.cover_png is None
    assert pack.video is None
    assert "$NVDA" in pack.creative_brief.read_text(encoding="utf-8")
    assert "# Platform Copy" in pack.platform_copy.read_text(encoding="utf-8")

    shot_plan = json.loads(pack.shot_plan.read_text(encoding="utf-8"))
    qa_report = json.loads(pack.qa_report.read_text(encoding="utf-8"))
    assert shot_plan["ticker"] == "NVDA"
    assert qa_report["ticker_in_first_3_seconds"]
    assert qa_report["state_in_alert_scene"]
    assert qa_report["product_demo_structure"] == [
        "tension",
        "sentinel_alert",
        "context_stack",
        "cta",
    ]
    assert qa_report["ok"]
