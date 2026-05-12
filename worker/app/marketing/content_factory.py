"""Content Factory · turn an Opportunity into three redline-scanned drafts.

Each Opportunity fans out into:
  - X thread
  - Telegram post
  - YouTube Shorts script

LLM rules (per Week 3 spec):
  - Mock content NEVER reaches Feishu. If ANTHROPIC_API_KEY is missing and no
    composer was injected, `MultiPlatformComposer()` raises ContentFactoryError.
  - Tests inject a fake composer (any object exposing `.compose(...)`).
  - Redline is enforced AFTER LLM output. A blocked draft is still returned to
    the caller so it can submit_to_review with `redline_result=Blocked` (caller
    decides whether to push to Feishu — by design, even blocked drafts go to
    the review queue so humans can see the failure pattern).

CTA URL convention (matches Week 1 /stocks/[ticker] page):
  {GROWTH_OS_PUBLIC_URL}/stocks/{TICKER}
    ?utm_source={x|telegram|youtube}
    &utm_medium={thread|broadcast|shorts}
    &utm_campaign={campaign_id}
    &utm_content={content_id}
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Protocol

from .opportunities import Opportunity
from .redline import RedlineResult, scan as redline_scan
from .review_queue import ContentDraft

logger = logging.getLogger(__name__)

DEFAULT_MODEL_ID = "claude-sonnet-4-6"


def _resolve_model() -> str:
    """Allow third-party proxies (e.g. code.newcli.com) that only support
    older Sonnet IDs to override via MARKETING_COMPOSER_MODEL."""
    return os.environ.get("MARKETING_COMPOSER_MODEL", "").strip() or DEFAULT_MODEL_ID

PLATFORM_X = "X"
PLATFORM_TELEGRAM = "Telegram"
PLATFORM_SHORTS = "YouTube Shorts"
PLATFORMS = (PLATFORM_X, PLATFORM_TELEGRAM, PLATFORM_SHORTS)

_UTM_SOURCE: dict[str, str] = {
    PLATFORM_X: "x",
    PLATFORM_TELEGRAM: "telegram",
    PLATFORM_SHORTS: "youtube",
}
_UTM_MEDIUM: dict[str, str] = {
    PLATFORM_X: "thread",
    PLATFORM_TELEGRAM: "broadcast",
    PLATFORM_SHORTS: "shorts",
}
_PLATFORM_SUFFIX: dict[str, str] = {
    PLATFORM_X: "x",
    PLATFORM_TELEGRAM: "tg",
    PLATFORM_SHORTS: "yt",
}


class ContentFactoryError(RuntimeError):
    pass


class ComposerLike(Protocol):
    def compose(self, *, opportunity: Opportunity, platform: str, cta_url: str) -> str: ...


@dataclass(frozen=True)
class DraftBundle:
    """Output of create_drafts_for_opportunity — drafts + per-draft redline."""
    drafts: list[ContentDraft]
    redlines: dict[str, RedlineResult]  # content_id → result


# ---- ID + URL helpers ----


def _today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d")


def content_id_for(opportunity: Opportunity, platform: str, date: Optional[str] = None) -> str:
    suffix = _PLATFORM_SUFFIX[platform]
    return f"CT-{date or _today_str()}-{opportunity.ticker.upper()}-{suffix}"


def campaign_id_for(date: Optional[str] = None) -> str:
    return f"CMP-{date or _today_str()}-daily"


def build_cta_url(
    opportunity: Opportunity,
    platform: str,
    campaign_id: str,
    content_id: str,
    *,
    public_url: Optional[str] = None,
) -> str:
    base = (public_url or os.environ.get("GROWTH_OS_PUBLIC_URL") or "http://localhost:3000").rstrip("/")
    return (
        f"{base}/stocks/{opportunity.ticker.upper()}"
        f"?utm_source={_UTM_SOURCE[platform]}"
        f"&utm_medium={_UTM_MEDIUM[platform]}"
        f"&utm_campaign={campaign_id}"
        f"&utm_content={content_id}"
    )


# ---- LLM composer (Anthropic Sonnet 4.6) ----


SYSTEM_PROMPTS: dict[str, str] = {
    PLATFORM_X: (
        "You are Sentinel AI's X (Twitter) writer for US equity context. "
        "Write a 4-tweet thread. Tone: factual, calm, no hype. "
        "FORBIDDEN words (auto-rejection): buy, sell, hold, price target, predict, "
        "guaranteed, moonshot, 100x, pump, dump, go long, go short. "
        "Use the analysis vocabulary: 'score', 'context', 'risk flag', 'analysis'. "
        "Never give recommendations."
    ),
    PLATFORM_TELEGRAM: (
        "You are Sentinel AI's Telegram channel writer for US equity context. "
        "Write a single broadcast post under 500 chars. Tone: tight, scan-friendly. "
        "Same forbidden-word list as X. No emojis."
    ),
    PLATFORM_SHORTS: (
        "You are Sentinel AI's video scripts writer. "
        "Write a 45-60 second vertical short-video script with time stamps: "
        "0-3s Hook, 3-10s Score reveal, 10-40s 3 reasons, 40-55s CTA. "
        "Same forbidden-word list. End with 'Context, not financial advice.'"
    ),
}

USER_PROMPT_TEMPLATE = (
    "Opportunity:\n"
    "- Ticker: ${ticker}\n"
    "- Source: {source}\n"
    "- Intent: {intent}\n"
    "- Opportunity score (0-100): {score}\n"
    "- Top tweet sample: {raw_text}\n"
    "- Evidence: {evidence}\n\n"
    "Platform: {platform}\n"
    "CTA URL (must appear inline, no shortening): {cta_url}\n\n"
    "Requirements:\n"
    "- Include the ticker as ${ticker}.\n"
    "- Include at least one risk-flag sentence.\n"
    "- Include the CTA URL inline (Markdown link OK).\n"
    "- End with: Context, not financial advice.\n"
    "- Do not invent numerical scores or price targets. Use the score given.\n"
)


def _format_user_prompt(opportunity: Opportunity, platform: str, cta_url: str) -> str:
    return USER_PROMPT_TEMPLATE.format(
        ticker=opportunity.ticker.upper(),
        source=opportunity.source,
        intent=opportunity.intent,
        score=opportunity.opportunity_score,
        raw_text=opportunity.raw_text[:200],
        evidence=opportunity.evidence,
        platform=platform,
        cta_url=cta_url,
    )


class MultiPlatformComposer:
    """Anthropic-backed composer for X / Telegram / Shorts drafts.

    Raises ContentFactoryError at construction if ANTHROPIC_API_KEY is missing
    and no client was injected — mock content must NEVER reach Feishu.
    """

    def __init__(
        self,
        *,
        client=None,
        model: Optional[str] = None,
        max_tokens: int = 800,
    ) -> None:
        if client is None:
            api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
            if not api_key:
                raise ContentFactoryError(
                    "ANTHROPIC_API_KEY missing — refusing to generate mock content. "
                    "Set the key in .env.local or inject a test composer."
                )
            from anthropic import Anthropic

            base_url = os.environ.get("ANTHROPIC_BASE_URL", "").strip()
            kwargs: dict = {"api_key": api_key}
            if base_url:
                kwargs["base_url"] = base_url
            client = Anthropic(**kwargs)
        self.client = client
        self.model = model or _resolve_model()
        self.max_tokens = max_tokens

    def compose(self, *, opportunity: Opportunity, platform: str, cta_url: str) -> str:
        if platform not in SYSTEM_PROMPTS:
            raise ContentFactoryError(f"Unsupported platform: {platform}")
        system = SYSTEM_PROMPTS[platform]
        user = _format_user_prompt(opportunity, platform, cta_url)
        response = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user}],
        )
        return response.content[0].text.strip()


# ---- OpenAI-compatible fallback composer ----


def _resolve_fallback_model() -> str:
    """Configured model for the fallback proxy (e.g. fox serves `gpt-5.5`)."""
    return os.environ.get("MARKETING_FALLBACK_MODEL", "").strip() or "gpt-5.5"


class OpenAICompatibleComposer:
    """OpenAI-Chat-Completions composer used as a fallback when the Anthropic
    proxy is rate-limited. Works with any provider exposing
    `POST /chat/completions` — fox, OpenRouter, vLLM, etc.

    Like `MultiPlatformComposer`, raises `ContentFactoryError` at construction
    if no API key is available — mock content NEVER reaches Feishu.
    """

    def __init__(
        self,
        *,
        client=None,
        model: Optional[str] = None,
        max_tokens: int = 800,
    ) -> None:
        if client is None:
            api_key = os.environ.get("MARKETING_FALLBACK_API_KEY", "").strip()
            if not api_key:
                raise ContentFactoryError(
                    "MARKETING_FALLBACK_API_KEY missing — cannot construct fallback composer."
                )
            from openai import OpenAI

            base_url = os.environ.get("MARKETING_FALLBACK_BASE_URL", "").strip()
            kwargs: dict = {"api_key": api_key}
            if base_url:
                kwargs["base_url"] = base_url
            client = OpenAI(**kwargs)
        self.client = client
        self.model = model or _resolve_fallback_model()
        self.max_tokens = max_tokens

    def compose(self, *, opportunity: Opportunity, platform: str, cta_url: str) -> str:
        if platform not in SYSTEM_PROMPTS:
            raise ContentFactoryError(f"Unsupported platform: {platform}")
        system = SYSTEM_PROMPTS[platform]
        user = _format_user_prompt(opportunity, platform, cta_url)
        response = self.client.chat.completions.create(
            model=self.model,
            max_tokens=self.max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return response.choices[0].message.content.strip()


# ---- Fallback wrapper ----


class FallbackComposer:
    """Tries `primary.compose(...)` first. On `anthropic.RateLimitError` (or
    any anthropic.APIStatusError 429-class), delegates to `fallback.compose(...)`.

    All other exceptions propagate from the primary path — only rate limits
    trigger the fallback by design (so we don't silently mask real bugs).
    """

    def __init__(self, *, primary, fallback) -> None:
        self.primary = primary
        self.fallback = fallback

    def compose(self, *, opportunity: Opportunity, platform: str, cta_url: str) -> str:
        try:
            return self.primary.compose(
                opportunity=opportunity, platform=platform, cta_url=cta_url
            )
        except Exception as exc:
            if not self._is_rate_limited(exc):
                raise
            logger.warning(
                "[content_factory] primary composer rate-limited on %s — using fallback (%s)",
                platform,
                type(exc).__name__,
            )
            return self.fallback.compose(
                opportunity=opportunity, platform=platform, cta_url=cta_url
            )

    @staticmethod
    def _is_rate_limited(exc: Exception) -> bool:
        # anthropic.RateLimitError is the canonical signal; but proxies sometimes
        # raise APIStatusError with status 429 or a string body containing rate
        # limit phrasing. Catch both shapes.
        try:
            from anthropic import APIStatusError, RateLimitError

            if isinstance(exc, RateLimitError):
                return True
            if isinstance(exc, APIStatusError) and getattr(exc, "status_code", None) == 429:
                return True
        except ImportError:
            pass
        msg = str(exc).lower()
        return any(needle in msg for needle in ("rate limit", "too many requests", "请求过于频繁"))


def build_default_composer() -> ComposerLike:
    """Construct the production composer: Anthropic primary, optional fallback.

    Returns a plain `MultiPlatformComposer` when no fallback creds are set;
    wraps in `FallbackComposer` when `MARKETING_FALLBACK_API_KEY` is present.
    """
    primary = MultiPlatformComposer()
    if not os.environ.get("MARKETING_FALLBACK_API_KEY", "").strip():
        return primary
    fallback = OpenAICompatibleComposer()
    return FallbackComposer(primary=primary, fallback=fallback)


# ---- Hook extraction ----


def _extract_hook(body: str, *, max_chars: int = 140) -> str:
    """First non-empty sentence (or first line) as a hook."""
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        sentence = re.split(r"(?<=[.!?])\s", stripped, maxsplit=1)[0]
        return sentence[:max_chars].rstrip()
    return body[:max_chars].rstrip()


# ---- Risk level ----


def _risk_level(opportunity: Opportunity, redline: RedlineResult) -> str:
    if not redline.ok:
        return "High"
    if opportunity.compliance_risk >= 50:
        return "High"
    if opportunity.compliance_risk >= 20:
        return "Medium"
    return "Low"


# ---- Public API ----


def create_drafts_for_opportunity(
    opportunity: Opportunity,
    *,
    composer: Optional[ComposerLike] = None,
    campaign_id: Optional[str] = None,
    date: Optional[str] = None,
    public_url: Optional[str] = None,
) -> DraftBundle:
    """Generate one ContentDraft per platform for an Opportunity.

    Each draft is redline-scanned. Drafts that fail redline are still returned
    (with `risk_level=High`) so the review queue can capture the failure for
    human inspection — they are NOT silently dropped, and they are NOT auto-fixed.
    """
    cmp = composer or build_default_composer()
    camp = campaign_id or campaign_id_for(date)
    drafts: list[ContentDraft] = []
    redlines: dict[str, RedlineResult] = {}

    for platform in PLATFORMS:
        cid = content_id_for(opportunity, platform, date=date)
        cta = build_cta_url(opportunity, platform, camp, cid, public_url=public_url)
        try:
            body = cmp.compose(opportunity=opportunity, platform=platform, cta_url=cta)
        except Exception as exc:
            logger.exception(
                "[content_factory] composer failed for %s on %s: %s",
                opportunity.opportunity_id,
                platform,
                exc,
            )
            continue

        redline = redline_scan(body, require_source=True, require_disclaimer=True)
        redlines[cid] = redline
        drafts.append(
            ContentDraft(
                content_id=cid,
                campaign_id=camp,
                platform=platform,
                ticker=opportunity.ticker.upper(),
                hook=_extract_hook(body),
                body=body,
                cta_url=cta,
                risk_level=_risk_level(opportunity, redline),
                publish_time=None,
                source_opportunity_id=opportunity.opportunity_id,
            )
        )

    return DraftBundle(drafts=drafts, redlines=redlines)
