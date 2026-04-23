#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "yfinance>=0.2.40",
#     "pandas>=2.0.0",
#     "numpy>=1.24.0",
# ]
# ///
"""
回测引擎
========
验证 8 维度评分模型在历史数据上的表现。

用法:
    uv run backtest.py AAPL --start 2024-01-01 --end 2025-12-31
    uv run backtest.py AAPL MSFT --start 2024-01-01 --compare
    uv run backtest.py AAPL --optimize

注意:
    - 简化版回测，使用动量+基本面指标模拟评分
    - 完整版需要 vectorbt（可选安装）
"""

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import yfinance as yf


# ============================================================
# 数据结构
# ============================================================

@dataclass
class Trade:
    """单笔交易"""
    entry_date: str
    entry_price: float
    exit_date: str | None
    exit_price: float | None
    quantity: float
    pnl: float | None
    pnl_pct: float | None
    holding_days: int | None


@dataclass
class BacktestResult:
    """回测结果"""
    ticker: str
    start_date: str
    end_date: str
    initial_cash: float
    final_value: float
    total_return: float
    benchmark_return: float
    alpha: float
    max_drawdown: float
    sharpe_ratio: float
    sortino_ratio: float
    win_rate: float
    total_trades: int
    avg_holding_days: float
    best_trade: float
    worst_trade: float
    trades: list[Trade]


# ============================================================
# 评分模型（简化版）
# ============================================================

def calculate_rsi(prices: pd.Series, period: int = 14) -> pd.Series:
    """计算 RSI"""
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


def calculate_macd(prices: pd.Series) -> tuple[pd.Series, pd.Series]:
    """计算 MACD"""
    ema12 = prices.ewm(span=12, adjust=False).mean()
    ema26 = prices.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    return macd, signal


def calculate_momentum_score(prices: pd.Series, idx: int) -> float:
    """
    计算动量评分（-1 到 1）

    基于:
    - RSI (超卖买入，超买卖出)
    - MACD 交叉
    - 价格位置（相对 52 周高低）
    """
    if idx < 60:  # 需要足够历史数据
        return 0.0

    price_slice = prices.iloc[:idx + 1]
    current_price = price_slice.iloc[-1]

    # RSI
    rsi = calculate_rsi(price_slice, 14).iloc[-1]
    if pd.isna(rsi):
        rsi_score = 0
    elif rsi < 30:
        rsi_score = 0.5  # 超卖 → 看涨
    elif rsi > 70:
        rsi_score = -0.5  # 超买 → 看跌
    else:
        rsi_score = (50 - rsi) / 100  # 中性区域

    # MACD
    macd, signal = calculate_macd(price_slice)
    macd_val = macd.iloc[-1]
    signal_val = signal.iloc[-1]
    if pd.isna(macd_val) or pd.isna(signal_val):
        macd_score = 0
    elif macd_val > signal_val:
        macd_score = 0.3  # 金叉
    else:
        macd_score = -0.3  # 死叉

    # 52 周位置
    if len(price_slice) >= 252:
        high_52w = price_slice.iloc[-252:].max()
        low_52w = price_slice.iloc[-252:].min()
        position = (current_price - low_52w) / (high_52w - low_52w) if high_52w != low_52w else 0.5
        # 靠近低点 → 看涨，靠近高点 → 看跌
        position_score = 0.4 * (0.5 - position)
    else:
        position_score = 0

    # 综合
    return np.clip(rsi_score * 0.4 + macd_score * 0.3 + position_score * 0.3, -1, 1)


def calculate_trend_score(prices: pd.Series, idx: int) -> float:
    """
    计算趋势评分（-1 到 1）

    基于:
    - 短期 vs 长期均线
    - 价格动量
    """
    if idx < 50:
        return 0.0

    price_slice = prices.iloc[:idx + 1]

    # 均线
    ma10 = price_slice.rolling(10).mean().iloc[-1]
    ma50 = price_slice.rolling(50).mean().iloc[-1]

    if pd.isna(ma10) or pd.isna(ma50):
        ma_score = 0
    elif ma10 > ma50:
        ma_score = 0.5  # 短期 > 长期 → 上升趋势
    else:
        ma_score = -0.5

    # 10 日动量
    if len(price_slice) >= 10:
        momentum_10d = (price_slice.iloc[-1] / price_slice.iloc[-10] - 1)
        momentum_score = np.clip(momentum_10d * 5, -0.5, 0.5)
    else:
        momentum_score = 0

    return np.clip(ma_score * 0.6 + momentum_score * 0.4, -1, 1)


