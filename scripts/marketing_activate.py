"""One-shot activation: collect creds, validate Claude + X cookie, optionally
send 1 live test tweet.

Usage (from repo root, with worker venv activated):
    python scripts/marketing_activate.py

Walks through:
  1. Verify ANTHROPIC_API_KEY exists (or prompt).
  2. Verify X cookie at worker/data/x-cookies.json (or prompt to log in).
  3. Run 1 Claude composer call (cheap) to confirm API works.
  4. Ask whether to send 1 live tweet for a chosen ticker (default TSLA).
  5. Print a summary + the tweet URL if posted.

Idempotent and safe: every step is opt-in. Cancel any time.
"""
from __future__ import annotations

import asyncio
import getpass
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKER_DIR = REPO_ROOT / "worker"
ENV_PATH = REPO_ROOT / ".env.local"  # canonical Sentinel env file

sys.path.insert(0, str(WORKER_DIR))


def _print(line: str = ""):
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


def _ask_yn(question: str, default: bool = False) -> bool:
    suffix = " [Y/n] " if default else " [y/N] "
    raw = input(question + suffix).strip().lower()
    if not raw:
        return default
    return raw[0] == "y"


def _read_env_file() -> dict[str, str]:
    if not ENV_PATH.exists():
        return {}
    out: dict[str, str] = {}
    for raw in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip()
    return out


def _append_env(updates: dict[str, str]) -> None:
    ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
    existing = _read_env_file()
    for key, value in updates.items():
        existing[key] = value
    body = "\n".join(f"{k}={v}" for k, v in sorted(existing.items())) + "\n"
    ENV_PATH.write_text(body, encoding="utf-8")
    _print(f"  -> wrote {len(updates)} key(s) to {ENV_PATH}")


def _step_anthropic_key() -> bool:
    _print("\n[1/4] Anthropic API key")
    if os.environ.get("ANTHROPIC_API_KEY"):
        _print(f"  OK  ANTHROPIC_API_KEY already set in environment")
        return True
    env = _read_env_file()
    if env.get("ANTHROPIC_API_KEY"):
        os.environ["ANTHROPIC_API_KEY"] = env["ANTHROPIC_API_KEY"]
        _print("  OK  loaded ANTHROPIC_API_KEY from worker/.env")
        return True

    if not _ask_yn("  Paste an ANTHROPIC_API_KEY now?", default=True):
        _print("  SKIP (composer will run in Mock Mode)")
        return False

    key = getpass.getpass("  ANTHROPIC_API_KEY: ").strip()
    if not key.startswith("sk-ant-"):
        _print("  WARN: key does not look like an Anthropic key (continuing anyway)")
    os.environ["ANTHROPIC_API_KEY"] = key
    _append_env({"ANTHROPIC_API_KEY": key})
    return True


REQUIRED_OAUTH_KEYS = (
    "X_API_KEY",
    "X_API_SECRET",
    "X_ACCESS_TOKEN",
    "X_ACCESS_TOKEN_SECRET",
)


def _step_x_oauth() -> bool:
    _print("\n[2/4] X OAuth 1.0a keys (for posting)")

    env = _read_env_file()
    have = {k: bool(env.get(k) or os.environ.get(k)) for k in REQUIRED_OAUTH_KEYS}
    missing = [k for k, v in have.items() if not v]

    if not missing:
        for k in REQUIRED_OAUTH_KEYS:
            os.environ[k] = env.get(k) or os.environ.get(k, "")
        _print("  OK  all 4 OAuth keys present in env / .env")
        return True

    _print(f"  missing: {', '.join(missing)}")
    _print("  Get them at developer.x.com/en/portal/dashboard")
    _print("  -> select your App -> Keys and tokens -> regenerate / copy")
    _print("  -> ensure App permissions = Read and write")
    if not _ask_yn("  Paste keys now?", default=True):
        _print("  SKIP (live posting disabled until keys are present)")
        return False

    pasted: dict[str, str] = {}
    for k in missing:
        value = getpass.getpass(f"  {k}: ").strip()
        if not value:
            _print(f"  ERR  {k} blank, abort")
            return False
        pasted[k] = value
        os.environ[k] = value
    _append_env(pasted)
    _print("  OK  4 keys captured")
    return True


