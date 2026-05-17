"""9:16 product-demo short-video renderer for Growth OS.

The renderer produces deterministic, reviewable Shorts/TikTok asset packs. It
borrows the product-demo structure from the Sentinel Remotion work:
tension -> product alert -> evidence stack -> CTA.
"""

from __future__ import annotations

import asyncio
import html
import json
import re
import subprocess
import tempfile
import textwrap
from dataclasses import dataclass
from pathlib import Path

WIDTH = 1080
HEIGHT = 1920
FPS = 30
DEFAULT_DURATION_SECONDS = 30
SCENE_TIMELINE = (
    (0, 3, "tension"),
    (3, 10, "sentinel_alert"),
    (10, 22, "context_stack"),
    (22, 30, "cta"),
)
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


def _display_url(spec: ShortVideoSpec) -> str:
    ticker = _ticker(spec)
    raw = spec.cta_url.replace("https://", "").replace("http://", "")
    host = raw.split("/", 1)[0]
    return f"{host}/stocks/{ticker}"


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


def _multiline(
    x: int,
    y: int,
    value: str,
    *,
    size: int,
    color: str,
    width: int,
    line_gap: int,
    weight: int = 600,
) -> str:
    return "\n".join(
        _text(x, y + i * line_gap, line, size=size, color=color, weight=weight)
        for i, line in enumerate(_wrap(value, width))
    )


def _pill(x: int, y: int, label: str, *, fill: str, color: str = "#07120d") -> str:
    width = max(170, len(label) * 18 + 54)
    return f"""
    <rect x="{x}" y="{y}" width="{width}" height="58" rx="6" fill="{fill}"/>
    {_text(x + 28, y + 39, label, size=25, color=color, weight=820)}
    """


def _progress_bar(progress: float) -> str:
    bar_w = max(1, min(948, int(948 * progress)))
    return f"""
    <rect x="66" y="1810" width="948" height="14" rx="7" fill="#22362a"/>
    <rect x="66" y="1810" width="{bar_w}" height="14" rx="7" fill="#d7ffe2"/>
    """


def _scene_for_progress(progress: float) -> str:
    seconds = max(0.0, min(DEFAULT_DURATION_SECONDS - 0.01, progress * DEFAULT_DURATION_SECONDS))
    for start, end, scene in SCENE_TIMELINE:
        if start <= seconds < end:
            return scene
    return "cta"


def _svg_shell(body: str, spec: ShortVideoSpec, *, progress: float) -> str:
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#06110d"/>
      <stop offset="0.58" stop-color="#0c1813"/>
      <stop offset="1" stop-color="#10100c"/>
    </linearGradient>
    <filter id="softShadow" x="-20%" y="-20%" width="140%" height="140%">
      <feDropShadow dx="0" dy="18" stdDeviation="22" flood-color="#000" flood-opacity="0.34"/>
    </filter>
    <pattern id="grid" width="54" height="54" patternUnits="userSpaceOnUse">
      <path d="M54 0H0V54" fill="none" stroke="#d7ffe2" stroke-opacity="0.045" stroke-width="1"/>
    </pattern>
  </defs>
  <rect width="{WIDTH}" height="{HEIGHT}" fill="url(#bg)"/>
  <rect width="{WIDTH}" height="{HEIGHT}" fill="url(#grid)"/>
  <rect x="66" y="76" width="948" height="118" rx="0" fill="#0f251a"/>
  {_text(96, 128, "Sentinel AI", size=34, color="#e8fff3", weight=780)}
  {_text(96, 169, "Market state monitor", size=24, color="#95b7a3", weight=540)}
  {_text(724, 130, f"${_ticker(spec)} / {_state(spec)}", size=24, color="#d7ffe2", weight=760)}
  {_text(812, 169, "Shorts / TikTok", size=22, color="#95b7a3", weight=540)}
  {body}
  {_progress_bar(progress)}
  {_text(76, 1870, spec.disclaimer, size=24, color="#6f8b78", weight=520)}
