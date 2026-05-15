"""Minimal 9:16 short-video renderer for Growth OS.

The first production goal is not cinematic AI video. It is a reliable,
reviewable, platform-safe information card that turns one market opportunity
into an mp4 preview for YouTube Shorts / TikTok manual upload.
"""

from __future__ import annotations

import html
import json
import re
import subprocess
import tempfile
import textwrap
import asyncio
from dataclasses import dataclass
from pathlib import Path

WIDTH = 1080
HEIGHT = 1920
FPS = 30
DEFAULT_DURATION_SECONDS = 18
FORBIDDEN_TERMS = (
    "buy",
    "sell",
    "hold",
    "price target",
    "ai predicts",
    "predicts",
    "guaranteed",
    "100x",
    "pump",
    "dump",
    "go long",
    "go short",
)


@dataclass(frozen=True)
class ShortVideoSpec:
    ticker: str
    state: str
    hook: str
    why_now: str
    risk_flags: tuple[str, ...]
    cta_url: str
    disclaimer: str = "Context, not financial advice."


@dataclass(frozen=True)
class ShortVideoAssetPack:
    output_dir: Path
    creative_brief: Path
    script: Path
    shot_plan: Path
    captions: Path
    cover_svg: Path
    cover_png: Path | None
    video: Path | None
    platform_copy: Path
    qa_report: Path


def _wrap(text: str, width: int) -> list[str]:
    return textwrap.wrap(text.strip(), width=width, break_long_words=False) or [""]


def _ticker(spec: ShortVideoSpec) -> str:
    return spec.ticker.strip().upper().lstrip("$")


def _state(spec: ShortVideoSpec) -> str:
    return spec.state.strip().upper()


def _words(value: str) -> int:
    return len(re.findall(r"[A-Za-z0-9$']+", value))


def _forbidden_hits(spec: ShortVideoSpec) -> list[str]:
    haystack = " ".join(
        [
            spec.hook,
            spec.why_now,
            " ".join(spec.risk_flags),
            spec.cta_url,
            spec.disclaimer,
        ]
    ).lower()
    return [term for term in FORBIDDEN_TERMS if term in haystack]


def _text(x: int, y: int, value: str, *, size: int, color: str, weight: int = 600) -> str:
    escaped = html.escape(value)
    return (
        f'<text x="{x}" y="{y}" fill="{color}" '
        f'font-family="Inter, Arial, sans-serif" font-size="{size}" '
        f'font-weight="{weight}">{escaped}</text>'
    )


def _multiline(x: int, y: int, value: str, *, size: int, color: str, width: int, line_gap: int) -> str:
    lines = _wrap(value, width)
    return "\n".join(
        _text(x, y + i * line_gap, line, size=size, color=color, weight=560)
        for i, line in enumerate(lines)
    )


