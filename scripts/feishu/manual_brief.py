"""Manual brief CLI — generate review drafts from REAL intelligence profiles.

Pre-Task-1 behavior:
  Built synthetic Opportunity shells without consulting the intelligence
  layer — every ticker came out CALM with $0.0 price.

Post-Task-1 behavior:
  Pulls each ticker through intelligence.build_daily_profiles (FMP /stable
  quote + SEC catalysts + X SERP + YouTube) and then
  profile_to_opportunity → real state, real price, real volume, real
  signal heats. The user can always force a ticker through with --score 0
  since manual_brief is operator-initiated (we honour intent over filter).

Usage:
    # Default: real intelligence, all named tickers included
    worker/.venv/Scripts/python.exe scripts/feishu/manual_brief.py \\
        --tickers NVDA AMD TSLA

    # Same plus per-ticker state derivation breakdown to stdout
    worker/.venv/Scripts/python.exe scripts/feishu/manual_brief.py \\
        --tickers NVDA AMD TSLA --debug-state

    # No Feishu writes (preview only)
    worker/.venv/Scripts/python.exe scripts/feishu/manual_brief.py \\
        --tickers NVDA --no-feishu
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKER_DIR = REPO_ROOT / "worker"

# Force UTF-8 stdout — template + debug output uses emojis that Windows
# default code page (gbk / cp936) can't encode.
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except AttributeError:
    pass


def _load_env_local(path: Path) -> None:
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


def _print_debug_state(profile, diagnosis) -> None:
    """Per-ticker explanation of why the state was assigned."""
    mover = profile.evidence.get("mover", {}) or {}
    print(f"\n  [debug-state] {profile.ticker}")
    print(f"    state            = {diagnosis.state.value}")
    print(f"    rule_fired       = {diagnosis.rule_fired}")
    confirming = ", ".join(diagnosis.confirming_signals) or "(none)"
    disagreeing = ", ".join(diagnosis.disagreeing_signals) or "(none)"
    print(f"    confirming({diagnosis.confirming_signal_count}): {confirming}")
    print(f"    disagreeing({diagnosis.disagreeing_signal_count}): {disagreeing}")
    print(f"    filing_catalyst  = {diagnosis.has_filing_catalyst}")
    print(f"    narrative_gap    = {diagnosis.narrative_gap:.3f}")
    print(f"    volume_relative  = {diagnosis.volume_relative}")
    print(f"    price            = ${mover.get('price')}")
    print(f"    change_pct       = {mover.get('change_pct')}%")
    print(f"    sources_used     = {profile.evidence.get('sources_used')}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Manual ticker brief → Intelligence → Content Factory → Feishu"
    )
    parser.add_argument(
        "--tickers", nargs="+", required=True,
        help="Ticker symbols, space-separated",
    )
    parser.add_argument(
        "--score", type=int, default=0,
        help="Floor on profile.overall_opportunity. Default 0 — operator "
             "intent overrides composite score. Set to 70+ only when you "
             "want intelligence to gate-keep your own picks.",
    )
    parser.add_argument(
        "--no-feishu", action="store_true",
        help="Skip Feishu submit, print drafts only",
    )
    parser.add_argument(
        "--debug-state", action="store_true",
        help="Print per-ticker state derivation (rule fired, "
             "confirming/disagreeing signals, volume, price)",
    )
    args = parser.parse_args()

    if not 0 <= args.score <= 100:
        print("[error] --score must be 0-100", file=sys.stderr)
        return 2

    _load_env_local(REPO_ROOT / ".env.local")
    sys.path.insert(0, str(WORKER_DIR))

    from app.marketing.intelligence import (
        build_daily_profiles,
        profile_to_opportunity,
    )
    from app.marketing.jobs import generate_daily_review_drafts
    from app.marketing.opportunities import ACTION_CREATE_CONTENT
    from app.marketing.review_queue import submit_draft_to_review
    from app.marketing.state_resolver import diagnose

    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    tickers = [t.strip().upper() for t in args.tickers if t.strip()]

    # The scanner runs once, fetches real profiles for every requested
    # ticker, prints debug info if asked, then converts to Opportunity
    # with suggested_action forced to CREATE_CONTENT (manual brief is
    # operator-initiated; we don't second-guess the picks).
    async def intelligence_scanner(_unused, *, min_score: int = 0):
        profiles = await build_daily_profiles(
            seed_tickers=tickers, limit=len(tickers)
        )
        print(f"[manual-brief] built {len(profiles)} profile(s) from intelligence layer")
        if not profiles:
            print(
                "[warn] zero profiles returned — FMP or SEC adapter is "
                "down, or .env.local is missing keys.",
                file=sys.stderr,
            )
            return []

        opportunities = []
        for profile in profiles:
            if args.debug_state:
                _print_debug_state(profile, diagnose(profile))
            opp = profile_to_opportunity(profile)
            # Honor operator intent: force CREATE even if composite < 70.
            forced = dataclasses.replace(
                opp, suggested_action=ACTION_CREATE_CONTENT
            )
            if forced.opportunity_score < args.score:
                print(
                    f"[skip] {profile.ticker} score={forced.opportunity_score} "
                    f"< floor {args.score}"
                )
                continue
            opportunities.append(forced)
        return opportunities

    submitted: list = []

    async def fake_submit(draft, *, client=None, notify_chat=True):
        submitted.append(draft)
        print(f"  [dry-run] {draft.content_id} ({draft.platform})")
        return None

    submit_fn = fake_submit if args.no_feishu else submit_draft_to_review

    session = f"manual_brief_{today}"
    mode = "DRY-RUN (composer only)" if args.no_feishu else "LIVE (writing to Feishu)"
    print(f"[manual-brief] session={session} tickers={tickers} mode={mode}")
    print(f"[manual-brief] score_floor={args.score} debug_state={args.debug_state}")

    try:
        result = asyncio.run(
            generate_daily_review_drafts(
                session_label=session,
                scanner=intelligence_scanner,
                submit_fn=submit_fn,
            )
        )
    except Exception as exc:
        print(f"[error] pipeline failed: {exc}", file=sys.stderr)
        return 1

    print()
    print("─" * 60)
    print(f"opportunities       : {result['opportunities']}")
    print(f"drafts_created      : {result['drafts_created']}")
    print(f"submitted_to_review : {result['submitted_to_review']}")
    print(f"skipped             : {result['skipped']}")
    if result["errors"]:
        print("errors:")
        for e in result["errors"]:
            print(f"  - {e}")
    print("─" * 60)
    return 0 if not result["errors"] else 1


if __name__ == "__main__":
    sys.exit(main())
