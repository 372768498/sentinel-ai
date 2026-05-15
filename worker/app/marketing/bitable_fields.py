"""Feishu Bitable field registry for Sentinel AI Growth OS.

Feishu UI should be Chinese-first. Worker code stays bilingual during and
after migration: every reader calls ``normalize_fields()`` so legacy English
records and renamed Chinese records both work.
"""

from __future__ import annotations

# ---- Table display names -------------------------------------------------

TABLE_CAMPAIGNS = "活动"
TABLE_CONTENT_QUEUE = "内容队列"
TABLE_PERFORMANCE = "表现数据"

TABLE_NAME_MAP: dict[str, str] = {
    "Campaigns": TABLE_CAMPAIGNS,
    "Content Queue": TABLE_CONTENT_QUEUE,
    "Performance": TABLE_PERFORMANCE,
}


# ---- Campaigns / 活动 ----------------------------------------------------

CAMPAIGN_ID = "活动ID"
CAMPAIGN_DATE = "日期"
CAMPAIGN_SESSION = "场次"
CAMPAIGN_MAIN_TICKER = "主股票代码"
CAMPAIGN_STATUS = "状态"
CAMPAIGN_OWNER = "负责人"
CAMPAIGN_NOTES = "备注"

CAMPAIGNS_LEGACY_TO_NEW: dict[str, str] = {
    "campaign_id": CAMPAIGN_ID,
    "date": CAMPAIGN_DATE,
    "session": CAMPAIGN_SESSION,
    "main_ticker": CAMPAIGN_MAIN_TICKER,
    "status": CAMPAIGN_STATUS,
    "owner": CAMPAIGN_OWNER,
    "notes": CAMPAIGN_NOTES,
}


# ---- Content Queue / 内容队列 -------------------------------------------

CONTENT_ID = "内容ID"
PLATFORM = "平台"
TICKER = "股票代码"
HOOK = "钩子"
HOOK_ZH = "钩子中文"
BODY = "正文"
BODY_ZH = "正文中文"
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

CONTENT_QUEUE_LEGACY_TO_NEW: dict[str, str] = {
    "content_id": CONTENT_ID,
    "campaign_id": CAMPAIGN_ID,
    "platform": PLATFORM,
    "ticker": TICKER,
    "hook": HOOK,
    "hook_zh": HOOK_ZH,
    "body": BODY,
    "body_zh": BODY_ZH,
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


# ---- Performance / 表现数据 ---------------------------------------------

PERF_CONTENT_ID = CONTENT_ID
PERF_VIEWS = "曝光数"
PERF_CLICKS = "点击数"
PERF_EMAILS_CAPTURED = "邮件留资数"
PERF_SIGNUPS = "注册数"
PERF_PAID_USERS = "付费用户数"
PERF_CLICK_TO_EMAIL_RATE = "点击到留资率"
PERF_FREE_TO_PAID_RATE = "免费到付费率"
PERF_CAC_ESTIMATE = "预估获客成本"
PERF_NOTES = "备注"

PERFORMANCE_LEGACY_TO_NEW: dict[str, str] = {
    "content_id": PERF_CONTENT_ID,
    "views": PERF_VIEWS,
    "clicks": PERF_CLICKS,
    "emails_captured": PERF_EMAILS_CAPTURED,
    "signups": PERF_SIGNUPS,
    "paid_users": PERF_PAID_USERS,
    "click_to_email_rate": PERF_CLICK_TO_EMAIL_RATE,
    "free_to_paid_rate": PERF_FREE_TO_PAID_RATE,
    "cac_estimate": PERF_CAC_ESTIMATE,
    "notes": PERF_NOTES,
}


# Backward-compatible name used by existing Content Queue code/tests.
LEGACY_TO_NEW = CONTENT_QUEUE_LEGACY_TO_NEW

ALL_LEGACY_TO_NEW: dict[str, str] = {
    **CAMPAIGNS_LEGACY_TO_NEW,
    **CONTENT_QUEUE_LEGACY_TO_NEW,
    **PERFORMANCE_LEGACY_TO_NEW,
}


def normalize_fields(fields: dict) -> dict:
    """Mirror fields under both English legacy keys and Chinese display names."""
    if not fields:
        return {}
    out = dict(fields)
    for english, chinese in ALL_LEGACY_TO_NEW.items():
        if english in out and chinese not in out:
            out[chinese] = out[english]
        elif chinese in out and english not in out:
            out[english] = out[chinese]
    return out


ALL_LEGACY_NAMES: tuple[str, ...] = tuple(sorted(ALL_LEGACY_TO_NEW.keys()))
ALL_CHINESE_NAMES: tuple[str, ...] = tuple(sorted(set(ALL_LEGACY_TO_NEW.values())))