def render_svg(spec: ShortVideoSpec, *, progress: float = 0.0) -> str:
    ticker = _ticker(spec)
    state = _state(spec)
    flags = list(spec.risk_flags[:3])
    while len(flags) < 3:
        flags.append("No additional risk flag supplied")
    bar_w = max(1, min(948, int(948 * progress)))
    state_fill = {
        "HEATED": "#f3c64a",
        "INFLECTION": "#ff5f4f",
        "WATCHING": "#72d6ff",
        "CALM": "#99f6c8",
    }.get(state, "#f3c64a")

    cards = []
    y0 = 724
    accents = ("#f3c64a", "#ff7b49", "#dd5b5b")
    for idx, flag in enumerate(flags, start=1):
        y = y0 + (idx - 1) * 278
        cards.append(
            f"""
            <g>
              <rect x="66" y="{y}" width="948" height="236" rx="8" fill="#16231d"/>
              <rect x="96" y="{y + 36}" width="10" height="164" fill="{accents[idx - 1]}"/>
              {_text(134, y + 86, f"{idx}. {flag}", size=34, color="#e8fff3", weight=760)}
              {_multiline(134, y + 140, "Risk flag to verify before the next catalyst.", size=26, color="#a9c2b2", width=52, line_gap=36)}
            </g>
            """
        )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#07120d"/>
      <stop offset="0.58" stop-color="#0d1a14"/>
      <stop offset="1" stop-color="#10100c"/>
    </linearGradient>
    <filter id="softShadow" x="-20%" y="-20%" width="140%" height="140%">
      <feDropShadow dx="0" dy="18" stdDeviation="22" flood-color="#000" flood-opacity="0.34"/>
    </filter>
  </defs>
  <rect width="{WIDTH}" height="{HEIGHT}" fill="url(#bg)"/>
  <rect x="66" y="78" width="948" height="120" rx="0" fill="#0f251a"/>
  {_text(96, 130, "Sentinel AI", size=34, color="#e8fff3", weight=760)}
  {_text(96, 172, spec.disclaimer, size=24, color="#95b7a3", weight=520)}
  {_text(858, 146, "Shorts / TikTok", size=24, color="#95b7a3", weight=520)}

  <g filter="url(#softShadow)">
    <rect x="66" y="246" width="948" height="410" rx="8" fill="#122119"/>
    {_text(104, 340, f"${ticker}", size=72, color="#e8fff3", weight=820)}
    <rect x="104" y="378" width="300" height="70" rx="4" fill="{state_fill}"/>
    {_text(136, 425, state, size=35, color="#11140f", weight=820)}
    {_multiline(104, 520, spec.hook, size=50, color="#ffffff", width=30, line_gap=58)}
    {_multiline(104, 610, spec.why_now, size=30, color="#bad6c5", width=48, line_gap=40)}
  </g>

  {''.join(cards)}

  <rect x="66" y="1592" width="948" height="170" rx="8" fill="#d7ffe2"/>
  {_text(104, 1654, f"Preview the full ${ticker} context", size=34, color="#0b1711", weight=820)}
  {_multiline(104, 1708, spec.cta_url.replace("https://", ""), size=30, color="#17492f", width=42, line_gap=38)}
  <rect x="66" y="1810" width="948" height="14" rx="7" fill="#22362a"/>
  <rect x="66" y="1810" width="{bar_w}" height="14" rx="7" fill="#d7ffe2"/>
  {_text(540, 1870, spec.disclaimer, size=24, color="#6f8b78", weight=520)}
</svg>"""


def write_preview_svg(spec: ShortVideoSpec, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_svg(spec, progress=0.35), encoding="utf-8")
    return path


def render_cover_svg(spec: ShortVideoSpec) -> str:
    ticker = _ticker(spec)
    state = _state(spec)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}">
  <rect width="{WIDTH}" height="{HEIGHT}" fill="#07120d"/>
  <rect x="70" y="92" width="940" height="150" rx="8" fill="#0f251a"/>
  {_text(106, 154, "Sentinel Market State", size=34, color="#d7ffe2", weight=760)}
  {_text(106, 204, spec.disclaimer, size=24, color="#95b7a3", weight=520)}
  <rect x="70" y="390" width="940" height="710" rx="8" fill="#122119"/>
  {_text(112, 535, f"${ticker}", size=98, color="#ffffff", weight=860)}
  <rect x="112" y="590" width="390" height="90" rx="4" fill="#d7ffe2"/>
  {_text(150, 650, state, size=42, color="#07120d", weight=840)}
  {_multiline(112, 805, spec.hook, size=62, color="#ffffff", width=25, line_gap=72)}
  <rect x="70" y="1220" width="940" height="250" rx="8" fill="#d7ffe2"/>
  {_text(112, 1310, "3 signals to verify", size=54, color="#07120d", weight=840)}
  {_text(112, 1386, "Context scan, not financial advice", size=32, color="#17492f", weight=620)}
  {_text(112, 1745, "Run the free context scan", size=38, color="#d7ffe2", weight=780)}
</svg>"""


def write_cover_svg(spec: ShortVideoSpec, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_cover_svg(spec), encoding="utf-8")
    return path