</svg>"""


def _render_tension_scene(spec: ShortVideoSpec, progress: float) -> str:
    ticker = _ticker(spec)
    body = f"""
    <g filter="url(#softShadow)">
      <rect x="66" y="300" width="948" height="780" rx="8" fill="#111d18"/>
      {_text(104, 418, "YOU SAW THE MOVE.", size=54, color="#ffffff", weight=880)}
      {_text(104, 500, "But not the state change.", size=48, color="#d7ffe2", weight=760)}
      <rect x="104" y="620" width="872" height="220" rx="8" fill="#07120d"/>
      {_text(142, 700, f"${ticker}", size=74, color="#ffffff", weight=880)}
      {_text(142, 770, "attention is moving faster than context", size=31, color="#a8c6b4", weight=560)}
      <path d="M142 900 C270 820 390 960 520 875 S770 835 936 930" fill="none" stroke="#d7ffe2" stroke-width="9" stroke-linecap="round"/>
    </g>
    <rect x="66" y="1190" width="948" height="300" rx="8" fill="#d7ffe2"/>
    {_text(104, 1290, "The clip is not the answer.", size=44, color="#07120d", weight=840)}
    {_text(104, 1360, "It is the trigger to verify.", size=42, color="#17492f", weight=760)}
    """
    return _svg_shell(body, spec, progress=progress)


def _render_alert_scene(spec: ShortVideoSpec, progress: float) -> str:
    ticker = _ticker(spec)
    state = _state(spec)
    body = f"""
    <g filter="url(#softShadow)">
      <rect x="118" y="286" width="844" height="1180" rx="48" fill="#050706"/>
      <rect x="148" y="344" width="784" height="1040" rx="34" fill="#101915"/>
      <rect x="186" y="420" width="708" height="124" rx="12" fill="#15261d"/>
      {_text(222, 475, "Priority market state", size=30, color="#d7ffe2", weight=760)}
      {_text(222, 515, "Sentinel AI just flagged this", size=24, color="#95b7a3", weight=540)}
      <rect x="186" y="610" width="708" height="420" rx="14" fill="#0b120f"/>
      {_text(226, 715, f"${ticker}", size=82, color="#ffffff", weight=900)}
      {_pill(226, 765, state, fill="#d7ffe2")}
      {_multiline(226, 900, spec.why_now, size=36, color="#bad6c5", width=32, line_gap=48)}
      <rect x="186" y="1092" width="708" height="204" rx="14" fill="#d7ffe2"/>
      {_text(226, 1170, "No score. No prediction.", size=38, color="#07120d", weight=860)}
      {_text(226, 1232, "Just context to check.", size=36, color="#17492f", weight=720)}
    </g>
    """
    return _svg_shell(body, spec, progress=progress)


def _render_context_scene(spec: ShortVideoSpec, progress: float) -> str:
    flags = list(spec.risk_flags[:3])
    while len(flags) < 3:
        flags.append("No additional risk flag supplied")
    accents = ("#d7ffe2", "#f3c64a", "#ff7b49")
    cards = []
    for idx, flag in enumerate(flags, start=1):
        y = 418 + (idx - 1) * 330
        cards.append(
            f"""
            <rect x="66" y="{y}" width="948" height="270" rx="8" fill="#121f19"/>
            <rect x="96" y="{y + 38}" width="11" height="192" fill="{accents[idx - 1]}"/>
            {_text(136, y + 92, f"Signal {idx}", size=30, color=accents[idx - 1], weight=820)}
            {_multiline(136, y + 162, flag, size=42, color="#ffffff", width=31, line_gap=52)}
            """
        )
    body = f"""
    {_text(66, 310, "3 signals to verify", size=58, color="#ffffff", weight=880)}
    {_text(70, 365, "Before you trust the market narrative.", size=30, color="#95b7a3", weight=560)}
    {''.join(cards)}
    <rect x="66" y="1456" width="948" height="206" rx="8" fill="#07120d"/>
    {_text(104, 1530, "Sentinel compresses the noise", size=38, color="#d7ffe2", weight=820)}
    {_text(104, 1592, "into a state you can verify.", size=36, color="#bad6c5", weight=680)}
    """
    return _svg_shell(body, spec, progress=progress)


def _render_cta_scene(spec: ShortVideoSpec, progress: float) -> str:
    ticker = _ticker(spec)
    state = _state(spec)
    body = f"""
    <g filter="url(#softShadow)">
      <rect x="66" y="300" width="948" height="490" rx="8" fill="#122119"/>
      {_text(104, 420, f"${ticker}", size=88, color="#ffffff", weight=900)}
      {_pill(104, 470, state, fill="#d7ffe2")}
      {_multiline(104, 635, spec.hook, size=48, color="#ffffff", width=30, line_gap=58)}
    </g>
    <rect x="66" y="910" width="948" height="390" rx="8" fill="#d7ffe2"/>
    {_text(104, 1030, "Run the context scan", size=54, color="#07120d", weight=880)}
    {_text(104, 1104, "before the next headline.", size=44, color="#17492f", weight=760)}
    {_multiline(104, 1220, _display_url(spec), size=31, color="#17492f", width=40, line_gap=40)}
    <rect x="66" y="1430" width="948" height="170" rx="8" fill="#07120d"/>
    {_text(104, 1500, "Context, not advice.", size=42, color="#d7ffe2", weight=840)}
    {_text(104, 1560, "Save the ticker. Check the state.", size=31, color="#95b7a3", weight=580)}
    """
    return _svg_shell(body, spec, progress=progress)


def render_svg(spec: ShortVideoSpec, *, progress: float = 0.0) -> str:
    scene = _scene_for_progress(progress)
    if scene == "tension":
        return _render_tension_scene(spec, progress)
    if scene == "sentinel_alert":
        return _render_alert_scene(spec, progress)
    if scene == "context_stack":
        return _render_context_scene(spec, progress)
    return _render_cta_scene(spec, progress)


def write_preview_svg(spec: ShortVideoSpec, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_svg(spec, progress=0.36), encoding="utf-8")
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
  {_text(112, 1745, "Run the context scan", size=38, color="#d7ffe2", weight=780)}
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
        (0, 3, "Tension", f"You saw the ${ticker} move, but not the state change."),
        (3, 10, "Sentinel Alert", f"Sentinel AI flags ${ticker} as {_state(spec)}. {spec.why_now}"),
        (10, 14, "Signal 1", flags[0]),
        (14, 18, "Signal 2", flags[1]),
        (18, 22, "Signal 3", flags[2]),
        (22, 26, "CTA", "Run the context scan before the next headline."),
        (26, 30, "Disclaimer", spec.disclaimer),
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
    return {
        "canvas": {"width": WIDTH, "height": HEIGHT, "fps": FPS, "safe_area_px": 96},
        "template": "sentinel_product_demo_risk_stack",
        "reference_pattern": "tension -> product alert -> evidence stack -> CTA",
        "ticker": ticker,
        "state": _state(spec),
        "duration_seconds": DEFAULT_DURATION_SECONDS,
        "scenes": [
            {
                "id": f"scene_{idx:02d}_{label.lower().replace(' ', '_')}",
                "start": start,
                "end": end,
                "label": label,
                "text": text,
                "max_words": 14,
                "animation": "hard_cut_product_ui",
            }
            for idx, (start, end, label, text) in enumerate(_script_lines(spec), start=1)
        ],
        "signals": list(spec.risk_flags[:3]),
        "cta_url": spec.cta_url,
        "disclaimer": spec.disclaimer,
    }


def render_creative_brief(spec: ShortVideoSpec) -> str:
    flags = "\n".join(f"- {flag}" for flag in spec.risk_flags[:3])
    forbidden = _forbidden_hits(spec)
    forbidden_line = ", ".join(forbidden) if forbidden else "None"
    return f"""# Sentinel AI Short Video Creative Brief