async def _step_claude_smoke() -> bool:
    _print("\n[3/4] Claude composer smoke")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        _print("  SKIP (no ANTHROPIC_API_KEY)")
        return False
    from app.marketing import Composer
    from app.marketing.personas import SEC_FILING_REPORTER

    composer = Composer(dry_run=False)
    try:
        result = composer.compose_post(
            persona=SEC_FILING_REPORTER,
            ticker="TEST",
            change_pct=1.0,
            score=70,
            headline="filed an 8-K disclosing $X buyback",
            source_url="https://www.sec.gov/test",
            deep_link="https://t.me/test",
        )
    except Exception as exc:
        _print(f"  ERR  Claude call failed: {exc}")
        return False
    if not result.redline.ok:
        _print(f"  ERR  redline failed: {result.redline.violations}")
        return False
    _print(f"  OK  Claude returned {len(result.text)}-char redline-clean draft")
    _print(f"      {result.text.splitlines()[0]}")
    return True


async def _step_live_test_tweet(ticker: str) -> bool:
    _print(f"\n[4/4] Live test tweet — ticker={ticker}")
    if not all(os.environ.get(k) for k in REQUIRED_OAUTH_KEYS):
        _print("  SKIP (OAuth keys missing)")
        return False
    if not _ask_yn(f"  Really send 1 LIVE tweet for ${ticker}?", default=False):
        _print("  SKIP")
        return False

    from app.marketing import Composer, Publisher, XClient
    from app.scanner import fetch_watchlist_moves
    from app.marketing.signals import score_from_move
    from app.marketing.catalysts import fallback_source, latest_catalyst

    moves = await fetch_watchlist_moves((ticker,))
    if not moves:
        _print(f"  ERR  no movement data for {ticker}")
        return False
    move = moves[0]
    score = score_from_move(move)
    catalyst = await latest_catalyst(ticker)

    sign = "+" if move.change_pct > 0 else ""
    if catalyst:
        headline = f"{catalyst.headline()}; intraday move {sign}{move.change_pct:.2f}%"
        source_url = catalyst.homepage_url
    else:
        headline = f"intraday move of {sign}{move.change_pct:.2f}% on watchlist"
        source_url = fallback_source(ticker)

    x_client = XClient(dry_run=False)  # reads OAuth keys from env
    await x_client.login()  # validates keys present

    pub = Publisher(
        composer=Composer(),
        x_client=x_client,
        bot_username=os.environ.get("BOT_USERNAME", "SentinelAIProChannelBot"),
    )
    outcome = await pub.publish_alert(
        ticker=move.ticker, change_pct=move.change_pct, score=score,
        headline=headline, source_url=source_url,
    )

    _print("  TEXT:")
    for line in outcome.text.splitlines():
        _print(f"    {line}")
    _print(f"  redline: {'OK' if outcome.redline_ok else outcome.redline_violations}")
    _print(f"  posted:  {outcome.post_result.posted}")
    if outcome.post_result.posted:
        _print(f"  tweet:   https://twitter.com/i/web/status/{outcome.post_result.tweet_id}")
    if outcome.post_result.error:
        _print(f"  ERROR:   {outcome.post_result.error}")
        return False
    return outcome.post_result.posted


async def main() -> int:
    _print("=" * 70)
    _print("  SENTINEL MARKETING ACTIVATION")
    _print("=" * 70)

    have_anthropic = _step_anthropic_key()
    have_oauth = _step_x_oauth()

    if have_anthropic:
        await _step_claude_smoke()

    if have_oauth:
        ticker = input("\n  Test ticker for live tweet (default TSLA, blank to skip): ").strip() or "TSLA"
        if ticker.lower() != "skip":
            await _step_live_test_tweet(ticker.upper())

    _print("\n" + "=" * 70)
    _print("  Activation complete.")
    _print("  To enable cron-driven dispatch in production:")
    _print("    MARKETING_ENABLED=true")
    _print("    X_DRY_RUN=false")
    _print("    MARKETING_SCORE_THRESHOLD=80")
    _print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
