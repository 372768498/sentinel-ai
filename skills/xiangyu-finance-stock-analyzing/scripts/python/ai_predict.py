#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "yfinance>=0.2.40",
#     "feedparser>=6.0.0",
#     "anthropic>=0.40.0",
#     "openai>=1.50.0",
# ]
# ///
"""
AI 趋势预测
===========
使用 LLM 分析新闻、财报、分析师评论，生成趋势判断。

用法:
    uv run ai_predict.py AAPL
    uv run ai_predict.py AAPL --provider openai --model gpt-4o
    uv run ai_predict.py AAPL MSFT --output json

支持的 LLM 提供商:
    - anthropic (默认): Claude 模型
    - openai: GPT 模型
    - openrouter: 多模型网关

环境变量:
    - ANTHROPIC_API_KEY
    - OPENAI_API_KEY
    - OPENROUTER_API_KEY
"""

import argparse
import json
import os
import sys
from dataclasses import dataclass, asdict
from datetime import datetime

import feedparser
import yfinance as yf


# ============================================================
# 数据结构
# ============================================================

@dataclass
class AIPrediction:
    """AI 预测结果"""
    ticker: str
    trend: str  # "bullish", "bearish", "neutral"
    confidence: float  # 0.0 - 1.0
    key_factors: list[str]
    risks: list[str]
    reasoning: str
    model: str
    provider: str
    timestamp: str


# ============================================================
# 上下文收集
# ============================================================

def get_news_context(ticker: str, max_items: int = 15) -> str:
    """获取最近新闻"""
    url = f"https://news.google.com/rss/search?q={ticker}+stock&hl=en-US&gl=US&ceid=US:en"

    try:
        feed = feedparser.parse(url)
        news_items = []
        for entry in feed.entries[:max_items]:
            # 清理标题
            title = entry.title.replace(" - ", " | ")
            pub_date = entry.get("published", "")[:16]
            news_items.append(f"- [{pub_date}] {title}")

        return "\n".join(news_items) if news_items else "No recent news found."
    except Exception as e:
        return f"Failed to fetch news: {e}"


def get_financial_context(ticker: str) -> str:
    """获取财务数据摘要"""
    try:
        stock = yf.Ticker(ticker)
        info = stock.info

        # 基本信息
        company_name = info.get("longName", ticker)
        sector = info.get("sector", "N/A")
        industry = info.get("industry", "N/A")

        # 价格
        current_price = info.get("regularMarketPrice", "N/A")
        prev_close = info.get("previousClose", "N/A")
        high_52w = info.get("fiftyTwoWeekHigh", "N/A")
        low_52w = info.get("fiftyTwoWeekLow", "N/A")

        # 估值
        pe = info.get("trailingPE", "N/A")
        forward_pe = info.get("forwardPE", "N/A")
        peg = info.get("pegRatio", "N/A")
        pb = info.get("priceToBook", "N/A")

        # 财务
        revenue_growth = info.get("revenueGrowth", "N/A")
        if isinstance(revenue_growth, float):
            revenue_growth = f"{revenue_growth * 100:.1f}%"

        profit_margin = info.get("profitMargins", "N/A")
        if isinstance(profit_margin, float):
            profit_margin = f"{profit_margin * 100:.1f}%"

        # 分析师
        target_price = info.get("targetMeanPrice", "N/A")
        recommendation = info.get("recommendationKey", "N/A")
        num_analysts = info.get("numberOfAnalystOpinions", "N/A")

        # 短期表现
        hist = stock.history(period="1mo")
        if not hist.empty:
            month_return = (hist["Close"].iloc[-1] / hist["Close"].iloc[0] - 1) * 100
            month_return_str = f"{month_return:+.1f}%"
        else:
            month_return_str = "N/A"

        context = f"""
## Company Overview
- Name: {company_name}
- Ticker: {ticker}
- Sector: {sector}
- Industry: {industry}

## Price Data
- Current Price: ${current_price}
- Previous Close: ${prev_close}
- 52-Week High: ${high_52w}
- 52-Week Low: ${low_52w}
- 1-Month Return: {month_return_str}

## Valuation
- P/E Ratio (TTM): {pe}
- Forward P/E: {forward_pe}
- PEG Ratio: {peg}
- Price/Book: {pb}

## Financials
- Revenue Growth (YoY): {revenue_growth}
- Profit Margin: {profit_margin}

## Analyst Consensus
- Mean Target Price: ${target_price}
- Recommendation: {recommendation}
- Number of Analysts: {num_analysts}
"""
        return context

    except Exception as e:
        return f"Failed to fetch financial data: {e}"


