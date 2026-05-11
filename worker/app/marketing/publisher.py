"""Orchestrator: scanner signal -> Composer -> redline -> XClient post + deep-link."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from .composer import Composer
from .personas import ALL_PERSONAS, Persona
from .tracker import build_deep_link, build_payload
from .x_client import PostResult, XClient

logger = logging.getLogger(__name__)


@dataclass
class PublishOutcome:
    ticker: str
    persona: str
    text: str
    deep_link: str
    redline_ok: bool
    redline_violations: tuple[str, ...]
    post_result: PostResult


class Publisher:
    def __init__(
        self,
        *,
        composer: Composer,
        x_client: XClient,
        bot_username: str,
        source_label: str = "xtw",
    ):
        self.composer = composer
        self.x_client = x_client
        self.bot_username = bot_username
        self.source_label = source_label

    def _pick_persona(self, score: int, ticker: str) -> Persona:
        # Deterministic rotation so the same ticker on the same day always gets
        # the same persona (avoids one ticker being narrated by 2 voices).
        index = (score + sum(ord(c) for c in ticker)) % len(ALL_PERSONAS)
        return ALL_PERSONAS[index]

    async def publish_alert(
        self,
        *,
        ticker: str,
        change_pct: float,
        score: int,
        headline: str,
        source_url: str,
        persona: Optional[Persona] = None,
        max_chars: int = 270,
    ) -> PublishOutcome:
        persona = persona or self._pick_persona(score, ticker)
        payload = build_payload(source=self.source_label, score=score, ticker=ticker)
        deep_link = build_deep_link(self.bot_username, payload)

        composition = self.composer.compose_post(
            persona=persona,
            ticker=ticker,
            change_pct=change_pct,
            score=score,
            headline=headline,
            source_url=source_url,
            deep_link=deep_link,
            max_chars=max_chars,
        )

        text = composition.text
        if deep_link not in text:
            text = f"{text}\n\n{deep_link}"

        post_result = await self.x_client.post(text)
        outcome = PublishOutcome(
            ticker=ticker,
            persona=persona.name,
            text=text,
            deep_link=deep_link,
            redline_ok=composition.redline.ok,
            redline_violations=composition.redline.violations,
            post_result=post_result,
        )
        logger.info(
            "publish ticker=%s persona=%s redline_ok=%s posted=%s tweet_id=%s",
            ticker,
            persona.name,
            outcome.redline_ok,
            post_result.posted,
            post_result.tweet_id,
        )
        return outcome
