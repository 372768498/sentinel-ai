from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from app import main


def test_email_daily_test_send_requires_internal_token(monkeypatch) -> None:
    monkeypatch.setattr(
        main,
        "settings",
        SimpleNamespace(worker_internal_token="secret"),
    )

    client = TestClient(main.app)
    response = client.post(
        "/api/marketing/email-daily/test-send?only_email=a@example.com"
    )

    assert response.status_code == 401


def test_email_daily_test_send_masks_email_and_disables_bulk(monkeypatch) -> None:
    monkeypatch.setattr(
        main,
        "settings",
        SimpleNamespace(worker_internal_token="secret"),
    )
    calls: list[dict] = []

    async def fake_send_email_digest(**kwargs):
        calls.append(kwargs)
        return {
            "session": "email_daily",
            "mode": "LIVE",
            "leads_queried": 1,
            "leads_eligible": 1,
            "sent": 1,
            "skipped_unverified": 0,
            "errors": [],
            "renders": [
                {
                    "email": "372768498@qq.com",
                    "subject": "Today: nothing unusual",
                    "branch": "nothing",
                }
            ],
        }

    import app.marketing.email_jobs as email_jobs

    monkeypatch.setattr(email_jobs, "send_email_digest", fake_send_email_digest)

    client = TestClient(main.app)
    response = client.post(
        "/api/marketing/email-daily/test-send"
        "?only_email=372768498@qq.com&dry_run=false",
        headers={"X-Internal-Token": "secret"},
    )

    assert response.status_code == 200
    assert calls == [
        {
            "only_email": "372768498@qq.com",
            "live": True,
            "allow_bulk": False,
            "limit": 1,
        }
    ]
    body = response.json()
    assert body["sent"] == 1
    assert body["renders"][0]["email"] == "37***@qq.com"
