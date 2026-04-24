from __future__ import annotations

from html import escape


_TIER_MAP = {
    "BUY": "Bullish",
    "STRONG_BUY": "Bullish",
    "HOLD": "Neutral",
    "SELL": "Bearish",
    "STRONG_SELL": "Bearish",
}


def _format_tier(reco: str | None) -> str | None:
    if not reco:
        return None
    return _TIER_MAP.get(reco.upper(), reco)


def build_email_html(
    *,
    ticker: str,
    score: int | None,
    rating: str | None,
    recommendation: str | None,
    supporting_points: list[str],
    caveats: list[str],
) -> str:
    points_html = "".join(
        f"<li style='margin-bottom:8px'>{escape(point)}</li>" for point in supporting_points[:4]
    )
    caveats_html = "".join(
        f"<li style='margin-bottom:8px'>{escape(point)}</li>" for point in caveats[:4]
    )

    return f"""
    <div style="background:#06110b;padding:32px;font-family:'IBM Plex Mono',Consolas,monospace;color:#d7ffe9">
      <div style="max-width:680px;margin:0 auto;border:1px solid rgba(0,255,136,.18);background:#0a0f0c">
        <div style="padding:24px 28px;border-bottom:1px solid rgba(0,255,136,.14)">
          <div style="font-size:11px;letter-spacing:.22em;color:#6ed4a0;text-transform:uppercase">Sentinel Intelligence Briefing</div>
          <h1 style="margin:12px 0 0;font-size:26px;color:#ffffff">{escape(ticker)} 风险简报已生成</h1>
          <p style="margin:12px 0 0;color:#9cd8b5;font-size:14px;line-height:1.7">
            附件中包含本次分析的 PDF 简报。以下为核心结论摘要。
          </p>
        </div>
        <div style="padding:28px">
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="margin-bottom:22px">
            <tr>
              <td style="width:33%;padding:14px;border:1px solid rgba(0,255,136,.14);background:#050806">
                <div style="font-size:11px;letter-spacing:.18em;text-transform:uppercase;color:#70c89a">Overall Score</div>
                <div style="font-size:28px;color:#fff;margin-top:10px">{score if score is not None else "--"}/100</div>
              </td>
              <td style="width:33%;padding:14px;border:1px solid rgba(0,255,136,.14);background:#050806">
                <div style="font-size:11px;letter-spacing:.18em;text-transform:uppercase;color:#70c89a">Rating</div>
                <div style="font-size:28px;color:#fff;margin-top:10px">{escape(rating or "--")}</div>
              </td>
              <td style="width:33%;padding:14px;border:1px solid rgba(0,255,136,.14);background:#050806">
                <div style="font-size:11px;letter-spacing:.18em;text-transform:uppercase;color:#70c89a">Signal Tier</div>
                <div style="font-size:28px;color:#fff;margin-top:10px">{escape(_format_tier(recommendation) or "--")}</div>
              </td>
            </tr>
          </table>

          <div style="display:block;border:1px solid rgba(0,255,136,.14);background:#050806;padding:18px;margin-bottom:16px">
            <div style="font-size:11px;letter-spacing:.18em;text-transform:uppercase;color:#70c89a;margin-bottom:12px">Bull Case Drivers</div>
            <ul style="margin:0;padding-left:18px;color:#d7ffe9;line-height:1.7">{points_html}</ul>
          </div>

          <div style="display:block;border:1px solid rgba(255,196,0,.18);background:#090705;padding:18px">
            <div style="font-size:11px;letter-spacing:.18em;text-transform:uppercase;color:#d9ba6d;margin-bottom:12px">Risk Notes</div>
            <ul style="margin:0;padding-left:18px;color:#f4e6bf;line-height:1.7">{caveats_html}</ul>
          </div>

          <p style="margin:20px 0 0;font-size:11px;color:#6b8879;line-height:1.6;text-align:center;letter-spacing:.05em">
            Not investment advice · For educational purposes only · Past performance does not guarantee future results
          </p>
        </div>
      </div>
    </div>
    """