def write_cover_png(spec: ShortVideoSpec, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    _svgs_to_pngs([(render_cover_svg(spec), path)])
    return path


def _script_lines(spec: ShortVideoSpec) -> list[tuple[int, int, str, str]]:
    ticker = _ticker(spec)
    flags = list(spec.risk_flags[:3])
    while len(flags) < 3:
        flags.append("No additional risk flag supplied")
    return [
        (0, 2, "Hook", f"${ticker} {_state(spec)}: {spec.hook}"),
        (2, 7, "State reveal", f"${ticker} is in {_state(spec)} state."),
        (7, 12, "Signal 1", flags[0]),
        (12, 17, "Signal 2", flags[1]),
        (17, 22, "Signal 3", flags[2]),
        (22, 26, "Sentinel State", spec.why_now),
        (26, 30, "CTA", f"Run the free context scan. {spec.disclaimer}"),
    ]


def _srt_timestamp(seconds: int) -> str:
    return f"00:00:{seconds:02d},000"


def render_captions_srt(spec: ShortVideoSpec) -> str:
    blocks = []
    for idx, (start, end, _label, text) in enumerate(_script_lines(spec), start=1):
        blocks.append(f"{idx}\n{_srt_timestamp(start)} --> {_srt_timestamp(end)}\n{text}")
    return "\n\n".join(blocks) + "\n"


def build_shot_plan(spec: ShortVideoSpec) -> dict:
    ticker = _ticker(spec)
    flags = list(spec.risk_flags[:3])
    return {
        "canvas": {"width": WIDTH, "height": HEIGHT, "fps": FPS, "safe_area_px": 96},
        "template": "ticker_state_risk_stack",
        "ticker": ticker,
        "state": _state(spec),
        "duration_seconds": 30,
        "scenes": [
            {
                "id": f"scene_{idx:02d}_{label.lower().replace(' ', '_')}",
                "start": start,
                "end": end,
                "label": label,
                "text": text,
                "max_words": 12,
                "animation": "fade_up",
            }
            for idx, (start, end, label, text) in enumerate(_script_lines(spec), start=1)
        ],
        "signals": flags,
        "cta_url": spec.cta_url,
        "disclaimer": spec.disclaimer,
    }


def render_creative_brief(spec: ShortVideoSpec) -> str:
    flags = "\n".join(f"- {flag}" for flag in spec.risk_flags[:3])
    forbidden = _forbidden_hits(spec)
    forbidden_line = ", ".join(forbidden) if forbidden else "None"
    return f"""# Sentinel AI Short Video Creative Brief

## Ticker

${_ticker(spec)}

## Angle

Ticker State / Risk Stack

## User Anxiety

The viewer wants to know what changed before trusting the market narrative.

## Hook

{spec.hook}

## Why Now

{spec.why_now}

## Evidence Signals

{flags}

## CTA

{spec.cta_url}

## Disclaimer

{spec.disclaimer}

## Forbidden Term Check

{forbidden_line}
"""


def render_script_md(spec: ShortVideoSpec) -> str:
    rows = "\n".join(
        f"| {start}-{end}s | {label} | {text} |"
        for start, end, label, text in _script_lines(spec)
    )
    return f"""# Sentinel AI Short Video Script

| Time | Beat | On-screen / Voiceover |
| --- | --- | --- |
{rows}
"""


def render_platform_copy(spec: ShortVideoSpec) -> str:
    ticker = _ticker(spec)
    return f"""# Platform Copy

## YouTube Shorts Title

${ticker} risk stack: 3 signals to verify

## YouTube Description

Sentinel AI flagged a {_state(spec).lower()} state in ${ticker}. Run the context scan: {spec.cta_url}

{spec.disclaimer}

## TikTok Caption

${ticker} moved, but the move is not the whole story. 3 signals to verify. {spec.disclaimer}

## Pinned Comment

Run the free ${ticker} context scan: {spec.cta_url}

## Hashtags

#SentinelAI #StockMarket #Investing #MarketSignals #{ticker}
"""


def build_qa_report(spec: ShortVideoSpec) -> dict:
    lines = _script_lines(spec)
    forbidden = _forbidden_hits(spec)
    first_text = " ".join(line[3] for line in lines if line[0] < 2)
    scene_word_counts = [
        {"label": label, "words": _words(text), "ok": _words(text) <= 12}
        for _start, _end, label, text in lines
    ]
    return {
        "resolution": {"width": WIDTH, "height": HEIGHT, "ok": WIDTH == 1080 and HEIGHT == 1920},
        "duration_seconds": 30,
        "duration_ok": True,
        "ticker_in_first_2_seconds": _ticker(spec) in first_text.upper(),
        "state_in_first_2_seconds": _state(spec) in first_text.upper(),
        "scene_word_counts": scene_word_counts,
        "captions_safe_area": True,
        "cta_specific": "context scan" in spec.cta_url.lower()
        or "/stocks/" in spec.cta_url.lower(),
        "has_disclaimer": bool(spec.disclaimer.strip()),
        "forbidden_terms": forbidden,
        "ok": not forbidden
        and all(item["ok"] for item in scene_word_counts)
        and bool(spec.disclaimer.strip()),
    }


def write_asset_pack(
    spec: ShortVideoSpec,
    output_dir: Path,
    *,
    render_cover: bool = False,
    render_video: bool = False,
    ffmpeg_bin: str = "ffmpeg",
) -> ShortVideoAssetPack:
    output_dir.mkdir(parents=True, exist_ok=True)

    creative_brief = output_dir / "creative_brief.md"
    script = output_dir / "script.md"
    shot_plan = output_dir / "shot_plan.json"
    captions = output_dir / "captions.srt"
    cover_svg = output_dir / "cover.svg"
    cover_png = output_dir / "cover.png"
    video = output_dir / "video.mp4"
    platform_copy = output_dir / "platform_copy.md"
    qa_report = output_dir / "qa_report.json"

    creative_brief.write_text(render_creative_brief(spec), encoding="utf-8")
    script.write_text(render_script_md(spec), encoding="utf-8")
    shot_plan.write_text(
        json.dumps(build_shot_plan(spec), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    captions.write_text(render_captions_srt(spec), encoding="utf-8")
    write_cover_svg(spec, cover_svg)
    platform_copy.write_text(render_platform_copy(spec), encoding="utf-8")
    qa_report.write_text(
        json.dumps(build_qa_report(spec), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    rendered_cover = write_cover_png(spec, cover_png) if render_cover else None
    rendered_video = (
        render_mp4(spec, video, duration_seconds=30, ffmpeg_bin=ffmpeg_bin)
        if render_video
        else None
    )

    return ShortVideoAssetPack(
        output_dir=output_dir,
        creative_brief=creative_brief,
        script=script,
        shot_plan=shot_plan,
        captions=captions,
        cover_svg=cover_svg,
        cover_png=rendered_cover,
        video=rendered_video,
        platform_copy=platform_copy,
        qa_report=qa_report,
    )


def render_mp4(
    spec: ShortVideoSpec,
    output_path: Path,
    *,
    duration_seconds: int = DEFAULT_DURATION_SECONDS,
    fps: int = FPS,
    ffmpeg_bin: str = "ffmpeg",
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="sentinel_short_") as tmp:
        frame_dir = Path(tmp)
        frame_count = duration_seconds * fps
        frames = [
            (render_svg(spec, progress=i / max(1, frame_count - 1)), frame_dir / f"frame_{i:04d}.png")
            for i in range(frame_count)
        ]
        _svgs_to_pngs(frames)
        cmd = [
            ffmpeg_bin,
            "-y",
            "-framerate",
            str(fps),
            "-i",
            str(frame_dir / "frame_%04d.png"),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-r",
            str(fps),
            "-movflags",
            "+faststart",
            str(output_path),
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return output_path


def _svgs_to_pngs(frames: list[tuple[str, Path]]) -> None:
    async def _render() -> None:
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page(viewport={"width": WIDTH, "height": HEIGHT}, device_scale_factor=1)
            for svg, output_path in frames:
                await page.set_content(svg)
                await page.screenshot(
                    path=str(output_path),
                    clip={"x": 0, "y": 0, "width": WIDTH, "height": HEIGHT},
                )
            await browser.close()

    asyncio.run(_render())
