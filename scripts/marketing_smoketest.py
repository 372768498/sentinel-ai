"""End-to-end smoke test for the marketing pipeline.

Real watchlist + real yfinance data -> Composer (Mock or Claude) -> redline ->
XClient (dry-run by default).

Usage (from repo root):
    python scripts/marketing_smoketest.py              # default dry-run, all tickers
    python scripts/marketing_smoketest.py --threshold 50  # lower bar to see something
    python scripts/marketing_smoketest.py --tickers AAPL,NVDA  # subset
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKER_DIR = REPO_ROOT / "worker"
sys.path.insert(0, str(WORKER_DIR))

from app.marketing import (  # noqa: E402
    Composer,
    Publisher,
    XClient,
    score_from_move,
)
from app.marketing.catalysts import fallback_source, latest_catalyst  # noqa: E402
from app.marketing.tracker import build_deep_link, build_payload  # noqa: E402
from app.scanner import fetch_watchlist_moves  # noqa: E402
from app.watchlist import DEFAULT_WATCHLIST  # noqa: E402

DIVIDER = "-" * 78


def _fmt_score(score: int) -> str:
    if score >= 90:
        return f"{score:>3}!"
    if score >= 80:
        return f"{score:>3}*"
    return f"{score:>3} "


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--threshold", type=int, default=50,
                        help="score gate (default 50 to make smoke meaningful)")
    parser.add_argument("--tickers", default=",".join(DEFAULT_WATCHLIST),
                        help="comma-separated tickers")
    parser.add_argument("--bot-username", default=os.environ.get(
        "BOT_USERNAME", "SentinelAIProChannelBot"))
    args = parser.parse_args()

    tickers = tuple(t.strip().upper() for t in args.tickers.split(",") if t.strip())

    print(f"\n{DIVIDER}")
    print(f"  SENTINEL MARKETING PIPELINE · SMOKE TEST")
    print(f"{DIVIDER}")
    print(f"  Watchlist:        {', '.join(tickers)}")
    print(f"  Score threshold:  {args.threshold}")
    print(f"  Bot username:     {args.bot_username}")
    print(f"  ANTHROPIC_API_KEY:{'set (Claude live)' if os.environ.get('ANTHROPIC_API_KEY') else 'not set (Mock Mode)'}")
    print(f"  X_DRY_RUN:        {os.environ.get('X_DRY_RUN', 'true')} (default true)")
    print(f"{DIVIDER}\n")

    print("[1/4] Fetching real prices via yfinance ...")
    moves = await fetch_watchlist_moves(tickers)
    print(f"      got {len(moves)} moves")
    for m in sorted(moves, key=lambda x: abs(x.change_pct), reverse=True):
        s = score_from_move(m)
        print(f"      {m.ticker:6} {m.signed_pct:>8}  score={_fmt_score(s)}  "
              f"${m.prev_close:.2f} -> ${m.last_price:.2f}")

    qualified = [(m, score_from_move(m)) for m in moves
                 if score_from_move(m) >= args.threshold]
    print(f"\n[2/4] Gate (score >= {args.threshold}): {len(qualified)} qualified\n")

    if not qualified:
        print("      No tickers cleared the gate. Lower --threshold to see composition.\n")
        return 0

    pub = Publisher(
        composer=Composer(),  # auto-Mock if ANTHROPIC_API_KEY missing
        x_client=XClient(),  # auto-dry-run unless X_DRY_RUN=false
        bot_username=args.bot_username,
    )

    print("[3/4] Looking up SEC catalysts (parallel) ...")
    catalyst_results = await asyncio.gather(
        *[latest_catalyst(move.ticker) for move, _ in qualified]
    )
    for (move, _), cat in zip(qualified, catalyst_results):
        if cat:
            print(f"      {move.ticker:6} {cat.form:5} {cat.filing_date}  {cat.homepage_url[:70]}")
        else:
            print(f"      {move.ticker:6} (no recent filing in window, falling back)")
    print()

    print("[4/4] Composing + redline-scanning each qualified signal ...\n")
    outcomes = []
    for (move, score), catalyst in zip(qualified, catalyst_results):
        sign = "+" if move.change_pct > 0 else ""
        if catalyst:
            headline = f"{catalyst.headline()}; intraday move {sign}{move.change_pct:.2f}%"
            source_url = catalyst.homepage_url
        else:
            headline = f"intraday move of {sign}{move.change_pct:.2f}% on watchlist"
            source_url = fallback_source(move.ticker)
        outcome = await pub.publish_alert(
            ticker=move.ticker,
            change_pct=move.change_pct,
            score=score,
            headline=headline,
            source_url=source_url,
        )
        outcomes.append(outcome)

    print(f"[5/5] Outcomes:\n")
    for o in outcomes:
        status = "[OK]" if o.redline_ok else f"[FAIL] {o.redline_violations}"
        post_status = "DRY-RUN" if o.post_result.dry_run else (
            f"POSTED {o.post_result.tweet_id}" if o.post_result.posted
            else f"ERROR {o.post_result.error}")
        print(f"  +-- {o.ticker} | persona: {o.persona}")
        print(f"  |   redline:   {status}")
        print(f"  |   post:      {post_status}")
        print(f"  |   deep-link: {o.deep_link}")
        print(f"  |   tweet text ({len(o.text)} chars):")
        for line in o.text.split("\n"):
            print(f"  |     {line}")
        print(f"  +--\n")

    # Verify deep-link parses back correctly via the bot's actual regex
    try:
        from app.bot.handlers.onboarding import START_PAYLOAD_RE
        print("[6/6] Verifying deep-link payloads parse via bot's START_PAYLOAD_RE ...\n")
        for o in outcomes:
            payload = o.deep_link.split("start=", 1)[1]
            m = START_PAYLOAD_RE.match(payload)
            if not m:
                print(f"  [FAIL] {o.ticker}: payload {payload!r} does NOT match bot regex")
                continue
            gd = m.groupdict()
            print(f"  [OK]   {o.ticker}: source={gd.get('source')} "
                  f"campaign={gd.get('campaign')} ticker={gd.get('ticker')}")
        print()
    except ImportError as exc:
        print(f"  (bot regex check skipped: {exc})\n")

    print(f"{DIVIDER}")
    print(f"  Smoke test complete. Composer={'Claude' if os.environ.get('ANTHROPIC_API_KEY') else 'Mock'}, "
          f"XClient=DRY-RUN.")
    print(f"{DIVIDER}\n")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