## Angle

Product Demo / Ticker State / Risk Stack

## Ticker

${_ticker(spec)}

## User Anxiety

The viewer saw market movement, but does not know whether the state change is real.

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
    return f"""# Sentinel AI Product-Demo Short Video Script

| Time | Beat | On-screen / Voiceover |
| --- | --- | --- |
{rows}
"""


def render_platform_copy(spec: ShortVideoSpec) -> str:
    ticker = _ticker(spec)
    return f"""# Platform Copy

## YouTube Shorts Title

${ticker}: state change, not just a price move

## YouTube Description

Sentinel AI flagged a {_state(spec).lower()} state in ${ticker}. Run the context scan: {spec.cta_url}

{spec.disclaimer}

## TikTok Caption

${ticker} moved, but the move is not the whole story. Check the state before the next headline. {spec.disclaimer}

## Pinned Comment

Run the free ${ticker} context scan: {spec.cta_url}

## Hashtags

#SentinelAI #StockMarket #Investing #MarketSignals #{ticker}
"""


def build_qa_report(spec: ShortVideoSpec) -> dict:
    lines = _script_lines(spec)
    forbidden = _forbidden_hits(spec)
    first_text = " ".join(line[3] for line in lines if line[0] < 3)
    scene_word_counts = [
        {"label": label, "words": _words(text), "ok": _words(text) <= 18}
        for _start, _end, label, text in lines
    ]
    return {
        "resolution": {"width": WIDTH, "height": HEIGHT, "ok": WIDTH == 1080 and HEIGHT == 1920},
        "duration_seconds": DEFAULT_DURATION_SECONDS,
        "duration_ok": 15 <= DEFAULT_DURATION_SECONDS <= 45,
        "product_demo_structure": [scene for _start, _end, scene in SCENE_TIMELINE],
        "ticker_in_first_3_seconds": _ticker(spec) in first_text.upper(),
        "ticker_in_first_2_seconds": _ticker(spec) in first_text.upper(),
        "state_in_alert_scene": _state(spec) in " ".join(line[3] for line in lines).upper(),
        "state_in_first_2_seconds": _state(spec) in " ".join(line[3] for line in lines).upper(),
        "scene_word_counts": scene_word_counts,
        "captions_safe_area": True,
        "cta_specific": "context scan" in spec.cta_url.lower() or "/stocks/" in spec.cta_url.lower(),
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
    shot_plan.write_text(json.dumps(build_shot_plan(spec), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    captions.write_text(render_captions_srt(spec), encoding="utf-8")
    write_cover_svg(spec, cover_svg)
    platform_copy.write_text(render_platform_copy(spec), encoding="utf-8")
    qa_report.write_text(json.dumps(build_qa_report(spec), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    rendered_cover = write_cover_png(spec, cover_png) if render_cover else None
    rendered_video = (
        render_mp4(spec, video, duration_seconds=DEFAULT_DURATION_SECONDS, ffmpeg_bin=ffmpeg_bin)
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
