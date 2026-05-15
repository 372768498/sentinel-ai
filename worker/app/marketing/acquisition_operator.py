"""Daily acquisition operator for the Sentinel AI Growth OS.

This is the "do not ask unless blocked" orchestration layer:

1. scan opportunities,
2. create X / Reddit / YouTube Shorts / TikTok drafts,
3. submit drafts to review,
4. generate reviewable short-video asset packs,
5. write a daily operator summary for the human operator.

Platform publishing remains owned by the review poller and publisher modules.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Awaitable, Callable, Optional

from .content_factory import (
    ContentFactoryError,
    GROWTH_PACK_PLATFORMS,
    PLATFORM_SHORTS,
    PLATFORM_TIKTOK,
    MultiPlatformComposer,
    create_growth_pack_for_opportunity,
)
from .feishu_client import FeishuAPIError, FeishuClient
from .jobs import _min_opportunity_score, _top_opportunities_count
from .kpi_db import KPIDBError, fetch_all_metrics
from .opportunities import ACTION_CREATE_CONTENT, Opportunity
from .review_queue import ContentDraft, ReviewQueueError, submit_draft_to_review
from .short_video_renderer import ShortVideoSpec, write_asset_pack
from .signal_layer import DEFAULT_WATCHLIST, scan_x_opportunities

logger = logging.getLogger(__name__)

SubmitFn = Callable[..., Awaitable[object]]
ScannerFn = Callable[..., Awaitable[list[Opportunity]]]
KPIFetcherFn = Callable[..., Awaitable[dict[str, dict[str, int]]]]


@dataclass(frozen=True)
class OperatorDraftResult:
    content_id: str
    platform: str
    ticker: str
    risk_level: str
    redline_ok: bool
    submitted_to_review: bool
    review_error: str | None
    video_pack_dir: str | None


@dataclass(frozen=True)
class OperatorKPIDecision:
    group_key: str
    platform: str
    content_count: int
    clicks: int
    emails_captured: int
    signups: int
    paid_users: int
    click_to_email_rate: float
    decision: str
    reason: str


@dataclass(frozen=True)
class OperatorRunResult:
    run_id: str
    session: str
    output_dir: str
    opportunities_scanned: int
    opportunities_selected: int
    drafts_created: int
    submitted_to_review: int
    video_packs_created: int
    blocked_count: int
    kpi_items_reviewed: int
    kpi_decisions: list[OperatorKPIDecision]
    errors: list[str]
    drafts: list[OperatorDraftResult]


def _operator_output_root() -> Path:
    raw = os.environ.get("MARKETING_ACQUISITION_OPERATOR_OUTPUT_DIR", "").strip()
    if raw:
        return Path(raw)
    return Path("docs") / "growth-runs"


def _kpi_lookback_days() -> int:
    raw = os.environ.get("MARKETING_ACQUISITION_OPERATOR_KPI_LOOKBACK_DAYS", "7")
    try:
        return max(1, min(30, int(raw)))
    except ValueError:
        return 7


def _run_id(content_date: str | None = None) -> str:
    if content_date:
        return content_date
    return datetime.now(timezone.utc).strftime("%Y%m%d%H%M")


def _video_spec_from_draft(draft: ContentDraft, opportunity: Opportunity) -> ShortVideoSpec:
    evidence = opportunity.evidence or {}
    risk_flags = _risk_flags(draft, opportunity)
    why_now = (
        _string_or_none(evidence.get("why_now"))
        or _string_or_none(evidence.get("state_one_liner"))
        or _shorten(opportunity.raw_text, 74)
        or "Signals overlap enough to verify context today."
    )
    return ShortVideoSpec(
        ticker=draft.ticker,
        state=opportunity.state,
        hook=_shorten(draft.hook, 84) or f"${draft.ticker} has signals to verify.",
        why_now=_shorten(why_now, 74),
        risk_flags=risk_flags,
        cta_url=draft.cta_url,
    )


def _risk_flags(draft: ContentDraft, opportunity: Opportunity) -> tuple[str, ...]:
    evidence = opportunity.evidence or {}
    explicit = evidence.get("risk_flags")
    if isinstance(explicit, list):
        flags = [str(item).strip() for item in explicit if str(item).strip()]
        if flags:
            return tuple(flags[:3])

    lines = [
        line.strip(" -•\t")
        for line in draft.body.splitlines()
        if "risk" in line.lower() or "flag" in line.lower()
    ]
    flags = [_shorten(line, 42) for line in lines if line]
    if flags:
        return tuple(flags[:3])

    return (
        "Attention crowding",
        "Catalyst proximity",
        "Narrative shift",
    )


def _string_or_none(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _shorten(value: str, max_chars: int) -> str:
    cleaned = " ".join(value.split())
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 1].rstrip() + "…"


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_markdown_outputs(result: OperatorRunResult, out_dir: Path) -> None:
    blocked = [d for d in result.drafts if d.review_error or not d.redline_ok]
    videos = [d for d in result.drafts if d.video_pack_dir]

    queue_lines = [
        "# Content Queue Summary",
        "",
        f"- Run: `{result.run_id}`",
        f"- Drafts created: {result.drafts_created}",
        f"- Submitted to review: {result.submitted_to_review}",
        "",
        "| content_id | platform | ticker | redline | submitted |",
        "| --- | --- | --- | --- | --- |",
    ]
    for draft in result.drafts:
        queue_lines.append(
            f"| `{draft.content_id}` | {draft.platform} | ${draft.ticker} | "
            f"{'pass' if draft.redline_ok else 'blocked'} | "
            f"{'yes' if draft.submitted_to_review else 'no'} |"
        )
    (out_dir / "content_queue_summary.md").write_text("\n".join(queue_lines) + "\n", encoding="utf-8")

    video_lines = [
        "# Video Pack Index",
        "",
        "| content_id | platform | ticker | pack |",
        "| --- | --- | --- | --- |",
    ]
    for draft in videos:
        video_lines.append(
            f"| `{draft.content_id}` | {draft.platform} | ${draft.ticker} | `{draft.video_pack_dir}` |"
        )
    if not videos:
        video_lines.append("| - | - | - | no video packs created |")
    (out_dir / "video_pack_index.md").write_text("\n".join(video_lines) + "\n", encoding="utf-8")

    blocked_lines = [
        "# Blocked Items",
        "",
        "| content_id | platform | reason |",
        "| --- | --- | --- |",
    ]
    for draft in blocked:
        reason = draft.review_error or "redline blocked"
        blocked_lines.append(f"| `{draft.content_id}` | {draft.platform} | {reason} |")
    if not blocked:
        blocked_lines.append("| - | - | none |")
    (out_dir / "blocked_items.md").write_text("\n".join(blocked_lines) + "\n", encoding="utf-8")

    kpi_lines = [
        "# KPI 决策",
        "",
        "> 规则：连续无留资的内容组暂停；click-to-email 表现好的内容组加码；其他保留继续观察。",
        "",
        "| 分组 | 平台 | 内容数 | 点击 | 留资 | 注册 | 付费 | click-to-email | 决策 | 原因 |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for decision in result.kpi_decisions:
        kpi_lines.append(
            f"| `{decision.group_key}` | {decision.platform} | {decision.content_count} | "
            f"{decision.clicks} | {decision.emails_captured} | {decision.signups} | "
            f"{decision.paid_users} | {decision.click_to_email_rate:.2%} | "
            f"{decision.decision} | {decision.reason} |"
        )
    if not result.kpi_decisions:
        kpi_lines.append("| - | - | 0 | 0 | 0 | 0 | 0 | 0.00% | 观察 | 暂无可复盘 KPI 数据 |")
    (out_dir / "kpi_decisions.md").write_text("\n".join(kpi_lines) + "\n", encoding="utf-8")

    next_actions = [
        "# Next Actions",
        "",
        "Default operator decisions:",
        "",
        "- X：继续进入审核队列；live posting 只有在开关打开后才自动发布。",
        "- Reddit：第一阶段只生成草稿，继续人工发布。",
        "- Shorts/TikTok：继续生成可审核素材包，暂不自动上传。",
        "- AdsPower：直到某个内容角度稳定获得 email lead 前不启动。",
        "",
        "Tomorrow / 明天动作:",
        "",
    ]
    if result.kpi_decisions:
        for decision in result.kpi_decisions:
            next_actions.append(
                f"- {decision.decision} `{decision.group_key}`：{decision.reason}"
            )
    else:
        next_actions.extend(
            [
                "- 继续跑第一批内容，先积累可复盘 KPI。",
                "- 暂不扩平台，优先让 `content_id -> email lead` 数据闭环稳定。",
            ]
        )
    (out_dir / "next_actions.md").write_text("\n".join(next_actions) + "\n", encoding="utf-8")


def build_kpi_decisions(metrics: dict[str, dict[str, int]]) -> list[OperatorKPIDecision]:
    grouped: dict[str, dict[str, int | str]] = {}
    for content_id, item in metrics.items():
        platform = _platform_from_content_id(content_id)
        group_key = f"{platform}:all"
        current = grouped.setdefault(
            group_key,
            {
                "platform": platform,
                "content_count": 0,
                "clicks": 0,
                "emails_captured": 0,
                "signups": 0,
                "paid_users": 0,
            },
        )
        current["content_count"] = int(current["content_count"]) + 1
        current["clicks"] = int(current["clicks"]) + int(item.get("clicks", 0))
        current["emails_captured"] = int(current["emails_captured"]) + int(item.get("emails_captured", 0))
        current["signups"] = int(current["signups"]) + int(item.get("signups", 0))
        current["paid_users"] = int(current["paid_users"]) + int(item.get("paid_users", 0))

    decisions: list[OperatorKPIDecision] = []
    for group_key, item in sorted(grouped.items()):
        clicks = int(item["clicks"])
        emails = int(item["emails_captured"])
        count = int(item["content_count"])
        rate = emails / clicks if clicks > 0 else 0.0
        decision, reason = _decision_for_group(count=count, clicks=clicks, emails=emails, rate=rate)
        decisions.append(
            OperatorKPIDecision(
                group_key=group_key,
                platform=str(item["platform"]),
                content_count=count,
                clicks=clicks,
                emails_captured=emails,
                signups=int(item["signups"]),
                paid_users=int(item["paid_users"]),
                click_to_email_rate=round(rate, 4),
                decision=decision,
                reason=reason,
            )
        )
    return decisions


def _platform_from_content_id(content_id: str) -> str:
    suffix = content_id.rsplit("-", 1)[-1].lower()
    return {
        "x": "X",
        "rd": "Reddit",
        "yt": "YouTube Shorts",
        "tt": "TikTok",
        "tg": "Telegram",
    }.get(suffix, "Unknown")


def _decision_for_group(*, count: int, clicks: int, emails: int, rate: float) -> tuple[str, str]:
    if count >= 10 and emails == 0:
        return "暂停 Pause", "已发布或追踪 10 条以上仍无 email lead，先暂停这个组。"
    if clicks >= 25 and rate >= 0.08:
        return "加码 Scale", "click-to-email 达到 8% 以上，下一轮生成 3 个变体。"
    if clicks >= 10 and emails == 0:
        return "改写 Rewrite", "有点击但没有留资，优先检查承诺、CTA 和落地页匹配。"
    return "保留 Keep", "数据不足或表现中性，继续观察。"


async def run_daily_acquisition_operator(
    session_label: str = "daily_acquisition_operator",
    *,
    tickers=DEFAULT_WATCHLIST,
    scanner: ScannerFn = scan_x_opportunities,
    composer: Optional[MultiPlatformComposer] = None,
    feishu_client: Optional[FeishuClient] = None,
    submit_fn: SubmitFn = submit_draft_to_review,
    kpi_fetcher: KPIFetcherFn | None = fetch_all_metrics,
    output_root: Path | None = None,
    content_date: str | None = None,
    campaign_id: str | None = None,
    render_video_packs: bool = False,
) -> dict:
    """Run the acquisition flywheel once and write an operator artifact folder."""

    run_id = _run_id(content_date)
    out_dir = (output_root or _operator_output_root()) / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    errors: list[str] = []
    min_score = _min_opportunity_score()
    top_n = _top_opportunities_count()
    kpi_decisions: list[OperatorKPIDecision] = []
    kpi_items_reviewed = 0

    if kpi_fetcher is not None:
        kpi_end = datetime.now(timezone.utc)
        kpi_start = kpi_end - timedelta(days=_kpi_lookback_days())
        try:
            metrics = await kpi_fetcher(kpi_start, kpi_end)
            kpi_items_reviewed = len(metrics)
            kpi_decisions = build_kpi_decisions(metrics)
        except (KPIDBError, RuntimeError) as exc:
            errors.append(f"kpi: {exc}")

    try:
        opportunities = await scanner(tickers, min_score=min_score)
    except Exception as exc:
        logger.exception("[acquisition_operator] scanner failed")
        errors.append(f"scanner: {exc}")
        result = OperatorRunResult(
            run_id=run_id,
            session=session_label,
            output_dir=str(out_dir),
            opportunities_scanned=0,
            opportunities_selected=0,
            drafts_created=0,
            submitted_to_review=0,
            video_packs_created=0,
            blocked_count=1,
            kpi_items_reviewed=kpi_items_reviewed,
            kpi_decisions=kpi_decisions,
            errors=errors,
            drafts=[],
        )
        _write_json(out_dir / "growth_run_summary.json", asdict(result))
        _write_markdown_outputs(result, out_dir)
        return asdict(result)

    eligible = [o for o in opportunities if o.suggested_action == ACTION_CREATE_CONTENT]
    selected = eligible[:top_n]

    try:
        cmp = composer or MultiPlatformComposer()
    except ContentFactoryError as exc:
        errors.append(str(exc))
        result = OperatorRunResult(
            run_id=run_id,
            session=session_label,
            output_dir=str(out_dir),
            opportunities_scanned=len(opportunities),
            opportunities_selected=len(selected),
            drafts_created=0,
            submitted_to_review=0,
            video_packs_created=0,
            blocked_count=max(1, len(selected) * len(GROWTH_PACK_PLATFORMS)),
            kpi_items_reviewed=kpi_items_reviewed,
            kpi_decisions=kpi_decisions,
            errors=errors,
            drafts=[],
        )
        _write_json(out_dir / "growth_run_summary.json", asdict(result))
        _write_markdown_outputs(result, out_dir)
        return asdict(result)

    draft_results: list[OperatorDraftResult] = []
    submitted = 0
    video_packs = 0

    for opportunity in selected:
        bundle = create_growth_pack_for_opportunity(
            opportunity,
            composer=cmp,
            date=content_date,
            campaign_id=campaign_id,
        )
        for draft in bundle.drafts:
            review_error: str | None = None
            submitted_ok = False
            try:
                await submit_fn(draft, client=feishu_client)
                submitted += 1
                submitted_ok = True
            except (ReviewQueueError, FeishuAPIError) as exc:
                review_error = str(exc)
                errors.append(f"{draft.content_id}: {exc}")

            pack_dir: str | None = None
            if draft.platform in (PLATFORM_SHORTS, PLATFORM_TIKTOK):
                asset_dir = out_dir / "video_packs" / draft.content_id
                spec = _video_spec_from_draft(draft, opportunity)
                write_asset_pack(
                    spec,
                    asset_dir,
                    render_cover=False,
                    render_video=render_video_packs,
                )
                pack_dir = str(asset_dir)
                video_packs += 1

            redline = bundle.redlines[draft.content_id]
            draft_results.append(
                OperatorDraftResult(
                    content_id=draft.content_id,
                    platform=draft.platform,
                    ticker=draft.ticker,
                    risk_level=draft.risk_level,
                    redline_ok=redline.ok,
                    submitted_to_review=submitted_ok,
                    review_error=review_error,
                    video_pack_dir=pack_dir,
                )
            )

    blocked_count = sum(1 for d in draft_results if d.review_error or not d.redline_ok)
    result = OperatorRunResult(
        run_id=run_id,
        session=session_label,
        output_dir=str(out_dir),
        opportunities_scanned=len(opportunities),
        opportunities_selected=len(selected),
        drafts_created=len(draft_results),
        submitted_to_review=submitted,
        video_packs_created=video_packs,
        blocked_count=blocked_count,
        kpi_items_reviewed=kpi_items_reviewed,
        kpi_decisions=kpi_decisions,
        errors=errors,
        drafts=draft_results,
    )
    _write_json(out_dir / "growth_run_summary.json", asdict(result))
    _write_markdown_outputs(result, out_dir)
    return asdict(result)
