#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "yfinance>=0.2.40",
#     "pandas>=2.0.0",
#     "fear-and-greed>=0.4",
#     "edgartools>=2.0.0",
#     "feedparser>=6.0.0",
# ]
# ///
"""
Stock Analysis v12 — 单股分析 + 深度报告体系。

快速模式 → 综合报告（10 维度评分，2-3 秒）
完整模式 → 综合报告 + 1 份深度报告（用户选择领域）

Usage:
    uv run analyze_stock.py TICKER --fast --output-dir ~/output/
    uv run analyze_stock.py TICKER --deep valuation --output-dir ~/output/
"""

import argparse
import asyncio
import json
import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path

import yfinance as yf

from shared import (
    Fundamentals,
    Signal,
    analyze_earnings_surprise,
    analyze_earnings_timing,
    analyze_fundamentals,
    analyze_analyst_sentiment,
    analyze_historical_patterns,
    analyze_market_context,
    analyze_peer_comparison,
    analyze_sector_performance,
    analyze_sentiment,
    analyze_technical,
    check_breaking_news,
    check_sector_geopolitical_risk,
    fetch_stock_data,
    format_output_json,
    format_output_text,
    resolve_ticker,
    synthesize_signal,
)

# 深度分析领域
DEEP_CHOICES = ["valuation", "growth", "technical", "fundamentals", "peers", "dividends"]


def parse_args():
    parser = argparse.ArgumentParser(description="Stock Analysis v12")
    parser.add_argument("ticker", help="Stock ticker or company name")
    parser.add_argument("--output", choices=["text", "json"], default="text")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--no-insider", action="store_true")
    parser.add_argument("--fast", action="store_true", help="Fast mode: skip slow analyses")
    parser.add_argument("--deep", choices=DEEP_CHOICES, help="Deep analysis domain")
    parser.add_argument("--output-dir", type=str, help="Save report .md files to directory")
    parser.add_argument("--apply-verification", type=str,
                        help="Path to Claude verification JSON, regenerate report with verified data")
    return parser.parse_args()


def analyze_single(ticker_input: str, args, breaking_news):
    """分析单只股票，返回综合报告所需全部数据。"""
    try:
        ticker, source = resolve_ticker(ticker_input)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(2)

    if args.verbose:
        print(f"\n=== Analyzing {ticker} (resolved from '{ticker_input}' via {source}) ===\n", file=sys.stderr)

    data = fetch_stock_data(ticker, verbose=args.verbose)
    if data is None:
        print(f"Error: Ticker '{ticker}' data unavailable", file=sys.stderr)
        sys.exit(2)

    # 深度模式获取额外季度数据
    if args.deep:
        from shared.data_fetcher import fetch_deep_data
        data = fetch_deep_data(data, verbose=args.verbose)

    # 始终执行验证（SEC EDGAR + Brave 全量）
    from shared.data_fetcher import fetch_verified_data
    data = fetch_verified_data(data, verbose=args.verbose)

    company = data.info.get("longName") or data.info.get("shortName") or ticker

    # ---- 分析 ----
    earnings = analyze_earnings_surprise(data)
    fundamentals = analyze_fundamentals(data, sector=data.info.get("sector", ""))
    analysts = analyze_analyst_sentiment(data)
    historical = analyze_historical_patterns(data)

    if args.verbose:
        print("Checking earnings timing...", file=sys.stderr)
    earnings_timing = analyze_earnings_timing(data)

    if args.verbose:
        print("Analyzing sector performance...", file=sys.stderr)
    sector = analyze_sector_performance(data, verbose=args.verbose)

    if args.verbose:
        print("Analyzing peer comparison...", file=sys.stderr)
    peer = analyze_peer_comparison(data, verbose=args.verbose)

    # 市场环境
    if args.verbose:
        print("Analyzing market context...", file=sys.stderr)
    market_context = analyze_market_context(verbose=args.verbose)

    # 技术分析
    if args.verbose:
        print("Analyzing technical indicators...", file=sys.stderr)
    technical = analyze_technical(data)

    # 情绪
    if args.verbose:
        print("Analyzing sentiment...", file=sys.stderr)
    sentiment = asyncio.run(
        analyze_sentiment(data, verbose=args.verbose, skip_insider=args.no_insider)
    )

    # 地缘政治
    geo_warning, geo_penalty = check_sector_geopolitical_risk(
        ticker, data.info.get("sector"), breaking_news, verbose=args.verbose,
    )

    if args.verbose:
        _print_status(earnings, fundamentals, analysts, historical,
                      market_context, sector, technical, sentiment, peer, earnings_timing)

    # 合成
    signal = synthesize_signal(
        ticker=ticker, company_name=company,
        earnings=earnings, fundamentals=fundamentals,
        analysts=analysts, historical=historical,
        market_context=market_context, sector=sector,
        earnings_timing=earnings_timing,
        technical=technical, sentiment=sentiment, peer=peer,
        breaking_news=breaking_news,
        geopolitical_risk_warning=geo_warning,
        geopolitical_risk_penalty=geo_penalty,
        web_verification=data.web_verification,
    )

    return signal, data, technical, peer, sentiment


def _print_status(earnings, fundamentals, analysts, historical,
                  market, sector, technical, sentiment, peer, timing):
    """Verbose 状态输出。"""
    check = lambda x: "Y" if x else "-"
    print("Components analyzed:", file=sys.stderr)
    print(f"  Earnings: {check(earnings)}  Fundamentals: {check(fundamentals)}  Analysts: {check(analysts and analysts.score)}", file=sys.stderr)
    print(f"  Historical: {check(historical)}  Market: {check(market)}  Sector: {check(sector)}", file=sys.stderr)
    print(f"  Technical: {check(technical)}  Sentiment: {check(sentiment)}  Peers: {check(peer)}", file=sys.stderr)
    print(f"  Earnings Timing: {check(timing)}", file=sys.stderr)
    print("", file=sys.stderr)


