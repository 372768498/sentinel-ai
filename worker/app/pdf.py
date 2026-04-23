from __future__ import annotations

from pathlib import Path

import markdown
from playwright.async_api import async_playwright


def _render_report_html(markdown_text: str, title: str) -> str:
    body = markdown.markdown(
        markdown_text,
        extensions=["tables", "fenced_code", "toc"],
    )
    return f"""
    <html lang="zh-CN">
      <head>
        <meta charset="utf-8" />
        <title>{title}</title>
        <style>
          body {{
            margin: 0;
            padding: 32px 40px;
            font-family: "Inter", "Segoe UI", sans-serif;
            background: #f7f7f5;
            color: #111827;
          }}
          main {{
            max-width: 860px;
            margin: 0 auto;
            background: white;
            border: 1px solid #e5e7eb;
            padding: 48px;
            box-shadow: 0 18px 40px rgba(0,0,0,.08);
          }}
          h1, h2, h3 {{
            color: #0f172a;
          }}
          h1 {{
            border-bottom: 2px solid #111827;
            padding-bottom: 10px;
          }}
          pre {{
            padding: 16px;
            background: #0b1220;
            color: #e5f0ff;
            overflow: auto;
          }}
          code {{
            font-family: "JetBrains Mono", monospace;
          }}
          table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
          }}
          th, td {{
            border: 1px solid #d1d5db;
            padding: 10px 12px;
            text-align: left;
          }}
          th {{
            background: #f3f4f6;
          }}
          blockquote {{
            margin: 18px 0;
            padding: 12px 18px;
            border-left: 4px solid #0f766e;
            background: #f0fdfa;
          }}
        </style>
      </head>
      <body>
        <main>{body}</main>
      </body>
    </html>
    """


async def generate_pdf(
    markdown_text: str,
    output_path: Path,
    title: str,
    chromium_executable: str | None = None,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    html = _render_report_html(markdown_text, title)

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            headless=True,
            executable_path=chromium_executable or None,
        )
        page = await browser.new_page()
        await page.set_content(html, wait_until="networkidle")
        await page.pdf(
            path=str(output_path),
            format="A4",
            print_background=True,
            margin={"top": "18mm", "right": "12mm", "bottom": "18mm", "left": "12mm"},
        )
        await browser.close()
