"""Content Factory · turn an Opportunity into three redline-scanned drafts.

Legacy draft generation fans out into:
  - X thread
  - Telegram post
  - YouTube Shorts script

Growth Content Pack fans out into:
  - X image/text post
  - Reddit image/text discussion post
  - YouTube Shorts script
  - TikTok script

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
    ?utm_source={x|reddit|telegram|youtube|tiktok}
    &utm_medium={thread|discussion|broadcast|shorts}
    &utm_campaign={campaign_id}
    &utm_content={content_id}
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from datetime import date as _date, datetime, timezone
from typing import Optional, Protocol

from .opportunities import Opportunity
from .redline import RedlineResult, scan as redline_scan
from .redline_earnings import check_earnings_window
from .review_queue import ContentDraft

logger = logging.getLogger(__name__)

DEFAULT_MODEL_ID = "claude-sonnet-4-6"


def _resolve_model() -> str:
    """Allow third-party proxies (e.g. code.newcli.com) that only support
    older Sonnet IDs to override via MARKETING_COMPOSER_MODEL."""
    return os.environ.get("MARKETING_COMPOSER_MODEL", "").strip() or DEFAULT_MODEL_ID

PLATFORM_X = "X"
PLATFORM_REDDIT = "Reddit"
PLATFORM_TELEGRAM = "Telegram"
PLATFORM_SHORTS = "YouTube Shorts"
PLATFORM_TIKTOK = "TikTok"

LEGACY_PLATFORMS = (PLATFORM_X, PLATFORM_TELEGRAM, PLATFORM_SHORTS)
GROWTH_PACK_PLATFORMS = (PLATFORM_X, PLATFORM_REDDIT, PLATFORM_SHORTS, PLATFORM_TIKTOK)
PLATFORMS = LEGACY_PLATFORMS

_UTM_SOURCE: dict[str, str] = {
    PLATFORM_X: "x",
    PLATFORM_REDDIT: "reddit",
    PLATFORM_TELEGRAM: "telegram",
    PLATFORM_SHORTS: "youtube",
    PLATFORM_TIKTOK: "tiktok",
}
_UTM_MEDIUM: dict[str, str] = {
    PLATFORM_X: "thread",
    PLATFORM_REDDIT: "discussion",
    PLATFORM_TELEGRAM: "broadcast",
    PLATFORM_SHORTS: "shorts",
    PLATFORM_TIKTOK: "shorts",
}
_PLATFORM_SUFFIX: dict[str, str] = {
    PLATFORM_X: "x",
    PLATFORM_REDDIT: "rd",
    PLATFORM_TELEGRAM: "tg",
    PLATFORM_SHORTS: "yt",
    PLATFORM_TIKTOK: "tt",
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


def _campaign_date_or_today(value: Optional[str]) -> _date:
    if value:
        try:
            return datetime.strptime(value, "%Y%m%d").date()
        except ValueError:
            pass
    return _date.today()


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
    base = (public_url or os.environ.get("GROWTH_OS_PUBLIC_URL") or "https://sentinelai.com").rstrip("/")
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
        "Write either a compact image/text post or a 4-tweet thread. "
        "Include a 'Visual brief:' line for the image card. Tone: factual, calm, no hype. "
        "FORBIDDEN words (auto-rejection): buy, sell, hold, price target, predict, "
        "guaranteed, moonshot, 100x, pump, dump, go long, go short. "
        "ALSO FORBIDDEN — DO NOT use these words at all: score, rating, "
        "X/100, out of 100, out of ten. Sentinel positioning is anomaly "
        "detection, not numeric scoring. "
        "Use the anomaly vocabulary instead: 'state', 'signal', 'context', "
        "'risk flag', 'anomaly', 'watching', 'calm', 'heated', 'inflection'. "
        "Never give recommendations."
    ),
    PLATFORM_TELEGRAM: (
        "You are Sentinel AI's Telegram channel writer for US equity context. "
        "Write a single broadcast post under 500 chars. Tone: tight, scan-friendly. "
        "Same forbidden-word list as X (including no 'score'/'rating'/'X/100'). "
        "Frame the post around the ticker's current Sentinel state. No emojis."
    ),
    PLATFORM_REDDIT: (
        "You are Sentinel AI's Reddit discussion writer for US equity context. "
        "Write a non-promotional discussion post with a plain title, body, and "
        "'Visual brief:' line for the attached image. The post must read like a "
        "market observation, not an ad. Ask one concrete discussion question. "
        "Same forbidden-word list as X (including no 'score'/'rating'/'X/100'). "
        "Frame the post around the ticker's current Sentinel state. No emojis."
    ),
    PLATFORM_SHORTS: (
        "You are Sentinel AI's video scripts writer. "
        "Write a 45-60 second vertical short-video script with time stamps: "
        "0-3s Hook, 3-10s State reveal, 10-40s 3 reasons, 40-55s CTA. "
        "Include a 'Visual brief:' line for the cover/frame direction. "
        "Same forbidden-word list (including no 'score'/'rating'/'X/100'). "
        "Lead with the ticker's Sentinel state. "
        "End with 'Context, not financial advice.'"
    ),
    PLATFORM_TIKTOK: (
        "You are Sentinel AI's TikTok short-video script writer for US equity context. "
        "Write a 30-45 second vertical script with time stamps: 0-2s Hook, "
        "2-8s State reveal, 8-32s 2-3 reasons, 32-45s CTA. "
        "Include a 'Visual brief:' line for captions and cover direction. "
        "Same forbidden-word list as X (including no 'score'/'rating'/'X/100'). "
        "Keep the language direct, not meme-heavy. "
        "End with 'Context, not financial advice.'"
    ),
}

USER_PROMPT_TEMPLATE = (
    "Opportunity:\n"
    "- Ticker: ${ticker}\n"
    "- Source: {source}\n"
    "- Intent: {intent}\n"
    "- Sentinel state: {state_label} — {state_one_liner}\n"
    "- Top tweet sample: {raw_text}\n"
    "- Evidence: {evidence}\n\n"
    "Platform: {platform}\n"
    "CTA URL (must appear inline, no shortening): {cta_url}\n\n"
    "Requirements:\n"
    "- Include the ticker as ${ticker}.\n"
    "- Frame the post around the Sentinel state above. Do NOT invent or echo "
    "  numeric scores or ratings.\n"
    "- Include at least one risk-flag sentence.\n"
    "- Include the CTA URL inline (Markdown link OK), but describe it as a "
    "stock-context preview or a way to unlock the full report. Do NOT claim "
    "the URL opens a full breakdown directly.\n"
    "- End with: Context, not financial advice.\n"
)


def _format_user_prompt(opportunity: Opportunity, platform: str, cta_url: str) -> str:
    from .state import STATE_DISPLAY, SentinelState

    state = SentinelState(opportunity.state)
    display = STATE_DISPLAY[state]
    return USER_PROMPT_TEMPLATE.format(
        ticker=opportunity.ticker.upper(),
        source=opportunity.source,
        intent=opportunity.intent,
        state_label=display["label"],
        state_one_liner=display["one_liner"],
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


def _clean_generated_text(body: str) -> str:
    """Normalize common proxy/model encoding artifacts before review."""
    replacements = {
        "\u9208\u9239?": "'",
        "\u9208\u922b?": "->",
        "\u8103": "x",
    }
    cleaned = body
    for bad, good in replacements.items():
        cleaned = cleaned.replace(bad, good)
    cleaned = re.sub(r"\s*[\u0400-\u04ff]{1,4}\s*", " - ", cleaned)
    cleaned = re.sub(
        r"\bFull anomaly breakdown\b",
        "Stock context preview",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"\bFull breakdown\b",
        "Stock context preview",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"\bfull anomaly report\b",
        "full report",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\s*[\u659c\u6cfb\u5fcc\u6297]{1,4}\s*", " - ", cleaned)
    return cleaned.replace("\r\n", "\n").strip()


# ---- Feature flag: USE_NEW_TEMPLATES → swap Telegram body source ----
#
# When USE_NEW_TEMPLATES env is truthy AND the platform is Telegram, the
# body is rendered from the deterministic free_telegram_anomaly template
# instead of the LLM composer. ALL other pipeline stages (redline scan,
# earnings-window check, Feishu submission) run unchanged. Flipping the
# flag back to false instantly restores the LLM path — no code revert.


def _use_new_templates_for_telegram() -> bool:
    return os.environ.get("USE_NEW_TEMPLATES", "").strip().lower() in (
        "1", "true", "yes", "on",
    )


def _build_free_telegram_anomaly_payload(
    opportunity: Opportunity, cta_url: str
):
    """Build an AnomalyPayload from an Opportunity + sensible defaults.

    Sprint 1 wire-up: many free_telegram fields (uniqueness_line,
    confirming_list, disagreeing_list, narrative_one_paragraph) need
    data that's only partially available on Opportunity today. We
    extract what we can from opportunity.evidence and fall back to
    transparent placeholders. Future rounds should pass a richer
    payload-builder or attach a structured profile_snapshot to
    Opportunity.evidence.
    """
    from .state import SentinelState
    from .templates.free_telegram import AnomalyPayload

    state = SentinelState(opportunity.state)
    evidence = opportunity.evidence or {}
    mover = evidence.get("mover", {}) or {}
    intel = evidence.get("intelligence_profile", {}) or {}

    confirming: list[str] = []
    disagreeing: list[str] = []
    for label, key in (
        ("market", "market_heat"),
        ("social", "social_heat"),
        ("search", "search_heat"),
        ("news", "news_heat"),
        ("competitor", "competitor_heat"),
    ):
        v = intel.get(key)
        if isinstance(v, (int, float)):
            if v >= 65:
                confirming.append(label)
            elif v <= 20:
                disagreeing.append(label)

    sources = intel.get("sources_used")
    src_label = f"{sources} sources" if isinstance(sources, int) and sources else "internal"

    change_pct = mover.get("change_pct")
    if change_pct is None:
        change_pct = 0.0
    price = mover.get("price")
    if price is None:
        price = 0.0
    volume_rel = mover.get("relative_volume")
    if volume_rel is None:
        volume_rel = 1.0

    now_utc = datetime.now(timezone.utc)
    return AnomalyPayload(
        session_label=evidence.get("session_label", "Daily scan"),
        timestamp_et=now_utc.strftime("%H:%M UTC"),
        state=state,
        ticker=opportunity.ticker,
        price=float(price),
        session_change_label="Intraday",
        price_change_pct=float(change_pct),
        volume_relative=float(volume_rel),
        anomaly_one_liner=(opportunity.raw_text or "Signal density elevated.")[:200],
        uniqueness_line=intel.get("uniqueness_line")
        or "Sector context: not available this run.",
        confirming_list=", ".join(confirming) or "anomaly signal",
        disagreeing_list=", ".join(disagreeing) or "no strong counter-signal",
        narrative_one_paragraph=(
            intel.get("why_now")
            or opportunity.raw_text
            or "Multiple signals overlap on this ticker today."
        )[:280],
        risk_one_liner="Position sizing matters more than direction.",
        source_categories=src_label,
        cta_url=cta_url,
        pro_url=evidence.get("pro_url", "https://app.jilo.ai/pro"),
    )


def _render_free_telegram_body(opportunity: Opportunity, cta_url: str) -> str:
    """Render the free Telegram anomaly body via the deterministic template."""
    from .templates.free_telegram import render_anomaly

    payload = _build_free_telegram_anomaly_payload(opportunity, cta_url)
    return render_anomaly(payload)


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


def _apply_earnings_window(
    body: str,
    redline: RedlineResult,
    earnings_date: Optional[_date],
    today: Optional[_date] = None,
) -> RedlineResult:
    """Overlay pre-earnings redline on top of the generic redline result.

    Out-of-window or no calendar data → returns the input result unchanged.
    Blocked phrase inside window → returns a new RedlineResult with the
    earnings violation appended (and ok=False so risk_level escalates).
    """
    if earnings_date is None:
        return redline
    earn = check_earnings_window(
        text=body, earnings_date=earnings_date, today=today
    )
    if earn.ok:
        return redline
    return RedlineResult(
        ok=False,
        violations=redline.violations + (earn.reason(),),
        has_source=redline.has_source,
        has_disclaimer=redline.has_disclaimer,
    )


def create_drafts_for_opportunity(
    opportunity: Opportunity,
    *,
    composer: Optional[ComposerLike] = None,
    campaign_id: Optional[str] = None,
    date: Optional[str] = None,
    public_url: Optional[str] = None,
    earnings_date: Optional[_date] = None,
    platforms: tuple[str, ...] = PLATFORMS,
) -> DraftBundle:
    """Generate one ContentDraft per platform for an Opportunity.

    Each draft is redline-scanned. Drafts that fail redline are still returned
    (with `risk_level=High`) so the review queue can capture the failure for
    human inspection — they are NOT silently dropped, and they are NOT auto-fixed.

    When `earnings_date` is provided AND the draft falls in the pre-earnings
    window (default -2 to +7 days), an additional directional-language check
    runs and may push the draft into a redline violation. Caller is
    responsible for the earnings calendar lookup (see data_sources/
    earnings_calendar.py::fetch_next_earnings_date).
    """
    cmp = composer or build_default_composer()
    camp = campaign_id or campaign_id_for(date)
    redline_today = _campaign_date_or_today(date)
    drafts: list[ContentDraft] = []
    redlines: dict[str, RedlineResult] = {}

    use_new_telegram = _use_new_templates_for_telegram()

    for platform in platforms:
        cid = content_id_for(opportunity, platform, date=date)
        cta = build_cta_url(opportunity, platform, camp, cid, public_url=public_url)
        if platform == PLATFORM_TELEGRAM and use_new_telegram:
            # Feature flag path: deterministic template, no LLM call.
            try:
                body = _render_free_telegram_body(opportunity, cta)
            except Exception as exc:
                logger.exception(
                    "[content_factory] new-template render failed for %s on %s: %s",
                    opportunity.opportunity_id,
                    platform,
                    exc,
                )
                continue
        else:
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

        body = _clean_generated_text(body)
        redline = redline_scan(body, require_source=True, require_disclaimer=True)
        redline = _apply_earnings_window(
            body, redline, earnings_date, today=redline_today
        )
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


def create_growth_pack_for_opportunity(
    opportunity: Opportunity,
    *,
    composer: Optional[ComposerLike] = None,
    campaign_id: Optional[str] = None,
    date: Optional[str] = None,
    public_url: Optional[str] = None,
    earnings_date: Optional[_date] = None,
) -> DraftBundle:
    """Generate Sentinel's acquisition pack for X, Reddit, Shorts, and TikTok."""
    return create_drafts_for_opportunity(
        opportunity,
        composer=composer,
        campaign_id=campaign_id,
        date=date,
        public_url=public_url,
        earnings_date=earnings_date,
        platforms=GROWTH_PACK_PLATFORMS,
    )
