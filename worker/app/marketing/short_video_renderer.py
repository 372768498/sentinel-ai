"""Minimal 9:16 short-video renderer for Growth OS.

The first production goal is not cinematic AI video. It is a reliable,
reviewable, platform-safe information card that turns one market opportunity
into an mp4 preview for YouTube Shorts / TikTok manual upload.
"""

from __future__ import annotations

import html
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


@dataclass(frozen=True)
class ShortVideoSpec:
    ticker: str
    state: str
    hook: str
    why_now: str
    risk_flags: tuple[str, ...]
    cta_url: str
    disclaimer: str = "Context, not financial advice."


def _wrap(text: str, width: int) -> list[str]:
    return textwrap.wrap(text.strip(), width=width, break_long_words=False) or [""]


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
    ticker = spec.ticker.strip().upper().lstrip("$")
    state = spec.state.strip().upper()
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
