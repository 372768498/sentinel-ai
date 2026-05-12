"""Task 4.3 · Weekly quality report — what operator-jojo scored last N days.

Reads Feishu Content Queue, slices by jojo_quality_score / jojo_kill_reason
/ jojo_one_word, prints to stdout. Manual-run only — no cron yet.

Usage:
    worker/.venv/Scripts/python.exe scripts/analytics/quality_report.py --days 7

Sections in the report (in order):
  1. Volume:        total / Approved / Rejected / Pending counts
  2. Quality:       avg quality_score on Approved
  3. Kill reasons:  distribution from Rejected rows
  4. By platform:   counts + avg score per Telegram / X / YouTube Shorts
  5. By template:   counts + avg score split between new-template
                    (free_tg_anomaly body starts with 🛰) and old-LLM
  6. Lowest scored: the 5 lowest-scoring Approved drafts + their one_word
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
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
        k, _, v = line.partition("=")
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def _text(value: object) -> str:
    """Bitable text fields sometimes come back as [{'type':'text','text':'x'}].
    Reduce to a plain string."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, dict):
                t = item.get("text") or item.get("link") or ""
                if t:
                    parts.append(str(t))
            else:
                parts.append(str(item))
        return "".join(parts).strip()
    if isinstance(value, dict):
        return str(value.get("text") or value.get("link") or "").strip()
    return str(value).strip()


def _score(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value) if value > 0 else None
    if isinstance(value, str):
        try:
            v = float(value.strip())
            return v if v > 0 else None
        except ValueError:
            return None
    return None


def _template_label(body: str) -> str:
    """Infer which template produced the body. New free_telegram template
    starts with the 🛰 satellite + "Sentinel · Anomaly Watch" header."""
    if body.startswith("🛰") or "Sentinel · Anomaly Watch" in body:
        return "new_template"
    return "llm_legacy"


def _fetch_all(client, app_token: str, table_id: str) -> list[dict]:
    out: list[dict] = []
    page_token = None
    while True:
        page = client.bitable_list_records(
            app_token, table_id, page_size=100, page_token=page_token
        )
        items = page.get("items", [])
        out.extend(items)
        if not page.get("has_more"):
            break
        page_token = page.get("page_token")
        if not page_token:
            break
    return out


def _within_window(record: dict, since: datetime) -> bool:
    """Bitable record carries created_time (epoch milliseconds) at the
    top level. Fall back to fields.publish_time if missing."""
    ms = record.get("created_time")
    if isinstance(ms, (int, float)) and ms > 0:
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc) >= since
    return True  # if no timestamp available, include rather than drop


def _avg(nums: list[float]) -> float | None:
    return sum(nums) / len(nums) if nums else None


def _fmt_avg(avg: float | None, n: int) -> str:
    return f"avg={avg:.2f} (n={n})" if avg is not None else f"avg=—  (n={n})"


