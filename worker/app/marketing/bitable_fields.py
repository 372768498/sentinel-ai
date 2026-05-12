"""Central registry for Feishu Bitable Content Queue field names.

Operator-jojo asked for Chinese column headers in Feishu UI. To make
renames safe, every worker site that reads/writes Bitable fields routes
through the constants here and the `normalize_fields()` helper.

Migration strategy:
  1. Refactor all read/write call sites to use these constants.
  2. Deploy worker — read sites call `normalize_fields(record_fields)`
     which maps any English legacy key to its Chinese counterpart, so
     the worker accepts BOTH naming conventions transparently.
  3. Run `scripts/feishu/rename_content_queue_to_chinese.py` to rename
     the Bitable columns in place. The field_id stays the same so
     existing data is preserved.
  4. After rename, Bitable answers with Chinese names. The worker's
     write side (constants below) is also Chinese, so writes work.
     Reads still tolerate English in case any stray legacy record
     surfaces.

NOT touched by this layer:
  - Single-select OPTION VALUES (e.g. 'Approved', 'Telegram', 'Pass').
    Worker logic uses these as enum keys (`if review_status == "Approved"`)
    so changing them would force a deep refactor. Operators see Chinese
    column headers + English cell values — acceptable.
"""
from __future__ import annotations

# ---- Field-name constants (Chinese display names) ------------------------

CONTENT_ID = "内容ID"
CAMPAIGN_ID = "活动ID"
PLATFORM = "平台"
TICKER = "股票代码"
HOOK = "钩子"
BODY = "正文"
CTA_URL = "跳转链接"
RISK_LEVEL = "风险等级"
REDLINE_RESULT = "合规检查"
REDLINE_HITS = "违规项"
REVIEW_STATUS = "审核状态"
REVIEWER_COMMENT = "审核备注"
PUBLISH_TIME = "发布时间"
PUBLISHED_URL = "已发布链接"
QUALITY_SCORE = "质量评分"
KILL_REASON = "拒绝原因"
ONE_WORD = "一句感受"


# ---- Legacy English → new Chinese map (used during migration only) ------

LEGACY_TO_NEW: dict[str, str] = {
    "content_id": CONTENT_ID,
    "campaign_id": CAMPAIGN_ID,
    "platform": PLATFORM,
    "ticker": TICKER,
    "hook": HOOK,
    "body": BODY,
    "cta_url": CTA_URL,
    "risk_level": RISK_LEVEL,
    "redline_result": REDLINE_RESULT,
    "redline_hits": REDLINE_HITS,
    "review_status": REVIEW_STATUS,
    "reviewer_comment": REVIEWER_COMMENT,
    "publish_time": PUBLISH_TIME,
    "published_url": PUBLISHED_URL,
    "jojo_quality_score": QUALITY_SCORE,
    "jojo_kill_reason": KILL_REASON,
    "jojo_one_word": ONE_WORD,
}


def normalize_fields(fields: dict) -> dict:
    """Return a copy of `fields` where each key is mirrored under both
    its English (legacy) and Chinese (new) form. Lets reading code
    look up by either name regardless of whether the Bitable rename
    has happened yet.

    Idempotent. Bidirectional: an English-only record gains Chinese
    mirrors; a Chinese-only record gains English mirrors.
    """
    if not fields:
        return {}
    out = dict(fields)
    for english, chinese in LEGACY_TO_NEW.items():
        if english in out and chinese not in out:
            out[chinese] = out[english]
        elif chinese in out and english not in out:
            out[english] = out[chinese]
    return out


# ---- Convenience: alphabetically ordered tuple for scripts --------------

ALL_LEGACY_NAMES: tuple[str, ...] = tuple(sorted(LEGACY_TO_NEW.keys()))
ALL_CHINESE_NAMES: tuple[str, ...] = tuple(sorted(LEGACY_TO_NEW.values()))