# ============================================================
# LLM 调用
# ============================================================

def build_prompt(ticker: str, news_context: str, financial_context: str) -> str:
    """构建 LLM prompt"""
    return f"""You are a professional stock analyst. Analyze the following information and predict the short-term (1-4 weeks) price trend for {ticker}.

## Recent News (Last 7 Days)
{news_context}

## Financial Summary
{financial_context}

## Analysis Task
Based on the information above, provide your analysis in the following JSON format:

```json
{{
  "trend": "bullish" | "bearish" | "neutral",
  "confidence": 0.0 to 1.0,
  "key_factors": [
    "Factor 1 driving your prediction",
    "Factor 2 driving your prediction",
    "Factor 3 driving your prediction"
  ],
  "risks": [
    "Risk 1 that could invalidate your prediction",
    "Risk 2 that could invalidate your prediction"
  ],
  "reasoning": "2-3 sentence summary of your analysis and prediction rationale."
}}
```

Guidelines:
- "bullish" = expect price to increase
- "bearish" = expect price to decrease
- "neutral" = no clear direction
- confidence: 0.0-0.4 = low, 0.4-0.7 = medium, 0.7-1.0 = high
- Focus on actionable insights, not generic statements
- Consider both fundamental and sentiment factors

Respond ONLY with the JSON object, no additional text."""


def call_anthropic(prompt: str, model: str) -> str:
    """调用 Anthropic Claude API"""
    try:
        import anthropic
    except ImportError:
        raise ImportError("Please install anthropic: pip install anthropic")

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY environment variable not set")

    client = anthropic.Anthropic(api_key=api_key)

    message = client.messages.create(
        model=model,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}]
    )

    return message.content[0].text


def call_openai(prompt: str, model: str) -> str:
    """调用 OpenAI API"""
    try:
        from openai import OpenAI
    except ImportError:
        raise ImportError("Please install openai: pip install openai")

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable not set")

    client = OpenAI(api_key=api_key)

    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"}
    )

    return response.choices[0].message.content


def call_openrouter(prompt: str, model: str) -> str:
    """调用 OpenRouter API（多模型网关）"""
    try:
        from openai import OpenAI
    except ImportError:
        raise ImportError("Please install openai: pip install openai")

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY environment variable not set")

    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key
    )

    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}]
    )

    return response.choices[0].message.content


def predict_with_llm(
    ticker: str,
    provider: str = "anthropic",
    model: str | None = None
) -> AIPrediction:
    """
    使用 LLM 进行趋势预测

    Args:
        ticker: 股票代码
        provider: LLM 提供商 ("anthropic", "openai", "openrouter")
        model: 模型名称（可选，使用默认）

    Returns:
        AI 预测结果
    """
    # 默认模型
    default_models = {
        "anthropic": "claude-sonnet-4-20250514",
        "openai": "gpt-4o",
        "openrouter": "anthropic/claude-3.5-sonnet"
    }

    if model is None:
        model = default_models.get(provider, "claude-sonnet-4-20250514")

    # 收集上下文
    print(f"  Fetching news for {ticker}...", file=sys.stderr)
    news_context = get_news_context(ticker)

    print(f"  Fetching financial data...", file=sys.stderr)
    financial_context = get_financial_context(ticker)

    # 构建 prompt
    prompt = build_prompt(ticker, news_context, financial_context)

    # 调用 LLM
    print(f"  Calling {provider} ({model})...", file=sys.stderr)

    if provider == "anthropic":
        response = call_anthropic(prompt, model)
    elif provider == "openai":
        response = call_openai(prompt, model)
    elif provider == "openrouter":
        response = call_openrouter(prompt, model)
    else:
        raise ValueError(f"Unsupported provider: {provider}")

    # 解析响应
    # 提取 JSON（处理可能的 markdown 代码块）
    response = response.strip()
    if response.startswith("```"):
        # 移除代码块标记
        lines = response.split("\n")
        response = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])

    try:
        result = json.loads(response)
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse LLM response as JSON: {e}\nResponse: {response}")

    return AIPrediction(
        ticker=ticker,
        trend=result.get("trend", "neutral"),
        confidence=result.get("confidence", 0.5),
        key_factors=result.get("key_factors", []),
        risks=result.get("risks", []),
        reasoning=result.get("reasoning", ""),
        model=model,
        provider=provider,
        timestamp=datetime.now().isoformat()
    )