def main() -> int:
    parser = argparse.ArgumentParser(description="Quality report over last N days")
    parser.add_argument("--days", type=int, default=7, help="Lookback window in days (default 7)")
    args = parser.parse_args()
    if args.days <= 0:
        print("[error] --days must be > 0", file=sys.stderr)
        return 2

    _load_env_local()
    sys.path.insert(0, str(WORKER_DIR))

    app_token = os.environ.get("FEISHU_BITABLE_APP_TOKEN")
    table_id = os.environ.get("FEISHU_CONTENT_QUEUE_TABLE_ID")
    if not app_token or not table_id:
        print("[error] FEISHU_BITABLE_APP_TOKEN + FEISHU_CONTENT_QUEUE_TABLE_ID required", file=sys.stderr)
        return 2

    from app.marketing.feishu_client import FeishuClient

    client = FeishuClient()
    records = _fetch_all(client, app_token, table_id)

    since = datetime.now(timezone.utc) - timedelta(days=args.days)
    in_window = [r for r in records if _within_window(r, since)]

    rows = []
    for r in in_window:
        f = r.get("fields", {}) or {}
        rows.append(
            {
                "content_id": _text(f.get("content_id")),
                "platform": _text(f.get("platform")),
                "review_status": _text(f.get("review_status")),
                "quality_score": _score(f.get("jojo_quality_score")),
                "kill_reason": _text(f.get("jojo_kill_reason")),
                "one_word": _text(f.get("jojo_one_word")),
                "body": _text(f.get("body")),
            }
        )

    total = len(rows)
    approved = [r for r in rows if r["review_status"] == "Approved"]
    rejected = [r for r in rows if r["review_status"] == "Rejected"]
    pending = [r for r in rows if r["review_status"] not in ("Approved", "Rejected", "Published", "Failed")]
    published = [r for r in rows if r["review_status"] == "Published"]

    print()
    print(f"╔══════════════════════════════════════════════════════════════╗")
    print(f"║  Sentinel · Quality Report                                   ║")
    print(f"║  Window: last {args.days:>2d} day(s)                                       ║")
    print(f"╚══════════════════════════════════════════════════════════════╝")

    # 1. Volume
    print(f"\n▎1. Volume in window")
    print(f"   total      = {total}")
    print(f"   approved   = {len(approved)}")
    print(f"   published  = {len(published)}")
    print(f"   rejected   = {len(rejected)}")
    print(f"   pending    = {len(pending)}")

    # 2. Quality (approved + published count as "got past the gate")
    scored = [r for r in rows if r["quality_score"] is not None]
    scores = [r["quality_score"] for r in scored]
    print(f"\n▎2. Quality scores ({len(scored)} scored rows)")
    print(f"   {_fmt_avg(_avg(scores), len(scores))}")
    bands = Counter()
    for s in scores:
        if s >= 4.5: bands["5 (great)"] += 1
        elif s >= 3.5: bands["4 (good)"] += 1
        elif s >= 2.5: bands["3 (ok)"] += 1
        elif s >= 1.5: bands["2 (weak)"] += 1
        else: bands["1 (kill)"] += 1
    for label in ("5 (great)", "4 (good)", "3 (ok)", "2 (weak)", "1 (kill)"):
        c = bands.get(label, 0)
        bar = "█" * c
        print(f"   {label:<11s} {c:>3d}  {bar}")

    # 3. Kill reasons
    print(f"\n▎3. Kill reasons (Rejected rows)")
    reasons = Counter(r["kill_reason"] for r in rejected if r["kill_reason"])
    if not reasons:
        print(f"   (no rejected rows in window)")
    for reason, c in reasons.most_common():
        print(f"   {reason:<18s} {c}")

    # 4. By platform
    print(f"\n▎4. By platform")
    by_platform: dict[str, list[float]] = defaultdict(list)
    counts_by_platform: Counter = Counter()
    for r in rows:
        platform = r["platform"] or "unknown"
        counts_by_platform[platform] += 1
        if r["quality_score"] is not None:
            by_platform[platform].append(r["quality_score"])
    for platform, c in counts_by_platform.most_common():
        scores_p = by_platform.get(platform, [])
        print(f"   {platform:<20s} count={c:>3d}  {_fmt_avg(_avg(scores_p), len(scores_p))}")

    # 5. By template (inferred from body)
    print(f"\n▎5. By template (inferred)")
    by_tpl: dict[str, list[float]] = defaultdict(list)
    counts_by_tpl: Counter = Counter()
    for r in rows:
        tpl = _template_label(r["body"])
        counts_by_tpl[tpl] += 1
        if r["quality_score"] is not None:
            by_tpl[tpl].append(r["quality_score"])
    for tpl, c in counts_by_tpl.most_common():
        scores_t = by_tpl.get(tpl, [])
        print(f"   {tpl:<16s} count={c:>3d}  {_fmt_avg(_avg(scores_t), len(scores_t))}")

    # 6. Lowest-scored 5
    print(f"\n▎6. Lowest-scored 5 drafts")
    lowest = sorted(
        (r for r in scored if r["quality_score"] is not None),
        key=lambda r: (r["quality_score"], r["content_id"]),
    )[:5]
    if not lowest:
        print(f"   (no scored rows)")
    for r in lowest:
        oneword = r["one_word"] or "—"
        print(f"   {r['quality_score']:.0f}  {r['content_id']:<28s} one_word: {oneword}")

    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