def calculate_daily_score(prices: pd.Series, idx: int) -> float:
    """
    计算每日综合评分（-1 到 1）

    组合动量和趋势评分
    """
    momentum = calculate_momentum_score(prices, idx)
    trend = calculate_trend_score(prices, idx)

    # 加权综合
    return momentum * 0.5 + trend * 0.5


# ============================================================
# 回测引擎
# ============================================================

def run_backtest(
    ticker: str,
    start: str,
    end: str,
    buy_threshold: float = 0.33,
    sell_threshold: float = -0.33,
    initial_cash: float = 100000,
    commission: float = 0.001,
    verbose: bool = False
) -> BacktestResult:
    """
    运行回测

    Args:
        ticker: 股票代码
        start: 起始日期
        end: 结束日期
        buy_threshold: 买入阈值
        sell_threshold: 卖出阈值
        initial_cash: 初始资金
        commission: 手续费率
        verbose: 详细输出

    Returns:
        回测结果
    """
    # 获取数据（多取 60 天用于指标计算）
    start_dt = datetime.fromisoformat(start) - timedelta(days=90)
    data = yf.download(ticker, start=start_dt.strftime("%Y-%m-%d"), end=end, progress=False)

    if data.empty:
        raise ValueError(f"No data for {ticker}")

    prices = data["Close"].squeeze()
    if isinstance(prices, pd.DataFrame):
        prices = prices.iloc[:, 0]

    # 找到实际起始索引
    start_idx = 0
    for i, date in enumerate(prices.index):
        if date.strftime("%Y-%m-%d") >= start:
            start_idx = i
            break

    # 初始化
    cash = initial_cash
    position = 0
    entry_price = 0
    entry_date = None
    trades: list[Trade] = []
    equity_curve = []

    # 逐日回测
    for i in range(start_idx, len(prices)):
        current_date = prices.index[i]
        current_price = prices.iloc[i]

        # 计算评分
        score = calculate_daily_score(prices, i)

        # 当前权益
        current_equity = cash + position * current_price
        equity_curve.append(current_equity)

        # 交易逻辑
        if position == 0 and score > buy_threshold:
            # 买入
            shares = int((cash * 0.95) / current_price)  # 95% 仓位
            if shares > 0:
                cost = shares * current_price * (1 + commission)
                if cost <= cash:
                    cash -= cost
                    position = shares
                    entry_price = current_price
                    entry_date = current_date.strftime("%Y-%m-%d")
                    if verbose:
                        print(f"  BUY  {current_date.strftime('%Y-%m-%d')} @ ${current_price:.2f} x {shares} (score={score:.3f})")

        elif position > 0 and score < sell_threshold:
            # 卖出
            proceeds = position * current_price * (1 - commission)
            cash += proceeds
            pnl = proceeds - position * entry_price * (1 + commission)
            pnl_pct = (current_price / entry_price - 1) * 100
            holding_days = (current_date - pd.Timestamp(entry_date)).days

            trades.append(Trade(
                entry_date=entry_date,
                entry_price=entry_price,
                exit_date=current_date.strftime("%Y-%m-%d"),
                exit_price=current_price,
                quantity=position,
                pnl=pnl,
                pnl_pct=pnl_pct,
                holding_days=holding_days
            ))

            if verbose:
                print(f"  SELL {current_date.strftime('%Y-%m-%d')} @ ${current_price:.2f} (pnl={pnl_pct:+.1f}%)")

            position = 0
            entry_price = 0
            entry_date = None

    # 最终结算（如果还有持仓）
    if position > 0:
        final_price = prices.iloc[-1]
        proceeds = position * final_price * (1 - commission)
        cash += proceeds
        pnl = proceeds - position * entry_price * (1 + commission)
        pnl_pct = (final_price / entry_price - 1) * 100
        holding_days = (prices.index[-1] - pd.Timestamp(entry_date)).days

        trades.append(Trade(
            entry_date=entry_date,
            entry_price=entry_price,
            exit_date=prices.index[-1].strftime("%Y-%m-%d"),
            exit_price=final_price,
            quantity=position,
            pnl=pnl,
            pnl_pct=pnl_pct,
            holding_days=holding_days
        ))

    # 计算指标
    final_value = cash
    total_return = (final_value / initial_cash - 1) * 100

    # 基准收益（SPY）
    spy = yf.download("SPY", start=start, end=end, progress=False)
    if not spy.empty:
        spy_prices = spy["Close"].squeeze()
        benchmark_return = (spy_prices.iloc[-1] / spy_prices.iloc[0] - 1) * 100
    else:
        benchmark_return = 0

    alpha = total_return - benchmark_return

    # 最大回撤
    equity_series = pd.Series(equity_curve)
    rolling_max = equity_series.expanding().max()
    drawdown = (equity_series - rolling_max) / rolling_max
    max_drawdown = drawdown.min() * 100

    # 夏普比率（简化：假设无风险利率 4%）
    if len(equity_curve) > 1:
        daily_returns = equity_series.pct_change().dropna()
        if daily_returns.std() > 0:
            sharpe_ratio = (daily_returns.mean() * 252 - 0.04) / (daily_returns.std() * np.sqrt(252))
        else:
            sharpe_ratio = 0
    else:
        sharpe_ratio = 0

    # 索提诺比率
    if len(equity_curve) > 1:
        negative_returns = daily_returns[daily_returns < 0]
        if len(negative_returns) > 0 and negative_returns.std() > 0:
            sortino_ratio = (daily_returns.mean() * 252 - 0.04) / (negative_returns.std() * np.sqrt(252))
        else:
            sortino_ratio = sharpe_ratio
    else:
        sortino_ratio = 0

    # 胜率
    if trades:
        winning_trades = [t for t in trades if t.pnl and t.pnl > 0]
        win_rate = len(winning_trades) / len(trades) * 100
        avg_holding = np.mean([t.holding_days for t in trades if t.holding_days])
        pnl_list = [t.pnl_pct for t in trades if t.pnl_pct is not None]
        best_trade = max(pnl_list) if pnl_list else 0
        worst_trade = min(pnl_list) if pnl_list else 0
    else:
        win_rate = 0
        avg_holding = 0
        best_trade = 0
        worst_trade = 0

    return BacktestResult(
        ticker=ticker,
        start_date=start,
        end_date=end,
        initial_cash=initial_cash,
        final_value=final_value,
        total_return=total_return,
        benchmark_return=benchmark_return,
        alpha=alpha,
        max_drawdown=max_drawdown,
        sharpe_ratio=sharpe_ratio,
        sortino_ratio=sortino_ratio,
        win_rate=win_rate,
        total_trades=len(trades),
        avg_holding_days=avg_holding,
        best_trade=best_trade,
        worst_trade=worst_trade,
        trades=trades
    )


