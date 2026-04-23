# -*- coding: utf-8 -*-
"""
报告存储模块
============
每次分析自动保存 JSON 报告，支持历史查询和信号追踪。

存储结构:
    ~/.clawdbot/skills/stock-analysis/reports/
    ├── index.json           # 报告索引（最近 1000 条）
    └── 2026/02/04/
        ├── AAPL_20260204_184500.json
        └── daily_summary.json
"""

import json
import os
from dataclasses import asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

# ============================================================
# 常量定义
# ============================================================

REPORTS_DIR = Path.home() / ".clawdbot/skills/stock-analysis/reports"
INDEX_FILE = REPORTS_DIR / "index.json"
MAX_INDEX_SIZE = 1000  # 索引最大条目数


# ============================================================
# 核心函数
# ============================================================

def save_report(signal: Any, mode: str = "full", ai_prediction: dict | None = None) -> str:
    """
    保存分析报告

    Args:
        signal: Signal 对象（来自 analyze_stock.py）
        mode: 分析模式 ("full", "fast", "ai")
        ai_prediction: AI 预测结果（可选）

    Returns:
        报告 ID（格式: TICKER_YYYYMMDD_HHMMSS）
    """
    now = datetime.now()
    report_id = f"{signal.ticker}_{now.strftime('%Y%m%d_%H%M%S')}"

    # 构建目录
    report_dir = REPORTS_DIR / now.strftime("%Y/%m/%d")
    report_dir.mkdir(parents=True, exist_ok=True)

    # 构建报告
    report = _build_report(signal, report_id, now, mode, ai_prediction)

    # 保存报告文件
    report_path = report_dir / f"{report_id}.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    # 更新索引
    _update_index(report_id, signal.ticker, now, signal.signal, signal.composite_score)

    return report_id


def get_history(ticker: str, days: int = 30) -> list[dict]:
    """
    获取指定股票的历史报告

    Args:
        ticker: 股票代码
        days: 查询天数

    Returns:
        报告列表（按时间倒序）
    """
    if not INDEX_FILE.exists():
        return []

    with open(INDEX_FILE, "r", encoding="utf-8") as f:
        index = json.load(f)

    # 筛选
    cutoff = datetime.now() - timedelta(days=days)
    cutoff_str = cutoff.isoformat()

    results = []
    for entry in index.get("entries", []):
        if entry["ticker"] == ticker.upper() and entry["timestamp"] >= cutoff_str:
            # 读取完整报告
            report_path = REPORTS_DIR / entry["path"]
            if report_path.exists():
                with open(report_path, "r", encoding="utf-8") as f:
                    results.append(json.load(f))

    return sorted(results, key=lambda x: x["meta"]["timestamp"], reverse=True)


def compare_signals(ticker: str, date_from: str, date_to: str) -> dict:
    """
    对比信号变化

    Args:
        ticker: 股票代码
        date_from: 起始日期 (YYYY-MM-DD)
        date_to: 结束日期 (YYYY-MM-DD)

    Returns:
        对比结果（信号变化、分数趋势）
    """
    if not INDEX_FILE.exists():
        return {"error": "No reports found"}

    with open(INDEX_FILE, "r", encoding="utf-8") as f:
        index = json.load(f)

    # 筛选时间范围
    from_dt = datetime.fromisoformat(date_from)
    to_dt = datetime.fromisoformat(date_to) + timedelta(days=1)

    reports = []
    for entry in index.get("entries", []):
        if entry["ticker"] != ticker.upper():
            continue
        entry_dt = datetime.fromisoformat(entry["timestamp"])
        if from_dt <= entry_dt < to_dt:
            report_path = REPORTS_DIR / entry["path"]
            if report_path.exists():
                with open(report_path, "r", encoding="utf-8") as f:
                    reports.append(json.load(f))

    if len(reports) < 2:
        return {"error": "Need at least 2 reports to compare"}

    # 按时间排序
    reports = sorted(reports, key=lambda x: x["meta"]["timestamp"])

    # 构建对比
    first = reports[0]
    last = reports[-1]

    signal_changes = []
    for i in range(1, len(reports)):
        prev = reports[i - 1]
        curr = reports[i]
        if prev["signal"]["action"] != curr["signal"]["action"]:
            signal_changes.append({
                "date": curr["meta"]["timestamp"][:10],
                "from": prev["signal"]["action"],
                "to": curr["signal"]["action"],
                "score_change": curr["signal"]["score"] - prev["signal"]["score"]
            })

    return {
        "ticker": ticker.upper(),
        "period": {"from": date_from, "to": date_to},
        "total_reports": len(reports),
        "first_signal": first["signal"]["action"],
        "last_signal": last["signal"]["action"],
        "score_trend": {
            "start": first["signal"]["score"],
            "end": last["signal"]["score"],
            "change": last["signal"]["score"] - first["signal"]["score"]
        },
        "signal_changes": signal_changes
    }


def get_latest(ticker: str) -> dict | None:
    """获取最新一份报告"""
    history = get_history(ticker, days=7)
    return history[0] if history else None


def list_reports(date: str | None = None, limit: int = 20) -> list[dict]:
    """
    列出报告摘要

    Args:
        date: 指定日期 (YYYY-MM-DD)，None 表示今天
        limit: 最大返回数量

    Returns:
        报告摘要列表
    """
    if not INDEX_FILE.exists():
        return []

    with open(INDEX_FILE, "r", encoding="utf-8") as f:
        index = json.load(f)

    entries = index.get("entries", [])

    if date:
        entries = [e for e in entries if e["timestamp"].startswith(date)]

    return entries[:limit]


