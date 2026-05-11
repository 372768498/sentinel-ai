"""Minimal Feishu (Lark) sender — OpenAPI first, webhook fallback.

Two send paths share a single `send_text` entrypoint:

1. If `FEISHU_BOT_WEBHOOK_URL` is set, POST directly to the custom-bot webhook.
2. Otherwise, exchange `FEISHU_APP_ID` + `FEISHU_APP_SECRET` for a
   tenant_access_token and POST to `im/v1/messages?receive_id_type=chat_id`
   using `FEISHU_REVIEW_CHAT_ID` as the target chat.

Token is cached in-process until ~60s before its server-reported expiry.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Optional

import httpx

FEISHU_BASE = "https://open.feishu.cn"
TOKEN_PATH = "/open-apis/auth/v3/tenant_access_token/internal"
MESSAGE_PATH = "/open-apis/im/v1/messages"
BITABLE_APPS_PATH = "/open-apis/bitable/v1/apps"
TOKEN_REFRESH_SKEW_SEC = 60


class FeishuConfigError(RuntimeError):
    """Raised when required env vars are missing."""


class FeishuAPIError(RuntimeError):
    """Raised when Feishu API returns non-zero code or non-2xx HTTP."""


@dataclass
class FeishuConfig:
    app_id: str
    app_secret: str
    chat_id: str
    webhook_url: Optional[str]

    @classmethod
    def from_env(cls) -> "FeishuConfig":
        webhook_url = os.environ.get("FEISHU_BOT_WEBHOOK_URL") or None

        if webhook_url:
            return cls(
                app_id=os.environ.get("FEISHU_APP_ID", ""),
                app_secret=os.environ.get("FEISHU_APP_SECRET", ""),
                chat_id=os.environ.get("FEISHU_REVIEW_CHAT_ID", ""),
                webhook_url=webhook_url,
            )

        missing: list[str] = []
        app_id = os.environ.get("FEISHU_APP_ID", "").strip()
        app_secret = os.environ.get("FEISHU_APP_SECRET", "").strip()
        chat_id = os.environ.get("FEISHU_REVIEW_CHAT_ID", "").strip()
        if not app_id:
            missing.append("FEISHU_APP_ID")
        if not app_secret:
            missing.append("FEISHU_APP_SECRET")
        if not chat_id:
            missing.append("FEISHU_REVIEW_CHAT_ID")
        if missing:
            raise FeishuConfigError(
                "Missing required env vars for Feishu OpenAPI: "
                + ", ".join(missing)
                + " (or set FEISHU_BOT_WEBHOOK_URL for webhook mode)"
            )
        return cls(app_id=app_id, app_secret=app_secret, chat_id=chat_id, webhook_url=None)


class FeishuClient:
    def __init__(self, config: Optional[FeishuConfig] = None, timeout: float = 10.0) -> None:
        self.config = config or FeishuConfig.from_env()
        self.timeout = timeout
        self._token: Optional[str] = None
        self._token_expires_at: float = 0.0

    def send_text(self, text: str) -> dict:
        return self._send(msg_type="text", content={"text": text}, label="send_text")

    def send_card(self, card: dict) -> dict:
        """Send a Feishu interactive card. `card` is the card JSON (config / header / elements)."""
        return self._send(msg_type="interactive", content=card, label="send_card")

    def _send(self, *, msg_type: str, content: dict, label: str) -> dict:
        if self.config.webhook_url:
            return self._send_webhook(msg_type=msg_type, content=content, label=label)
        return self._send_openapi(msg_type=msg_type, content=content, label=label)

    def _send_webhook(self, *, msg_type: str, content: dict, label: str) -> dict:
        if msg_type == "interactive":
            payload = {"msg_type": "interactive", "card": content}
        else:
            payload = {"msg_type": msg_type, "content": content}
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(self.config.webhook_url or "", json=payload)
        data = self._parse_json(resp, f"Feishu webhook {label}")
        code = data.get("code", data.get("StatusCode"))
        if code not in (0, None):
            raise FeishuAPIError(f"Feishu webhook {label} failed: {data}")
        return data

    def _send_openapi(self, *, msg_type: str, content: dict, label: str) -> dict:
        token = self._get_tenant_access_token()
        url = f"{FEISHU_BASE}{MESSAGE_PATH}?receive_id_type=chat_id"
        payload = {
            "receive_id": self.config.chat_id,
            "msg_type": msg_type,
            "content": json.dumps(content, ensure_ascii=False),
        }
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(
                url,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json=payload,
            )
        data = self._parse_json(resp, f"Feishu im/v1/messages {label}")
        if data.get("code") != 0:
            raise FeishuAPIError(f"Feishu {label} failed: {data}")
        return data

    def _get_tenant_access_token(self) -> str:
        now = time.time()
        if self._token and now < self._token_expires_at - TOKEN_REFRESH_SKEW_SEC:
            return self._token

        url = f"{FEISHU_BASE}{TOKEN_PATH}"
        body = {"app_id": self.config.app_id, "app_secret": self.config.app_secret}
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(url, json=body)
        data = self._parse_json(resp, "Feishu tenant_access_token")
        if data.get("code") != 0 or not data.get("tenant_access_token"):
            raise FeishuAPIError(f"Feishu tenant_access_token failed: {data}")
        self._token = data["tenant_access_token"]
        expire_sec = int(data.get("expire", 7200))
        self._token_expires_at = now + expire_sec
        return self._token

    @staticmethod
    def _parse_json(resp: httpx.Response, label: str) -> dict:
        try:
            return resp.json()
        except json.JSONDecodeError as exc:
            raise FeishuAPIError(
                f"{label} returned non-JSON (status={resp.status_code}): {resp.text[:500]}"
            ) from exc

    # ---- Bitable (multi-dim table) helpers ----

    def _auth_headers(self) -> dict[str, str]:
        token = self._get_tenant_access_token()
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    def bitable_create_app(self, name: str, folder_token: str = "") -> dict:
        """Create a new Bitable app in the given folder (empty = personal space).

        Returns the `app` object: {"app_token", "name", "folder_token", "url", ...}
        """
        url = f"{FEISHU_BASE}{BITABLE_APPS_PATH}"
        payload = {"name": name, "folder_token": folder_token}
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(url, headers=self._auth_headers(), json=payload)
        data = self._parse_json(resp, "Feishu bitable create_app")
        if data.get("code") != 0:
            raise FeishuAPIError(f"bitable_create_app failed: {data}")
        return data["data"]["app"]

    def bitable_list_tables(self, app_token: str) -> list[dict]:
        url = f"{FEISHU_BASE}{BITABLE_APPS_PATH}/{app_token}/tables"
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.get(url, headers=self._auth_headers())
        data = self._parse_json(resp, "Feishu bitable list_tables")
        if data.get("code") != 0:
            raise FeishuAPIError(f"bitable_list_tables failed: {data}")
        return data["data"].get("items", [])

    def bitable_create_table(
        self,
        app_token: str,
        name: str,
        fields: list[dict],
        default_view_name: str = "All",
    ) -> str:
        """Create a table with explicit fields. The first field becomes the primary key."""
        url = f"{FEISHU_BASE}{BITABLE_APPS_PATH}/{app_token}/tables"
        payload = {"table": {"name": name, "default_view_name": default_view_name, "fields": fields}}
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(url, headers=self._auth_headers(), json=payload)
        data = self._parse_json(resp, "Feishu bitable create_table")
        if data.get("code") != 0:
            raise FeishuAPIError(f"bitable_create_table failed for '{name}': {data}")
        return data["data"]["table_id"]

    def bitable_delete_table(self, app_token: str, table_id: str) -> None:
        url = f"{FEISHU_BASE}{BITABLE_APPS_PATH}/{app_token}/tables/{table_id}"
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.delete(url, headers=self._auth_headers())
        data = self._parse_json(resp, "Feishu bitable delete_table")
        if data.get("code") != 0:
            raise FeishuAPIError(f"bitable_delete_table failed: {data}")

    def bitable_create_record(self, app_token: str, table_id: str, fields: dict) -> dict:
        url = f"{FEISHU_BASE}{BITABLE_APPS_PATH}/{app_token}/tables/{table_id}/records"
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(url, headers=self._auth_headers(), json={"fields": fields})
        data = self._parse_json(resp, "Feishu bitable create_record")
        if data.get("code") != 0:
            raise FeishuAPIError(f"bitable_create_record failed: {data}")
        return data["data"]["record"]

    def bitable_list_records(
        self,
        app_token: str,
        table_id: str,
        *,
        page_size: int = 100,
        page_token: Optional[str] = None,
    ) -> dict:
        """List records (single page). Returns the full data dict including `items`,
        `has_more`, `page_token`."""
        url = f"{FEISHU_BASE}{BITABLE_APPS_PATH}/{app_token}/tables/{table_id}/records"
        params: dict[str, str | int] = {"page_size": page_size}
        if page_token:
            params["page_token"] = page_token
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.get(url, headers=self._auth_headers(), params=params)
        data = self._parse_json(resp, "Feishu bitable list_records")
        if data.get("code") != 0:
            raise FeishuAPIError(f"bitable_list_records failed: {data}")
        return data["data"]

    def bitable_update_record(
        self,
        app_token: str,
        table_id: str,
        record_id: str,
        fields: dict,
    ) -> dict:
        url = f"{FEISHU_BASE}{BITABLE_APPS_PATH}/{app_token}/tables/{table_id}/records/{record_id}"
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.put(url, headers=self._auth_headers(), json={"fields": fields})
        data = self._parse_json(resp, "Feishu bitable update_record")
        if data.get("code") != 0:
            raise FeishuAPIError(f"bitable_update_record failed: {data}")
        return data["data"]["record"]

    # ---- Drive permissions (share Bitable with a user) ----

    def drive_add_member(
        self,
        token: str,
        *,
        member_type: str,
        member_id: str,
        perm: str = "edit",
        file_type: str = "bitable",
    ) -> dict:
        """Add a collaborator to a Drive file. For Bitable, `token` = app_token.

        member_type: openid | userid | unionid | email | chatid
        perm: view | edit | full_access
        """
        url = f"{FEISHU_BASE}/open-apis/drive/v1/permissions/{token}/members?type={file_type}"
        payload = {"member_type": member_type, "member_id": member_id, "perm": perm}
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(url, headers=self._auth_headers(), json=payload)
        data = self._parse_json(resp, "Feishu drive add_member")
        if data.get("code") != 0:
            raise FeishuAPIError(f"drive_add_member failed: {data}")
        return data["data"]

    # ---- Contact lookup ----

    def lookup_user_id_by_email(self, email: str) -> Optional[str]:
        """Return open_id for an email, or None if not found. Needs `contact:user.email:readonly`."""
        return self._batch_get_id(emails=[email])

    def lookup_user_id_by_mobile(self, mobile: str) -> Optional[str]:
        """Return open_id for a mobile number, or None if not found.

        Mobile must include country code, e.g. '+8613800138000'.
        Needs `contact:user.phone:readonly`.
        """
        return self._batch_get_id(mobiles=[mobile])

    def _batch_get_id(
        self,
        *,
        emails: Optional[list[str]] = None,
        mobiles: Optional[list[str]] = None,
    ) -> Optional[str]:
        if not emails and not mobiles:
            raise ValueError("must provide emails or mobiles")
        url = f"{FEISHU_BASE}/open-apis/contact/v3/users/batch_get_id?user_id_type=open_id"
        body: dict[str, list[str]] = {}
        if emails:
            body["emails"] = emails
        if mobiles:
            body["mobiles"] = mobiles
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(url, headers=self._auth_headers(), json=body)
        data = self._parse_json(resp, "Feishu batch_get_id")
        if data.get("code") != 0:
            raise FeishuAPIError(f"batch_get_id failed: {data}")
        users = data["data"].get("user_list", [])
        if not users:
            return None
        return users[0].get("user_id")