def optimize_thresholds(
    ticker: str,
    start: str,
    end: str,
    buy_range: tuple = (0.2, 0.5, 0.05),
    sell_range: tuple = (-0.5, -0.2, 0.05),
    verbose: bool = False
) -> dict:
    """
    参数优化

    Args:
        ticker: 股票代码
        start/end: 时间范围
        buy_range: (min, max, step) 买入阈值范围
        sell_range: (min, max, step) 卖出阈值范围

    Returns:
        最优参数和结果
    """
    best_result = None
    best_params = None
    best_sharpe = -999

    buy_thresholds = np.arange(*buy_range)
    sell_thresholds = np.arange(*sell_range)

    total = len(buy_thresholds) * len(sell_thresholds)
    count = 0

    for buy_th in buy_thresholds:
        for sell_th in sell_thresholds:
            count += 1
            if verbose:
                print(f"\rOptimizing... {count}/{total}", end="", file=sys.stderr)

            try:
                result = run_backtest(ticker, start, end, buy_th, sell_th, verbose=False)
                if result.sharpe_ratio > best_sharpe:
                    best_sharpe = result.sharpe_ratio
                    best_result = result
                    best_params = {"buy_threshold": buy_th, "sell_threshold": sell_th}
            except Exception:
                continue

    if verbose:
        print(file=sys.stderr)

    return {
        "best_params": best_params,
        "best_sharpe": best_sharpe,
        "best_result": best_result
    }


# ============================================================
# 输出格式化
# ============================================================

def format_result_text(result: BacktestResult) -> str:
    """格式化为文本"""
    lines = [
        "",
        "╔" + "═" * 62 + "╗",
        f"║{'BACKTEST REPORT: ' + result.ticker:^62}║",
        f"║{result.start_date + ' to ' + result.end_date:^62}║",
        "╠" + "═" * 62 + "╣",
        "║ PERFORMANCE                                                  ║",
        "║ " + "─" * 60 + " ║",
        f"║ Total Return:        {result.total_return:>+8.1f}%{' ' * 32}║",
        f"║ SPY Benchmark:       {result.benchmark_return:>+8.1f}%{' ' * 32}║",
        f"║ Alpha:               {result.alpha:>+8.1f}%{' ' * 32}║",
        "║                                                              ║",
        "║ RISK METRICS                                                 ║",
        "║ " + "─" * 60 + " ║",
        f"║ Max Drawdown:        {result.max_drawdown:>8.1f}%{' ' * 32}║",
        f"║ Sharpe Ratio:        {result.sharpe_ratio:>8.2f}{' ' * 33}║",
        f"║ Sortino Ratio:       {result.sortino_ratio:>8.2f}{' ' * 33}║",
        f"║ Win Rate:            {result.win_rate:>8.1f}% ({len([t for t in result.trades if t.pnl and t.pnl > 0])}/{result.total_trades} trades){' ' * 14}║",
        "║                                                              ║",
        "║ TRADE SUMMARY                                                ║",
        "║ " + "─" * 60 + " ║",
        f"║ Total Trades:        {result.total_trades:>8}{' ' * 33}║",
        f"║ Avg Holding Period:  {result.avg_holding_days:>8.1f} days{' ' * 27}║",
        f"║ Best Trade:          {result.best_trade:>+8.1f}%{' ' * 32}║",
        f"║ Worst Trade:         {result.worst_trade:>+8.1f}%{' ' * 32}║",
        "╚" + "═" * 62 + "╝",
        ""
    ]
    return "\n".join(lines)