# ============================================================
# 输出格式化
# ============================================================

def format_prediction_text(pred: AIPrediction) -> str:
    """格式化为文本"""
    # 趋势图标
    trend_icons = {
        "bullish": "🟢 BULLISH",
        "bearish": "🔴 BEARISH",
        "neutral": "🟡 NEUTRAL"
    }
    trend_display = trend_icons.get(pred.trend, pred.trend.upper())

    # 置信度
    confidence_pct = int(pred.confidence * 100)

    lines = [
        "",
        "╔" + "═" * 62 + "╗",
        f"║{'AI TREND PREDICTION: ' + pred.ticker:^62}║",
        "╠" + "═" * 62 + "╣",
        f"║ Trend:       {trend_display:<48}║",
        f"║ Confidence:  {confidence_pct}%{' ' * 54}║",
        "║                                                              ║",
        "║ KEY FACTORS                                                  ║",
        "║ " + "─" * 60 + " ║",
    ]

    for factor in pred.key_factors[:5]:
        # 截断长因素
        factor_display = factor[:56] + "..." if len(factor) > 56 else factor
        lines.append(f"║ ✅ {factor_display:<57}║")

    lines.extend([
        "║                                                              ║",
        "║ RISKS                                                        ║",
        "║ " + "─" * 60 + " ║",
    ])

    for risk in pred.risks[:3]:
        risk_display = risk[:56] + "..." if len(risk) > 56 else risk
        lines.append(f"║ ⚠️  {risk_display:<56}║")

    lines.extend([
        "║                                                              ║",
        "║ REASONING                                                    ║",
        "║ " + "─" * 60 + " ║",
    ])

    # 分行显示推理
    reasoning = pred.reasoning
    while reasoning:
        line = reasoning[:58]
        reasoning = reasoning[58:]
        lines.append(f"║ {line:<60}║")

    lines.extend([
        "║                                                              ║",
        f"║ Model: {pred.model:<54}║",
        "╚" + "═" * 62 + "╝",
        ""
    ])

    return "\n".join(lines)


def format_prediction_json(pred: AIPrediction) -> str:
    """格式化为 JSON"""
    return json.dumps(asdict(pred), indent=2, ensure_ascii=False)


# ============================================================
# 主入口
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="AI 股票趋势预测")
    parser.add_argument("tickers", nargs="+", help="股票代码")
    parser.add_argument("--provider", choices=["anthropic", "openai", "openrouter"],
                        default="anthropic", help="LLM 提供商")
    parser.add_argument("--model", help="模型名称（可选）")
    parser.add_argument("--output", choices=["text", "json"], default="text")

    args = parser.parse_args()

    results = []

    for ticker in args.tickers:
        ticker = ticker.upper()
        print(f"\n=== AI Prediction for {ticker} ===\n", file=sys.stderr)

        try:
            prediction = predict_with_llm(ticker, args.provider, args.model)
            results.append(prediction)

            if args.output == "text":
                print(format_prediction_text(prediction))
            # JSON 模式最后统一输出

        except Exception as e:
            print(f"Error predicting {ticker}: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()

    # JSON 模式输出
    if args.output == "json" and results:
        if len(results) == 1:
            print(format_prediction_json(results[0]))
        else:
            print(json.dumps([asdict(r) for r in results], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
