"""Claude Sonnet 4.6 composer with prompt cache + redline retry + Mock Mode."""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Optional

from .personas import Persona
from .redline import RedlineResult, scan

logger = logging.getLogger(__name__)

MODEL_ID = "claude-sonnet-4-6"
MAX_RETRY = 3


@dataclass
class Composition:
    persona: str
    text: str
    redline: RedlineResult
    used_mock: bool


class ComposerError(RuntimeError):
    pass


class Composer:
    """Compose redline-compliant X posts from a Sentinel signal.

    Mock Mode is automatic when ANTHROPIC_API_KEY is missing OR dry_run=True.
    """

    def __init__(
        self,
        *,
        client=None,
        dry_run: bool = False,
        model: str = MODEL_ID,
    ):
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        self.model = model
        self.dry_run = dry_run or not api_key
        if self.dry_run:
            self.client = None
        elif client is not None:
            self.client = client
        else:
            from anthropic import Anthropic

            self.client = Anthropic(api_key=api_key)

    def compose_post(
        self,
        *,
        persona: Persona,
        ticker: str,
        change_pct: float,
        score: int,
        headline: str,
        source_url: str,
        deep_link: str,
        max_chars: int = 270,
    ) -> Composition:
        if self.dry_run or self.client is None:
            return self._mock(
                persona=persona,
                ticker=ticker,
                change_pct=change_pct,
                score=score,
                headline=headline,
                source_url=source_url,
                deep_link=deep_link,
            )

        user_prompt = self._user_prompt(
            persona=persona,
            ticker=ticker,
            change_pct=change_pct,
            score=score,
            headline=headline,
            source_url=source_url,
            max_chars=max_chars,
        )

        last_redline: Optional[RedlineResult] = None
        for attempt in range(MAX_RETRY):
            response = self.client.messages.create(
                model=self.model,
                max_tokens=600,
                system=[
                    {
                        "type": "text",
                        "text": persona.system_prompt,
                        "cache_control": {"type": "ephemeral"},
                    },
                ],
                messages=[{"role": "user", "content": user_prompt}],
            )
            text = response.content[0].text.strip()
            redline = scan(text, require_source=True, require_disclaimer=True)
            last_redline = redline
            if redline.ok and len(text) <= max_chars:
                return Composition(
                    persona=persona.name,
                    text=text,
                    redline=redline,
                    used_mock=False,
                )
            user_prompt += (
                f"\n\nDraft #{attempt + 1} failed: {redline.violations or 'over_length'}. "
                f"Rewrite, max {max_chars} chars, include source URL, end with disclaimer."
            )

        raise ComposerError(
            f"Failed redline after {MAX_RETRY} attempts. "
            f"Last violations: {last_redline.violations if last_redline else 'unknown'}"
        )

    def _user_prompt(
        self,
        *,
        persona: Persona,
        ticker: str,
        change_pct: float,
        score: int,
        headline: str,
        source_url: str,
        max_chars: int,
    ) -> str:
        sign = "+" if change_pct > 0 else ""
        return (
            f"Compose ONE X post in your persona ({persona.name}).\n\n"
            f"Signal facts (use only these — invent nothing):\n"
            f"- Ticker: ${ticker}\n"
            f"- Move: {sign}{change_pct:.2f}% intraday\n"
            f"- Sentinel score (0-100, internal): {score}\n"
            f"- Headline: {headline}\n"
            f"- Primary source: {source_url}\n\n"
            f"Constraints:\n"
            f"- Max {max_chars} chars total.\n"
            f"- Include the primary-source URL inline.\n"
            f"- End with: Context, not advice.\n\n"
            f"Voice examples for tone reference:\n"
            + "\n".join(f"- {ex}" for ex in persona.voice_examples)
        )

    def _mock(
        self,
        *,
        persona: Persona,
        ticker: str,
        change_pct: float,
        score: int,
        headline: str,
        source_url: str,
        deep_link: str,
    ) -> Composition:
        # Mock template stays close to what Claude would produce so dry-run
        # previews stay representative. No duplicated "crossed" wording.
        text = (
            f"${ticker}: {headline}. "
            f"Source: {source_url}\n\nContext, not advice."
        )
        redline = scan(text, require_source=True, require_disclaimer=True)
        return Composition(
            persona=persona.name,
            text=text,
            redline=redline,
            used_mock=True,
        )