def main():
    args = parse_args()

    if args.fast:
        args.no_insider = True

    # 突发新闻
    breaking_news = None
    if not args.fast:
        if args.verbose:
            print("Checking breaking news (last 24h)...", file=sys.stderr)
        breaking_news = check_breaking_news(verbose=args.verbose)
        if breaking_news and args.verbose:
            print(f"  Found {len(breaking_news)} breaking news alert(s)\n", file=sys.stderr)
    elif args.verbose:
        print("Skipping breaking news check (--fast mode)", file=sys.stderr)

    # 分析
    signal, data, technical, peer, sentiment = analyze_single(args.ticker, args, breaking_news)

    # 深度报告（先执行，以便综合报告可引用深度估值数据）
    deep_valuation = None
    if args.deep:
        deep_valuation = _run_deep_analysis(args, signal, data)

    # ---- 阶段 2：应用 Claude 验证结果 ----
    if args.apply_verification:
        vpath = Path(args.apply_verification).expanduser()
        if vpath.exists():
            from shared.web_verifier import apply_verification
            claude_results = json.loads(vpath.read_text(encoding="utf-8"))
            data.web_verification = apply_verification(
                data.ticker, data.pending_verification, claude_results,
            )
            # 重新合成 signal 以纳入验证数据
            signal = _rebuild_signal_with_verification(
                signal, data.web_verification,
            )
            if args.verbose:
                wv = data.web_verification
                print(f"  Applied verification: {wv.confirmed_count} confirmed, "
                      f"{wv.warning_count} warnings", file=sys.stderr)

    # 综合报告输出
    if args.output == "json":
        print(format_output_json(signal))
    else:
        report = format_output_text(
            signal, data_info=data.info, technical=technical,
            peer=peer, sentiment=sentiment, deep_valuation=deep_valuation,
            web_verification=data.web_verification,
        )
        print(report)

    # 保存综合报告
    if args.output_dir:
        out = Path(args.output_dir).expanduser()
        out.mkdir(parents=True, exist_ok=True)
        today = date.today().isoformat()

        report_text = format_output_text(
            signal, data_info=data.info, technical=technical,
            peer=peer, sentiment=sentiment, deep_valuation=deep_valuation,
            web_verification=data.web_verification,
        )
        fp = out / f"{signal.ticker}-综合报告-{today}.md"
        fp.write_text(report_text, encoding="utf-8")
        print(f"\n综合报告已保存: {fp}", file=sys.stderr)

    # ---- 阶段 1：输出 VERIFY_REQUEST（供 Claude 读取） ----
    if data.pending_verification and not args.apply_verification:
        verify_json = json.dumps(data.pending_verification, ensure_ascii=False)
        print(f"\n<!-- VERIFY_REQUEST: {verify_json} -->", file=sys.stderr)


def _rebuild_signal_with_verification(signal, web_verification):
    """将 Claude 验证结果回填到 signal 的验证字段。"""
    verified_metrics = {}
    verification_warnings = []

    for key, mv in web_verification.metrics.items():
        verified_metrics[key] = {
            "status": mv.status.value,
            "discrepancy_pct": mv.discrepancy_pct,
            "our_value": mv.our_value,
            "web_value": mv.web_value,
        }
    verification_warnings = list(web_verification.warnings)

    # 更新 signal 字段
    signal.verification_confidence = web_verification.overall_confidence
    signal.verified_metrics = verified_metrics
    signal.verification_warnings = verification_warnings

    # 置信度惩罚
    if web_verification.warning_count >= 3:
        signal.confidence = max(0.05, signal.confidence - 0.20)
    elif web_verification.warning_count >= 1:
        signal.confidence = max(0.05, signal.confidence - 0.10)

    return signal


def _run_deep_analysis(args, signal, data):
    """执行深度分析并输出/保存报告。返回深度结果（用于交叉引用）。"""
    from shared.deep_analyzers import run_deep_analysis
    from shared.deep_report_formatter import format_deep_report

    if args.verbose:
        print(f"\nRunning deep analysis: {args.deep}...", file=sys.stderr)

    deep_result = run_deep_analysis(args.deep, data, signal, verbose=args.verbose)
    if deep_result is None:
        print(f"Warning: Deep analysis '{args.deep}' returned no data", file=sys.stderr)
        return None

    deep_report = format_deep_report(args.deep, deep_result, signal)

    if args.output == "json":
        print(json.dumps(asdict(deep_result), indent=2, default=str))
    else:
        print(f"\n{'=' * 60}\n")
        print(deep_report)

    if args.output_dir:
        out = Path(args.output_dir).expanduser()
        out.mkdir(parents=True, exist_ok=True)
        today = date.today().isoformat()

        domain_names = {
            "valuation": "估值", "growth": "成长性", "technical": "技术面",
            "fundamentals": "基本面", "peers": "同行对比", "dividends": "股息",
        }
        domain_cn = domain_names.get(args.deep, args.deep)
        fp = out / f"{signal.ticker}-{domain_cn}-深度报告-{today}.md"
        fp.write_text(deep_report, encoding="utf-8")
        print(f"\n深度报告已保存: {fp}", file=sys.stderr)

    # 返回估值深度结果供综合报告交叉引用
    return deep_result if args.deep == "valuation" else None


if __name__ == "__main__":
    main()
