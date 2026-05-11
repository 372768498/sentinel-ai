from __future__ import annotations

import base64
import json
from pathlib import Path

import httpx

from .templates import build_email_html


async def send_briefing_email(
    *,
    api_key: str,
    from_email: str,
    to_email: str,
    ticker: str,
    result: dict,
    pdf_path: Path | None,
) -> str | None:
    attachments: list[dict] = []
    attachment_names: list[str] = []
    if pdf_path and pdf_path.exists():
        attachment_names.append(pdf_path.name)
        attachments.append(
            {
                "content": base64.b64encode(pdf_path.read_bytes()).decode("utf-8"),
                "filename": pdf_path.name,
            }
        )

    html = build_email_html(
        ticker=ticker,
        score=result.get("score_100"),
        rating=result.get("rating"),
        recommendation=result.get("state") or result.get("recommendation"),
        supporting_points=result.get("supporting_points", []),
        caveats=result.get("caveats", []),
    )

    payload = {
        "from": from_email,
        "to": [to_email],
        "subject": f"{ticker} | Sentinel Intelligence Briefing",
        "html": html,
        "attachments": attachments,
    }

    if not api_key:
        print("\n===== SENTINEL MOCK EMAIL BEGIN =====")
        print(json.dumps(
            {
                "from": from_email,
                "to": [to_email],
                "subject": payload["subject"],
                "attachments": attachment_names,
                "pdf_path": str(pdf_path) if pdf_path else None,
            },
            ensure_ascii=False,
            indent=2,
        ))
        print("----- HTML -----")
        print(html)
        print("===== SENTINEL MOCK EMAIL END =====\n")
        return "mock-console-delivery"

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        response.raise_for_status()
        data = response.json()
        return data.get("id")