# ============================================================
# 内部函数
# ============================================================

def _build_report(
    signal: Any,
    report_id: str,
    timestamp: datetime,
    mode: str,
    ai_prediction: dict | None
) -> dict:
    """构建报告数据结构"""
    # 提取组件分数
    component_scores = {}
    if hasattr(signal, "component_scores") and signal.component_scores:
        component_scores = signal.component_scores
    else:
        # 从 Signal 对象重建
        component_scores = {
            "earnings_surprise": {"score": getattr(signal, "earnings_score", None), "weight": 0.30},
            "fundamentals": {"score": getattr(signal, "fundamentals_score", None), "weight": 0.20},
            "analyst_sentiment": {"score": getattr(signal, "analyst_score", None), "weight": 0.20},
            "historical_patterns": {"score": getattr(signal, "historical_score", None), "weight": 0.10},
            "market_context": {"score": getattr(signal, "market_score", None), "weight": 0.10},
            "sector_performance": {"score": getattr(signal, "sector_score", None), "weight": 0.15},
            "momentum": {"score": getattr(signal, "momentum_score", None), "weight": 0.15},
            "sentiment": {"score": getattr(signal, "sentiment_score", None), "weight": 0.10},
        }

    # 提取风险警告
    risks = []
    if hasattr(signal, "caveats") and signal.caveats:
        risks = [{"type": "caveat", "message": c} for c in signal.caveats]
    if hasattr(signal, "risk_warnings") and signal.risk_warnings:
        risks.extend(signal.risk_warnings)

    return {
        "meta": {
            "id": report_id,
            "ticker": signal.ticker,
            "company_name": getattr(signal, "company_name", signal.ticker),
            "timestamp": timestamp.isoformat(),
            "version": "7.0.0",
            "mode": mode
        },
        "signal": {
            "action": signal.signal,
            "score": round(signal.composite_score, 4),
            "confidence": getattr(signal, "confidence", "medium")
        },
        "components": component_scores,
        "price": {
            "current": getattr(signal, "current_price", None),
            "target": getattr(signal, "target_price", None),
            "stop_loss": getattr(signal, "stop_loss", None)
        },
        "risks": risks,
        "summary": getattr(signal, "summary", ""),
        "ai_prediction": ai_prediction
    }


def _update_index(
    report_id: str,
    ticker: str,
    timestamp: datetime,
    signal: str,
    score: float
) -> None:
    """更新报告索引"""
    # 读取现有索引
    if INDEX_FILE.exists():
        with open(INDEX_FILE, "r", encoding="utf-8") as f:
            index = json.load(f)
    else:
        INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
        index = {"entries": []}

    # 添加新条目
    path = timestamp.strftime("%Y/%m/%d") + f"/{report_id}.json"
    index["entries"].insert(0, {
        "id": report_id,
        "ticker": ticker,
        "timestamp": timestamp.isoformat(),
        "signal": signal,
        "score": round(score, 4),
        "path": path
    })

    # 限制索引大小
    if len(index["entries"]) > MAX_INDEX_SIZE:
        index["entries"] = index["entries"][:MAX_INDEX_SIZE]

    # 保存
    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2, ensure_ascii=False)


# ============================================================
# CLI 入口
# ============================================================

def main():
    """命令行入口"""
    import argparse

    parser = argparse.ArgumentParser(description="报告存储管理")
    subparsers = parser.add_subparsers(dest="command")

    # history 子命令
    history_parser = subparsers.add_parser("history", help="查看历史报告")
    history_parser.add_argument("ticker", help="股票代码")
    history_parser.add_argument("--days", type=int, default=30, help="查询天数")
    history_parser.add_argument("--output", choices=["text", "json"], default="text")

    # diff 子命令
    diff_parser = subparsers.add_parser("diff", help="对比信号变化")
    diff_parser.add_argument("ticker", help="股票代码")
    diff_parser.add_argument("--from", dest="date_from", required=True, help="起始日期")
    diff_parser.add_argument("--to", dest="date_to", required=True, help="结束日期")

    # list 子命令
    list_parser = subparsers.add_parser("list", help="列出报告")
    list_parser.add_argument("--date", help="指定日期 (YYYY-MM-DD)")
    list_parser.add_argument("--limit", type=int, default=20)

    args = parser.parse_args()

    if args.command == "history":
        reports = get_history(args.ticker, args.days)
        if args.output == "json":
            print(json.dumps(reports, indent=2, ensure_ascii=False))
        else:
            if not reports:
                print(f"No reports found for {args.ticker} in last {args.days} days")
                return
            print(f"\n{'='*60}")
            print(f" History: {args.ticker.upper()} (Last {args.days} days)")
            print(f"{'='*60}\n")
            for r in reports:
                ts = r["meta"]["timestamp"][:16].replace("T", " ")
                sig = r["signal"]["action"]
                score = r["signal"]["score"]
                print(f"  {ts}  {sig:6}  score={score:+.3f}")
            print()

    elif args.command == "diff":
        result = compare_signals(args.ticker, args.date_from, args.date_to)
        print(json.dumps(result, indent=2, ensure_ascii=False))

    elif args.command == "list":
        reports = list_reports(args.date, args.limit)
        if not reports:
            print("No reports found")
            return
        print(f"\n{'Ticker':<8} {'Signal':<6} {'Score':>8} {'Time':<20}")
        print("-" * 50)
        for r in reports:
            print(f"{r['ticker']:<8} {r['signal']:<6} {r['score']:>+8.3f} {r['timestamp'][:16]}")
        print()

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
