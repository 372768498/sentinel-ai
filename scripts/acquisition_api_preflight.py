from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

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
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


@dataclass(frozen=True)
class Check:
    name: str
    keys: tuple[str, ...]
    required_now: bool
    note: str


CHECKS = (
    Check(
        name="内容生成 Content Generation",
        keys=("ANTHROPIC_API_KEY",),
        required_now=True,
        note="缺失时不会生成真实草稿，避免 mock 内容进入飞书。",
    ),
    Check(
        name="飞书审核 Feishu Review",
        keys=(
            "FEISHU_APP_ID",
            "FEISHU_APP_SECRET",
            "FEISHU_REVIEW_CHAT_ID",
            "FEISHU_BITABLE_APP_TOKEN",
            "FEISHU_CONTENT_QUEUE_TABLE_ID",
            "FEISHU_PERFORMANCE_TABLE_ID",
        ),
        required_now=True,
        note="用于内容队列、审核卡片、KPI 表和每日摘要。",
    ),
    Check(
        name="数据库 Attribution DB",
        keys=("DATABASE_URL",),
        required_now=True,
        note="用于读取 VisitEvent / EmailLead / SubscriptionStatus。",
    ),
    Check(
        name="产品链接 Public URL",
        keys=("GROWTH_OS_PUBLIC_URL",),
        required_now=True,
        note="用于生成 /stocks/{ticker} UTM CTA。",
    ),
    Check(
        name="X 发布 X Publishing",
        keys=("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET"),
        required_now=False,
        note="第一阶段可先 dry-run；打开 live posting 前必须补齐。",
    ),
    Check(
        name="YouTube 上传 YouTube Upload",
        keys=("YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN"),
        required_now=False,
        note="第一阶段先生成 Shorts 素材包，上传 API 可后置。",
    ),
    Check(
        name="TikTok 上传 TikTok Upload",
        keys=("TIKTOK_CLIENT_KEY", "TIKTOK_CLIENT_SECRET", "TIKTOK_REFRESH_TOKEN"),
        required_now=False,
        note="第一阶段先生成 TikTok 素材包，上传 API 可后置。",
    ),
    Check(
        name="Reddit 发布 Reddit Publishing",
        keys=("REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "REDDIT_REFRESH_TOKEN"),
        required_now=False,
        note="第一阶段建议只生成草稿，人工发帖。",
    ),
    Check(
        name="AdsPower 矩阵 AdsPower Matrix",
        keys=("ADSPOWER_API_BASE", "ADSPOWER_API_KEY"),
        required_now=False,
        note="第三阶段才接入；现在缺失不阻塞。",
    ),
)


def _mask(value: str) -> str:
    if len(value) <= 8:
        return "***"
    return value[:4] + "…" + value[-4:]


def main() -> int:
    _load_env_local()
    lines = ["# Sentinel AI 获客系统 API Key 预检", ""]
    missing_required: list[str] = []

    for check in CHECKS:
        present = [key for key in check.keys if os.environ.get(key, "").strip()]
        missing = [key for key in check.keys if key not in present]
        status = "通过" if not missing else ("阻塞" if check.required_now else "后置")
        lines.extend(
            [
                f"## {check.name}",
                "",
                f"- 状态：{status}",
                f"- 说明：{check.note}",
                "",
                "| Key | 状态 |",
                "| --- | --- |",
            ]
        )
        for key in check.keys:
            value = os.environ.get(key, "").strip()
            if value:
                lines.append(f"| `{key}` | 已配置 `{_mask(value)}` |")
            else:
                lines.append(f"| `{key}` | 缺失 |")
        lines.append("")
        if check.required_now:
            missing_required.extend(missing)

    out = REPO_ROOT / "docs" / "growth-runs" / "api-key-preflight.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"预检报告已生成：{out}")
    if missing_required:
        print("当前阻塞项：")
        for key in missing_required:
            print(f"- {key}")
        return 1
    print("必要 API Key 已齐，可以跑真实 Operator dry-run。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
