from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, EmailStr, Field


AnalyzeMode = Literal["basic", "deep"]
JobState = Literal["queued", "running", "completed", "failed"]


class AnalyzeRequest(BaseModel):
    history_id: str = Field(alias="historyId")
    access_token: str = Field(alias="accessToken")
    ticker: str
    email: EmailStr
    requested_mode: AnalyzeMode = Field(alias="requestedMode")
    deep_mode: str | None = Field(default=None, alias="deepMode")
    callback_url: str = Field(alias="callbackUrl")
    callback_secret: str = Field(alias="callbackSecret")

    model_config = {
        "populate_by_name": True
    }


class AnalyzeAccepted(BaseModel):
    job_id: str = Field(alias="jobId")
    status: JobState
    events_url: str = Field(alias="eventsUrl")
    poll_url: str = Field(alias="pollUrl")

    model_config = {
        "populate_by_name": True
    }


PushAlertTarget = Literal["all", "watchers"]


class PushAlertRequest(BaseModel):
    """Operator-triggered caught-moment alert. Internal-token protected."""
    ticker: str
    headline: str
    detail: str = ""
    source_url: str = ""
    change_pct: float = 0.0
    target: PushAlertTarget = "watchers"  # "all"=every active VIP, "watchers"=ticker holders only


class CallbackPayload(BaseModel):
    history_id: str = Field(alias="historyId")
    job_id: str = Field(alias="jobId")
    status: Literal["completed", "failed"]
    result_json: dict | None = Field(default=None, alias="resultJson")
    markdown_report: str | None = Field(default=None, alias="markdownReport")
    email_delivery_id: str | None = Field(default=None, alias="emailDeliveryId")
    error_message: str | None = Field(default=None, alias="errorMessage")

    model_config = {
        "populate_by_name": True
    }