def format_result_json(result: BacktestResult) -> str:
    """格式化为 JSON"""
    data = {
        "ticker": result.ticker,
        "period": {"start": result.start_date, "end": result.end_date},
        "performance": {
            "initial_cash": result.initial_cash,
            "final_value": round(result.final_value, 2),
            "total_return": round(result.total_return, 2),
            "benchmark_return": round(result.benchmark_return, 2),
            "alpha": round(result.alpha, 2)
        },
        "risk": {
            "max_drawdown": round(result.max_drawdown, 2),
            "sharpe_ratio": round(result.sharpe_ratio, 2),
            "sortino_ratio": round(result.sortino_ratio, 2)
        },
        "trades": {
            "total": result.total_trades,
            "win_rate": round(result.win_rate, 2),
            "avg_holding_days": round(result.avg_holding_days, 1),
            "best_trade": round(result.best_trade, 2),
            "worst_trade": round(result.worst_trade, 2)
        },
        "trade_log": [
            {
                "entry_date": t.entry_date,
                "entry_price": round(t.entry_price, 2),
                "exit_date": t.exit_date,
                "exit_price": round(t.exit_price, 2) if t.exit_price else None,
                "pnl_pct": round(t.pnl_pct, 2) if t.pnl_pct else None,
                "holding_days": t.holding_days
            }
            for t in result.trades
        ]
    }
    return json.dumps(data, indent=2)


# ============================================================
# 主入口
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="股票回测引擎")
    parser.add_argument("tickers", nargs="+", help="股票代码")
    parser.add_argument("--start", required=True, help="起始日期 (YYYY-MM-DD)")
    parser.add_argument("--end", default=datetime.now().strftime("%Y-%m-%d"), help="结束日期")
    parser.add_argument("--buy-threshold", type=float, default=0.33, help="买入阈值")
    parser.add_argument("--sell-threshold", type=float, default=-0.33, help="卖出阈值")
    parser.add_argument("--initial-cash", type=float, default=100000, help="初始资金")
    parser.add_argument("--optimize", action="store_true", help="参数优化模式")
    parser.add_argument("--output", choices=["text", "json"], default="text")
    parser.add_argument("--verbose", "-v", action="store_true")

    args = parser.parse_args()

    for ticker in args.tickers:
        ticker = ticker.upper()

        if args.verbose:
            print(f"\n=== Backtesting {ticker} ===\n", file=sys.stderr)

        try:
            if args.optimize:
                # 参数优化
                print(f"Optimizing parameters for {ticker}...", file=sys.stderr)
                opt_result = optimize_thresholds(ticker, args.start, args.end, verbose=args.verbose)

                if opt_result["best_result"]:
                    print(f"\nBest Parameters:", file=sys.stderr)
                    print(f"  Buy Threshold:  {opt_result['best_params']['buy_threshold']:.2f}", file=sys.stderr)
                    print(f"  Sell Threshold: {opt_result['best_params']['sell_threshold']:.2f}", file=sys.stderr)
                    print(f"  Sharpe Ratio:   {opt_result['best_sharpe']:.2f}", file=sys.stderr)

                    if args.output == "json":
                        print(format_result_json(opt_result["best_result"]))
                    else:
                        print(format_result_text(opt_result["best_result"]))
                else:
                    print("Optimization failed", file=sys.stderr)
            else:
                # 普通回测
                result = run_backtest(
                    ticker,
                    args.start,
                    args.end,
                    args.buy_threshold,
                    args.sell_threshold,
                    args.initial_cash,
                    verbose=args.verbose
                )

                if args.output == "json":
                    print(format_result_json(result))
                else:
                    print(format_result_text(result))

        except Exception as e:
            print(f"Error backtesting {ticker}: {e}", file=sys.stderr)
            if args.verbose:
                import traceback
                traceback.print_exc()


if __name__ == "__main__":
    main()
