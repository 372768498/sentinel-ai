from __future__ import annotations

from app.marketing import bitable_fields as bf


def test_normalize_fields_supports_all_growth_os_tables() -> None:
    fields = {
        "campaign_id": "CMP-1",
        "content_id": "CT-1",
        "clicks": 12,
        "emails_captured": 3,
        "review_status": "Pending",
    }

    normalized = bf.normalize_fields(fields)

    assert normalized[bf.CAMPAIGN_ID] == "CMP-1"
    assert normalized[bf.CONTENT_ID] == "CT-1"
    assert normalized[bf.PERF_CLICKS] == 12
    assert normalized[bf.PERF_EMAILS_CAPTURED] == 3
    assert normalized[bf.REVIEW_STATUS] == "Pending"
    assert normalized["clicks"] == 12


def test_table_names_are_chinese_first() -> None:
    assert bf.TABLE_NAME_MAP == {
        "Campaigns": "活动",
        "Content Queue": "内容队列",
        "Performance": "表现数据",
    }
