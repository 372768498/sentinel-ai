"""Run Sentinel AI acquisition operator once.

Default behavior submits generated drafts to Feishu Content Queue. Use
``--local-only`` when you only want to validate the content/video artifact
pipeline without touching Feishu.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKER_DIR = REPO_ROOT / "worker"

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except AttributeError:
    pass


def _load_env_local() -> None:
    path = REPO_ROOT / ".env.local"
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _missing(keys: tuple[str, ...]) -> list[str]:
    return [key for key in keys if not os.environ.get(key, "").strip()]


async def _local_submit(draft, *, client=None, notify_chat=True):
    from app.marketing import bitable_fields as bf

    return {
        "record_id": f"local-{draft.content_id}",
        "review_status": bf.STATUS_PENDING,
    }


class FixtureComposer:
    def compose(self, *, opportunity, platform: str, cta_url: str) -> str:
        return (
            f"${opportunity.ticker} has three signals to verify today.\n"
            "Risk flag: expectation crowding.\n"
            "Risk flag: narrative may be running ahead of fundamentals.\n"
            f"Stock context preview: {cta_url}\n\n"
            "Context, not financial advice."
        )


async def _fixture_scanner(tickers, *, min_score: int = 70):
    from app.marketing.opportunities import ACTION_CREATE_CONTENT, INTENT_TICKER_BUZZ, Opportunity

    ticker = next(iter(tickers), "NVDA")
    return [
        Opportunity(
            opportunity_id=f"OP-FIXTURE-{ticker}",
            source="fixture",
            ticker=ticker,
            intent=INTENT_TICKER_BUZZ,
            raw_text=f"${ticker} attention, valuation, and risk discussion are overlapping today.",
            url="https://example.com/sentinel-fixture",
            author_id="fixture",
            opportunity_score=90,
            compliance_risk=0,
            suggested_action=ACTION_CREATE_CONTENT,
            evidence={
                "why_now": "Attention, valuation, and risk discussion are overlapping today.",
                "risk_flags": [
                    "Expectation crowding",
                    "Narrative may be one-sided",
                    "Source freshness needs review",
                ],
            },
            state="heated",
        )
    ]


async def _fixture_kpi_fetcher(start, end):
    return {
        "CT-local-auto-check-NVDA-x": {
            "clicks": 100,
            "emails_captured": 9,
            "signups": 4,
            "paid_users": 1,
        }
    }


def _print_summary(result: dict) -> None:
    print("Sentinel AI 自动化获客 Operator 已完成")
    print(f"- run_id: {result['run_id']}")
    print(f"- output_dir: {result['output_dir']}")
    print(f"- opportunities_scanned: {result['opportunities_scanned']}")
    print(f"- opportunities_selected: {result['opportunities_selected']}")
    print(f"- drafts_created: {result['drafts_created']}")
    print(f"- submitted_to_review: {result['submitted_to_review']}")
    print(f"- video_packs_created: {result['video_packs_created']}")
    print(f"- kpi_items_reviewed: {result['kpi_items_reviewed']}")
    print(f"- blocked_count: {result['blocked_count']}")
    if result["errors"]:
        print("- errors:")
        for item in result["errors"]:
            print(f"  - {item}")


async def _run(args: argparse.Namespace) -> int:
    sys.path.insert(0, str(WORKER_DIR))

    from app.marketing.acquisition_operator import run_daily_acquisition_operator

    if args.local_only or args.fixture:
        submit_fn = _local_submit
    else:
        missing = _missing(
            (
                "ANTHROPIC_API_KEY",
                "FEISHU_APP_ID",
                "FEISHU_APP_SECRET",
                "FEISHU_BITABLE_APP_TOKEN",
                "FEISHU_CONTENT_QUEUE_TABLE_ID",
                "GROWTH_OS_PUBLIC_URL",
            )
        )
        if missing:
            print("阻塞：真实提交到飞书前需要补齐这些环境变量：", file=sys.stderr)
            for key in missing:
                print(f"- {key}", file=sys.stderr)
            print("如果只是本地验证产物，请加 --local-only。", file=sys.stderr)
            return 2
        submit_fn = None

    kwargs = {
        "session_label": args.session_label,
        "content_date": args.content_date,
        "campaign_id": args.campaign_id,
        "render_video_packs": args.render_video_packs,
    }
    if args.fixture:
        kwargs["scanner"] = _fixture_scanner
        kwargs["composer"] = FixtureComposer()
        kwargs["submit_fn"] = _local_submit
        if not args.no_kpi:
            kwargs["kpi_fetcher"] = _fixture_kpi_fetcher
    if args.output_dir:
        kwargs["output_root"] = Path(args.output_dir)
    if args.no_kpi:
        kwargs["kpi_fetcher"] = None
    if submit_fn is not None:
        kwargs["submit_fn"] = submit_fn

    result = await run_daily_acquisition_operator(**kwargs)
    _print_summary(result)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not result["errors"] else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Sentinel AI automated acquisition once")
    parser.add_argument("--local-only", action="store_true", help="不写入飞书，只生成本地产物")
    parser.add_argument("--fixture", action="store_true", help="使用固定样本跑确定性 smoke，不访问外部信号源/LLM/飞书")
    parser.add_argument("--no-kpi", action="store_true", help="跳过 KPI 回看")
    parser.add_argument("--render-video-packs", action="store_true", help="渲染短视频素材包里的视频文件")
    parser.add_argument("--content-date", help="覆盖内容日期/批次 ID，例如 202605170930")
    parser.add_argument("--campaign-id", help="覆盖 campaign_id")
    parser.add_argument("--session-label", default="manual_acquisition_operator")
    parser.add_argument("--output-dir", help="产物输出根目录，默认 docs/growth-runs")
    parser.add_argument("--json", action="store_true", help="额外打印完整 JSON")
    args = parser.parse_args()

    _load_env_local()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
