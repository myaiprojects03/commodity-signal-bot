"""
alerts/formatter.py

Builds detailed HTML + plain-text signal reports for email delivery.
Includes: candle patterns, 24h high/low/volume, full indicator suite.
All f-strings replaced with .format() for Python 3.8+ safety.
"""

from datetime import datetime, timezone
from typing import Optional

from analysis.trend import get_trend_label
from utils.helpers import format_price
from utils.logger import get_logger

logger = get_logger(__name__)

_DIVIDER = "━" * 38

_COLORS = {
    "BUY":      "#00b894",
    "SELL":     "#d63031",
    "WATCH":    "#fdcb6e",
    "ELITE":    "#6c5ce7",
    "STRONG":   "#0984e3",
    "MODERATE": "#636e72",
}

_PATTERN_LABELS = {
    "PIN_BAR":        "📍 Pin Bar",
    "SHOOTING_STAR":  "⭐ Shooting Star",
    "BULLISH_ENGULF": "🟢 Bullish Engulfing",
    "BEARISH_ENGULF": "🔴 Bearish Engulfing",
    "DOJI":           "⚪ Doji",
    "INSIDE_BAR":     "📦 Inside Bar",
    "MORNING_STAR":   "🌅 Morning Star",
    "EVENING_STAR":   "🌆 Evening Star",
    "TWEEZER_BOTTOM": "📌 Tweezer Bottom",
    "TWEEZER_TOP":    "📌 Tweezer Top",
    "LIQ_SWEEP_BULL": "⚡ Liquidity Sweep (Bull)",
    "LIQ_SWEEP_BEAR": "⚡ Liquidity Sweep (Bear)",
}


class AlertFormatter:

    def __init__(self, config: dict) -> None:
        self._cfg = config

    # ── Main entry points ─────────────────────────────────────────────────────

    def format_email(
        self,
        instrument: dict,
        current_price: float,
        direction: str,
        scoring_result: dict,
        zone: Optional[dict],
        support_zone: Optional[dict],
        resistance_zone: Optional[dict],
        trend_bias: dict,
        pattern_result: Optional[dict],
        indicators: dict,
        liquidity_result: dict,
        session_result: dict,
        rr_result: dict,
        timeframe: str = "1h",
    ) -> tuple:
        """Returns (subject, plain_text, html_body)."""
        symbol = instrument["symbol"]
        name   = instrument["name"]
        score  = scoring_result.get("score", 0)
        label  = scoring_result.get("label", "MODERATE")
        stype  = scoring_result.get("signal_type", "WATCH")

        subject = self._subject(name, stype, label, score)
        plain   = self._plain(
            instrument, current_price, direction, scoring_result,
            zone, support_zone, resistance_zone, trend_bias,
            pattern_result, indicators, liquidity_result, session_result, rr_result, timeframe
        )
        html    = self._html(
            instrument, current_price, direction, scoring_result,
            zone, support_zone, resistance_zone, trend_bias,
            pattern_result, indicators, liquidity_result, session_result, rr_result, timeframe
        )
        return subject, plain, html

    def format_summary_email(self, run_results: list, run_time: datetime) -> tuple:
        subject = "[Commodity Bot] Report — {}".format(run_time.strftime("%H:%M UTC"))
        plain   = self._summary_plain(run_results, run_time)
        html    = self._summary_html(run_results, run_time)
        return subject, plain, html

    # ── Subject ───────────────────────────────────────────────────────────────

    def _subject(self, name, stype, label, score) -> str:
        emoji = {"BUY": "🟢", "SELL": "🔴", "WATCH": "🟡"}.get(stype, "⚪")
        return "{} [{}] {} — {} Signal ({}/100) | Commodity Signal Bot".format(
            emoji, stype, name, label, score
        )

    # ── Plain Text ────────────────────────────────────────────────────────────

    def _plain(
        self, instrument, price, direction, scoring, zone,
        sup_z, res_z, trend, pattern, indicators, liquidity, session, rr, tf
    ) -> str:
        name   = instrument["name"]
        symbol = instrument["symbol"]
        score  = scoring.get("score", 0)
        label  = scoring.get("label", "")
        stype  = scoring.get("signal_type", "WATCH")
        p      = format_price(price, price)

        lines = [
            _DIVIDER,
            "  {} SIGNAL  |  {} ({})".format(stype, name, symbol),
            _DIVIDER,
            "  Price        : ${}".format(p),
            "  Signal       : {}  [{}]  {}/100".format(stype, label, score),
            "  Timeframe    : {}".format(tf.upper()),
            "  Time (UTC)   : {}".format(datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")),
            "",
        ]

        # Zone
        lines += ["  STRUCTURE", "  " + "─" * 34]
        if zone:
            zl = format_price(zone["zone_low"],  price)
            zh = format_price(zone["zone_high"], price)
            lines += [
                "  Zone Type    : {}".format(zone["type"].upper()),
                "  Zone Range   : ${} – ${}".format(zl, zh),
                "  Touch Count  : {}x".format(zone.get("touch_count", 0)),
                "  Zone Strength: {}".format(self._zone_strength(zone)),
                "  Round Number : {}".format("Yes" if zone.get("round_number") else "No"),
            ]
        else:
            lines.append("  Zone         : No active zone at price")

        # Indicators
        lines += [
            "",
            "  INDICATORS",
            "  " + "─" * 34,
            "  EMA 20       : ${}".format(self._fmt_val(indicators.get("ema20"), ".2f")),
            "  EMA 50       : ${}".format(self._fmt_val(indicators.get("ema50"), ".2f")),
            "  EMA 200      : ${}".format(self._fmt_val(indicators.get("ema200"), ".2f")),
            "  EMA Trend    : {}".format(
                "Bullish ↑" if indicators.get("ema_bullish") else
                "Bearish ↓" if indicators.get("ema_bearish") else "Mixed"
            ),
            "  RSI ({})      : {} {}".format(
                self._cfg["indicators"]["rsi_period"],
                self._fmt_val(indicators.get("rsi"), ".1f"),
                self._rsi_label(indicators)
            ),
            "  MACD         : {}".format(
                "Bullish cross ↑" if indicators.get("macd_bullish_cross") else
                "Bearish cross ↓" if indicators.get("macd_bearish_cross") else "Neutral"
            ),
            "  MACD Hist    : {}".format(self._fmt_val(indicators.get("macd_hist"), ".4f")),
            "  BB Upper     : ${}".format(self._fmt_val(indicators.get("bb_upper"), ".2f")),
            "  BB Lower     : ${}".format(self._fmt_val(indicators.get("bb_lower"), ".2f")),
            "  BB Position  : {}".format(
                "At Lower Band" if indicators.get("price_at_lower") else
                "At Upper Band" if indicators.get("price_at_upper") else "Mid-range"
            ),
            "  BB Squeeze   : {}".format("YES ⚡" if indicators.get("bb_squeeze") else "No"),
            "  Stochastic   : {}  (K={})".format(
                "Oversold" if indicators.get("stoch_oversold") else
                "Overbought" if indicators.get("stoch_overbought") else "Neutral",
                self._fmt_val(indicators.get("stoch_k"), ".1f")
            ),
            "  Volume       : {}".format(self._vol_label(indicators)),
            "  ATR (14)     : ${}".format(format_price(indicators.get("atr"), price)),
        ]

        # Trend
        w  = trend.get("weekly", {})
        d  = trend.get("daily",  {})
        h4 = trend.get("h4",     {})
        lines += [
            "",
            "  TREND ALIGNMENT",
            "  " + "─" * 34,
            "  Weekly       : {}".format(get_trend_label(w.get("direction", "range"))),
            "  Daily        : {}".format(get_trend_label(d.get("direction", "range"))),
            "  4H           : {}".format(get_trend_label(h4.get("direction", "range"))),
            "  Alignment    : {}".format(
                "✅ Aligned" if trend.get("aligned") else
                "⚠️ Partial" if trend.get("partial") else "❌ Counter"
            ),
        ]
        if h4.get("failed_swing"):
            lines.append("  ⚠️  Failed swing on 4H — exhaustion warning")

        # Candle pattern
        p_name    = (pattern.get("pattern", "None") if pattern else "None")
        p_quality = (pattern.get("quality", "N/A")  if pattern else "N/A")
        p_dir     = (pattern.get("direction", "")    if pattern else "")
        p_label   = _PATTERN_LABELS.get(p_name, p_name.replace("_", " ").title())
        lines += [
            "",
            "  CANDLE PATTERN",
            "  " + "─" * 34,
            "  Pattern      : {}".format(p_label if p_name != "None" else "None"),
            "  Quality      : {}".format(p_quality.title()),
            "  Direction    : {}".format(p_dir.upper() if p_dir else "N/A"),
        ]

        # Liquidity sweep
        if liquidity.get("sweep_detected"):
            lines += [
                "",
                "  ⚡ LIQUIDITY SWEEP DETECTED",
                "  Sweep Level  : ${}".format(format_price(liquidity.get("sweep_level", 0), price)),
                "  Direction    : {}".format((liquidity.get("sweep_direction") or "").upper()),
            ]

        # Session + R:R
        entry = rr.get("entry", price)
        sl    = rr.get("stop_loss")
        tp1   = rr.get("tp1")
        tp2   = rr.get("tp2")
        tp3   = rr.get("tp3")

        lines += [
            "",
            "  SESSION",
            "  " + "─" * 34,
            "  Session      : {}".format(session.get("session", "Unknown").replace("_", " ").title()),
            "  Session Adj  : {}{}pts".format(
                "+" if session.get("score_adjustment", 0) >= 0 else "",
                session.get("score_adjustment", 0)
            ),
            "",
            "  RISK / REWARD",
            "  " + "─" * 34,
            "  Entry        : ${}".format(format_price(entry, price)),
            "  Stop Loss    : ${}".format(format_price(sl, price) if sl else "N/A"),
            "  TP1          : ${}".format(format_price(tp1, price) if tp1 else "N/A"),
            "  TP2          : ${}".format(format_price(tp2, price) if tp2 else "N/A"),
            "  TP3          : ${}".format(format_price(tp3, price) if tp3 else "N/A"),
            "  R:R Ratio    : {:.1f}:1  ({})".format(rr.get("rr_ratio", 0), rr.get("rr_quality", "N/A")),
        ]

        lines += [
            "",
            _DIVIDER,
            "  CONFIDENCE   : {}/100  [{}]".format(score, label),
            "  SIGNAL       : {}".format(stype),
            "",
            "  ⚠️ Analysis only — not financial advice.",
            _DIVIDER,
        ]
        return "\n".join(lines)

    # ── HTML Signal Email ─────────────────────────────────────────────────────

    def _html(
        self, instrument, price, direction, scoring, zone,
        sup_z, res_z, trend, pattern, indicators, liquidity, session, rr, tf
    ) -> str:
        name   = instrument["name"]
        symbol = instrument["symbol"]
        score  = scoring.get("score", 0)
        label  = scoring.get("label", "MODERATE")
        stype  = scoring.get("signal_type", "WATCH")

        sig_color   = _COLORS.get(stype, "#636e72")
        label_color = _COLORS.get(label, "#636e72")
        p = format_price(price, price)

        entry = rr.get("entry", price)
        sl    = rr.get("stop_loss")
        tp1   = rr.get("tp1")
        tp2   = rr.get("tp2")
        tp3   = rr.get("tp3")

        w  = trend.get("weekly", {})
        d  = trend.get("daily",  {})
        h4 = trend.get("h4",    {})

        te = lambda dir_: "🟢" if dir_ == "uptrend" else "🔴" if dir_ == "downtrend" else "🟡"

        align_label = (
            "✅ Fully Aligned" if trend.get("aligned")
            else "⚠️ Partial (2/3)" if trend.get("partial")
            else "❌ Counter-Trend"
        )

        if direction == "buy" and sl:
            entry_advice = (
                "<b>📌 Entry Advice:</b> Consider entering between "
                "<b>${}</b> and <b>${}</b> "
                "to avoid being stopped out early. Wait for price to come to the zone.".format(
                    format_price(sl, price), format_price(entry, price)
                )
            )
        elif sl:
            entry_advice = (
                "<b>📌 Entry Advice:</b> Consider entering between "
                "<b>${}</b> and <b>${}</b> "
                "to avoid being stopped out early. Wait for price to reject the zone.".format(
                    format_price(entry, price), format_price(sl, price)
                )
            )
        else:
            entry_advice = "<b>📌 Entry Advice:</b> Use current price as entry reference."

        # Zone block
        if zone:
            zl = format_price(zone["zone_low"],  price)
            zh = format_price(zone["zone_high"], price)
            zone_html = """
            <tr><td><b>Zone Range</b></td><td>${} – ${}</td></tr>
            <tr><td><b>Zone Type</b></td><td>{}</td></tr>
            <tr><td><b>Touches</b></td><td>{}x &nbsp;({})</td></tr>
            <tr><td><b>Round Number</b></td><td>{}</td></tr>
            <tr><td><b>Daily Confluence</b></td><td>{}</td></tr>
            <tr><td><b>Weekly Confluence</b></td><td>{}</td></tr>
            """.format(
                zl, zh,
                zone["type"].upper(),
                zone.get("touch_count", 0), self._zone_strength(zone),
                "✅ Yes" if zone.get("round_number") else "❌ No",
                "✅ Yes" if zone.get("daily_confluence") else "❌ No",
                "✅ Yes" if zone.get("weekly_confluence") else "❌ No",
            )
        else:
            zone_html = "<tr><td colspan='2'>No active zone at current price</td></tr>"

        # Sweep block
        sweep_html = ""
        if liquidity.get("sweep_detected"):
            sweep_html = """
            <tr style="background:#fff3cd;">
              <td><b>⚡ Liquidity Sweep</b></td>
              <td>Detected at ${} ({})</td>
            </tr>""".format(
                format_price(liquidity.get("sweep_level", 0), price),
                (liquidity.get("sweep_direction") or "").upper()
            )

        # Candle pattern block
        p_name    = pattern.get("pattern", "None") if pattern else "None"
        p_quality = pattern.get("quality", "N/A")  if pattern else "N/A"
        p_dir     = pattern.get("direction", "")    if pattern else ""
        p_score   = pattern.get("score", 0)         if pattern else 0
        p_label   = _PATTERN_LABELS.get(p_name, p_name.replace("_", " ").title())
        pattern_color = (
            "#e8f8f5" if p_dir == "buy" else
            "#fdf0f0" if p_dir == "sell" else "#f4f6f8"
        )

        # Failed swing warning
        failed_swing_html = ""
        if h4.get("failed_swing"):
            failed_swing_html = "<tr style='background:#fff3cd;'><td><b>⚠️ Warning</b></td><td>Failed swing on 4H — trend showing exhaustion</td></tr>"

        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        stype_emoji = "🟢" if stype == "BUY" else "🔴" if stype == "SELL" else "🟡"

        html = """<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
  body {{ font-family: Arial, sans-serif; background: #f4f6f8; margin: 0; padding: 20px; }}
  .card {{ background: #fff; border-radius: 10px; max-width: 620px; margin: auto;
           box-shadow: 0 2px 8px rgba(0,0,0,0.12); overflow: hidden; }}
  .header {{ background: {sig_color}; color: white; padding: 20px 24px; }}
  .header h1 {{ margin: 0; font-size: 22px; }}
  .header .sub {{ margin: 4px 0 0; opacity: 0.85; font-size: 14px; }}
  .badge {{ display: inline-block; background: {label_color}; color: white;
            padding: 3px 10px; border-radius: 12px; font-size: 13px; font-weight: bold; }}
  .score-bar {{ background: #eee; border-radius: 20px; height: 10px; margin: 8px 0; }}
  .score-fill {{ background: {sig_color}; height: 10px; border-radius: 20px; width: {score}%; }}
  .section {{ padding: 16px 24px; border-bottom: 1px solid #eee; }}
  .section h3 {{ margin: 0 0 10px; color: #2d3436; font-size: 14px; text-transform: uppercase; letter-spacing: 1px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
  td {{ padding: 5px 4px; color: #333; }}
  td:first-child {{ color: #666; width: 40%; }}
  .rr-box {{ background: #f8f9fa; border-left: 4px solid {sig_color}; padding: 12px 16px; border-radius: 4px; margin-top: 8px; }}
  .entry-advice {{ background: #e8f4fd; border-left: 4px solid #0984e3; padding: 12px 16px; border-radius: 4px; font-size: 14px; }}
  .risk-note {{ background: #fff8e1; border-left: 4px solid #fdcb6e; padding: 12px 16px; border-radius: 4px; font-size: 13px; color: #555; }}
  .footer {{ padding: 14px 24px; font-size: 12px; color: #888; text-align: center; }}
</style>
</head>
<body>
<div class="card">

  <div class="header">
    <h1>{stype_emoji} {stype} — {name} ({symbol})</h1>
    <p class="sub">
      <span class="badge">{label}</span>&nbsp;&nbsp;
      {score}/100 confidence &nbsp;|&nbsp; {tf_upper} &nbsp;|&nbsp; {now_str}
    </p>
    <div class="score-bar"><div class="score-fill"></div></div>
  </div>

  <div class="section">
    <h3>💰 Price &amp; Zone</h3>
    <table>
      <tr><td><b>Current Price</b></td><td><b>${p}</b></td></tr>
      {zone_html}
    </table>
  </div>

  <div class="section">
    <h3>📊 Technical Indicators</h3>
    <table>
      <tr><td><b>EMA 20</b></td><td>${ema20}</td></tr>
      <tr><td><b>EMA 50</b></td><td>${ema50}</td></tr>
      <tr><td><b>EMA 200</b></td><td>${ema200}</td></tr>
      <tr><td><b>EMA Trend</b></td><td>{ema_trend}</td></tr>
      <tr><td><b>Price vs EMA 200</b></td><td>{ema200_pos}</td></tr>
      <tr><td><b>RSI ({rsi_period})</b></td><td>{rsi_val} — {rsi_label}</td></tr>
      <tr><td><b>MACD Line</b></td><td>{macd_val}</td></tr>
      <tr><td><b>MACD Histogram</b></td><td>{macd_hist}</td></tr>
      <tr><td><b>MACD Signal</b></td><td>{macd_cross}</td></tr>
      <tr><td><b>Bollinger Upper</b></td><td>${bb_upper}</td></tr>
      <tr><td><b>Bollinger Lower</b></td><td>${bb_lower}</td></tr>
      <tr><td><b>BB Position</b></td><td>{bb_pos}</td></tr>
      <tr><td><b>BB Squeeze</b></td><td>{bb_squeeze}</td></tr>
      <tr><td><b>Stochastic K</b></td><td>{stoch_val} — {stoch_label}</td></tr>
      <tr><td><b>Volume</b></td><td>{vol_label}</td></tr>
      <tr><td><b>ATR (14)</b></td><td>${atr}</td></tr>
      {sweep_html}
    </table>
  </div>

  <div class="section">
    <h3>🕯️ Candle Pattern (1H)</h3>
    <table>
      <tr style="background:{pattern_color};">
        <td><b>Pattern</b></td>
        <td><b>{p_label}</b></td>
      </tr>
      <tr><td><b>Quality</b></td><td>{p_quality}</td></tr>
      <tr><td><b>Direction</b></td><td>{p_dir_upper}</td></tr>
      <tr><td><b>Pattern Score</b></td><td>+{p_score} pts</td></tr>
    </table>
  </div>

  <div class="section">
    <h3>📈 Trend Alignment</h3>
    <table>
      <tr><td><b>Weekly</b></td><td>{te_w} {w_label}</td></tr>
      <tr><td><b>Daily</b></td><td>{te_d} {d_label}</td></tr>
      <tr><td><b>4H</b></td><td>{te_h4} {h4_label}</td></tr>
      <tr><td><b>Overall Bias</b></td><td>{align_label}</td></tr>
      {failed_swing_html}
    </table>
  </div>

  <div class="section">
    <h3>⚖️ Risk / Reward</h3>
    <div class="rr-box">
      <table>
        <tr><td><b>Entry</b></td><td><b>${entry}</b></td></tr>
        <tr><td><b>Stop Loss</b></td><td style="color:#d63031;"><b>${sl_disp}</b></td></tr>
        <tr><td><b>TP1</b></td><td style="color:#00b894;">${tp1_disp}</td></tr>
        <tr><td><b>TP2</b></td><td style="color:#00b894;">${tp2_disp}</td></tr>
        <tr><td><b>TP3</b></td><td style="color:#00b894;">${tp3_disp}</td></tr>
        <tr><td><b>R:R Ratio</b></td><td><b>{rr_ratio:.1f}:1</b> ({rr_quality})</td></tr>
        <tr><td><b>Session</b></td><td>{session_name}</td></tr>
        <tr><td><b>Session Score Adj</b></td><td>{session_adj} pts</td></tr>
      </table>
    </div>
    <br>
    <div class="entry-advice">{entry_advice}</div>
  </div>

  <div class="section">
    <div class="risk-note">
      <b>⚠️ Risk Note:</b> {risk_note}
    </div>
  </div>

  <div class="footer">
    This is analysis only, not financial advice. Always manage your own risk.<br>
    Commodity Signal Bot — {now_str}
  </div>
</div>
</body>
</html>""".format(
            sig_color   = sig_color,
            label_color = label_color,
            score       = score,
            stype_emoji = stype_emoji,
            stype       = stype,
            name        = name,
            symbol      = symbol,
            label       = label,
            tf_upper    = tf.upper(),
            now_str     = now_str,
            p           = p,
            zone_html   = zone_html,
            ema20       = self._fmt_val(indicators.get("ema20"),  ".2f"),
            ema50       = self._fmt_val(indicators.get("ema50"),  ".2f"),
            ema200      = self._fmt_val(indicators.get("ema200"), ".2f"),
            ema_trend   = ("🟢 Bullish ↑" if indicators.get("ema_bullish") else
                           "🔴 Bearish ↓" if indicators.get("ema_bearish") else "🟡 Mixed"),
            ema200_pos  = ("above 200 EMA ✅" if indicators.get("ema_above_200") else "below 200 EMA ⚠️"),
            rsi_period  = self._cfg["indicators"]["rsi_period"],
            rsi_val     = self._fmt_val(indicators.get("rsi"), ".1f"),
            rsi_label   = self._rsi_label(indicators),
            macd_val    = self._fmt_val(indicators.get("macd"),      ".4f"),
            macd_hist   = self._fmt_val(indicators.get("macd_hist"), ".4f"),
            macd_cross  = ("🟢 Bullish Cross ↑" if indicators.get("macd_bullish_cross") else
                           "🔴 Bearish Cross ↓" if indicators.get("macd_bearish_cross") else "⚪ Neutral"),
            bb_upper    = self._fmt_val(indicators.get("bb_upper"), ".2f"),
            bb_lower    = self._fmt_val(indicators.get("bb_lower"), ".2f"),
            bb_pos      = ("At Lower Band 🟢" if indicators.get("price_at_lower") else
                           "At Upper Band 🔴" if indicators.get("price_at_upper") else "Mid-range ⚪"),
            bb_squeeze  = ("YES ⚡ — Breakout Imminent" if indicators.get("bb_squeeze") else "No"),
            stoch_val   = self._fmt_val(indicators.get("stoch_k"), ".1f"),
            stoch_label = ("Oversold 🟢" if indicators.get("stoch_oversold") else
                           "Overbought 🔴" if indicators.get("stoch_overbought") else "Neutral ⚪"),
            vol_label   = self._vol_label(indicators),
            atr         = format_price(indicators.get("atr"), price),
            sweep_html  = sweep_html,
            pattern_color = pattern_color,
            p_label     = p_label if p_name != "None" else "None detected",
            p_quality   = p_quality.title(),
            p_dir_upper = p_dir.upper() if p_dir else "N/A",
            p_score     = p_score,
            te_w        = te(w.get("direction", "range")),
            w_label     = get_trend_label(w.get("direction", "range")),
            te_d        = te(d.get("direction", "range")),
            d_label     = get_trend_label(d.get("direction", "range")),
            te_h4       = te(h4.get("direction", "range")),
            h4_label    = get_trend_label(h4.get("direction", "range")),
            align_label = align_label,
            failed_swing_html = failed_swing_html,
            entry       = format_price(entry, price),
            sl_disp     = format_price(sl,  price) if sl  else "N/A",
            tp1_disp    = format_price(tp1, price) if tp1 else "N/A",
            tp2_disp    = format_price(tp2, price) if tp2 else "N/A",
            tp3_disp    = format_price(tp3, price) if tp3 else "N/A",
            rr_ratio    = rr.get("rr_ratio", 0),
            rr_quality  = rr.get("rr_quality", "N/A"),
            session_name = session.get("session", "Unknown").replace("_", " ").title(),
            session_adj = ("+" if session.get("score_adjustment", 0) >= 0 else "") + str(session.get("score_adjustment", 0)),
            entry_advice = entry_advice,
            risk_note   = self._risk_note(stype, rr, indicators, liquidity, trend, zone),
        )
        return html

    # ── Summary Email (30-min status) ─────────────────────────────────────────

    def _summary_plain(self, results: list, run_time: datetime) -> str:
        lines = [
            _DIVIDER,
            "  COMMODITY SIGNAL BOT — REPORT",
            "  {}".format(run_time.strftime("%Y-%m-%d %H:%M UTC")),
            _DIVIDER,
            "",
        ]

        for r in results:
            name    = r.get("name", "")
            symbol  = r.get("symbol", "")
            price   = r.get("price", 0)
            w_dir   = r.get("weekly_trend", "range")
            d_dir   = r.get("daily_trend",  "range")
            h4_dir  = r.get("h4_trend",     "range")
            zone    = r.get("zone")
            sup_z   = r.get("sup_zone")
            res_z   = r.get("res_zone")
            signal  = r.get("signal_sent")
            direct  = r.get("direction")
            atr     = r.get("atr")
            rsi     = r.get("rsi")
            session = r.get("session", "unknown").replace("_", " ").title()
            ticker  = r.get("ticker_24h", {})
            pattern = r.get("pattern")
            p       = format_price(price, price)

            lines += [
                "  {}".format("─" * 36),
                "  {} ({})".format(name, symbol),
                "  {}".format("─" * 36),
                "  Price        : ${}".format(p),
            ]

            # 24h stats
            if ticker:
                lines += [
                    "  24h High     : ${}".format(format_price(ticker.get("high_24h", 0), price)),
                    "  24h Low      : ${}".format(format_price(ticker.get("low_24h",  0), price)),
                    "  24h Change   : {} ({:.2f}%)".format(
                        "{:+.2f}".format(ticker.get("price_change_24h", 0)),
                        ticker.get("price_change_pct_24h", 0)
                    ),
                    "  24h Volume   : {:.0f} contracts".format(ticker.get("volume_24h", 0)),
                ]
            if atr:
                lines.append("  ATR (14)     : ${}".format(format_price(atr, price)))
            if rsi is not None:
                lines.append("  RSI (14)     : {:.1f}".format(rsi))

            # Pattern
            if pattern:
                p_name  = pattern.get("pattern", "None")
                p_label = _PATTERN_LABELS.get(p_name, p_name.replace("_", " ").title())
                p_qual  = pattern.get("quality", "N/A").title()
                lines.append("  Pattern      : {} [{}]".format(p_label, p_qual))
            else:
                lines.append("  Pattern      : None")

            lines += [
                "  Session      : {}".format(session),
                "",
                "  TREND",
                "  Weekly : {}".format(get_trend_label(w_dir)),
                "  Daily  : {}".format(get_trend_label(d_dir)),
                "  4H     : {}".format(get_trend_label(h4_dir)),
                "",
            ]

            # Zone info
            if zone:
                zl = format_price(zone["zone_low"],  price)
                zh = format_price(zone["zone_high"], price)
                lines += [
                    "  ACTIVE ZONE  : {}".format(zone["type"].upper()),
                    "  Zone Range   : ${} – ${}".format(zl, zh),
                    "  Touches      : {}x".format(zone.get("touch_count", 0)),
                ]
            else:
                if sup_z:
                    sl_lo = format_price(sup_z["zone_low"],  price)
                    sl_hi = format_price(sup_z["zone_high"], price)
                    dist  = abs(price - sup_z["zone_high"]) / price * 100
                    lines.append("  Nearest Sup  : ${} – ${}  ({:.1f}% below)".format(sl_lo, sl_hi, dist))
                if res_z:
                    rl = format_price(res_z["zone_low"],  price)
                    rh = format_price(res_z["zone_high"], price)
                    dist = abs(res_z["zone_low"] - price) / price * 100
                    lines.append("  Nearest Res  : ${} – ${}  ({:.1f}% above)".format(rl, rh, dist))

            lines.append("")

            if signal:
                lines += ["  ✅ SIGNAL     : {}".format(signal),
                          "  VERDICT      : See signal email for full trade setup."]
            elif direct == "buy" and zone:
                lines.append("  🟡 VERDICT    : Near support — wait for candle confirmation before buying.")
            elif direct == "sell" and zone:
                lines.append("  🔴 VERDICT    : Near resistance — DO NOT BUY here. Wait for pullback to support.")
            else:
                if sup_z and res_z:
                    lines.append("  ⚪ VERDICT    : Price mid-range between zones — NO TRADE. Wait for price to reach a zone.")
                else:
                    lines.append("  ⚪ VERDICT    : Insufficient zone data. HOLD / NO TRADE.")

            lines.append("")

        lines += [_DIVIDER, "  Analysis only — not financial advice.", _DIVIDER]
        return "\n".join(lines)

    def _summary_html(self, results: list, run_time: datetime) -> str:
        cards = ""
        for r in results:
            name    = r.get("name", "")
            symbol  = r.get("symbol", "")
            price   = r.get("price", 0)
            w_dir   = r.get("weekly_trend", "range")
            d_dir   = r.get("daily_trend",  "range")
            h4_dir  = r.get("h4_trend",     "range")
            zone    = r.get("zone")
            sup_z   = r.get("sup_zone")
            res_z   = r.get("res_zone")
            signal  = r.get("signal_sent")
            direct  = r.get("direction")
            atr     = r.get("atr")
            rsi     = r.get("rsi")
            macd    = r.get("macd")
            macd_h  = r.get("macd_hist")
            ema20   = r.get("ema20")
            ema50   = r.get("ema50")
            ema200  = r.get("ema200")
            stoch_k = r.get("stoch_k")
            vol_r   = r.get("vol_ratio")
            session = r.get("session", "unknown").replace("_", " ").title()
            ticker  = r.get("ticker_24h", {})
            pattern = r.get("pattern")
            p       = format_price(price, price)

            te = lambda d_: "🟢" if d_ == "uptrend" else "🔴" if d_ == "downtrend" else "🟡"

            # 24h ticker rows
            ticker_rows = ""
            if ticker and ticker.get("high_24h"):
                chg_color = "#00b894" if ticker.get("price_change_pct_24h", 0) >= 0 else "#d63031"
                chg_sign  = "+" if ticker.get("price_change_24h", 0) >= 0 else ""
                ticker_rows = """
                <tr style="background:#f0f4ff;">
                  <td colspan="2" style="padding:6px 4px 2px;font-size:12px;color:#888;font-weight:bold;text-transform:uppercase;letter-spacing:0.5px;">24-Hour Statistics</td>
                </tr>
                <tr><td><b>24h High</b></td><td style="color:#00b894;font-weight:bold;">${high}</td></tr>
                <tr><td><b>24h Low</b></td><td style="color:#d63031;font-weight:bold;">${low}</td></tr>
                <tr><td><b>24h Change</b></td><td style="color:{chg_color};font-weight:bold;">{chg_sign}{chg:.2f} ({pct:.2f}%)</td></tr>
                <tr><td><b>24h Volume</b></td><td>{vol:.0f} contracts</td></tr>
                <tr><td><b>VWAP</b></td><td>${vwap}</td></tr>
                """.format(
                    high     = format_price(ticker.get("high_24h", 0), price),
                    low      = format_price(ticker.get("low_24h",  0), price),
                    chg_color = chg_color,
                    chg_sign = chg_sign,
                    chg      = ticker.get("price_change_24h", 0),
                    pct      = ticker.get("price_change_pct_24h", 0),
                    vol      = ticker.get("volume_24h", 0),
                    vwap     = format_price(ticker.get("weighted_avg_price", 0), price),
                )

            # Indicator rows
            atr_row    = "<tr><td><b>ATR (14)</b></td><td>${}</td></tr>".format(format_price(atr, price)) if atr else ""
            rsi_row    = "<tr><td><b>RSI (14)</b></td><td>{:.1f}</td></tr>".format(rsi) if rsi is not None else ""
            ema_rows   = ""
            if ema20 or ema50 or ema200:
                ema_rows = """
                <tr><td><b>EMA 20</b></td><td>${}</td></tr>
                <tr><td><b>EMA 50</b></td><td>${}</td></tr>
                <tr><td><b>EMA 200</b></td><td>${}</td></tr>
                """.format(
                    self._fmt_val(ema20,  ".2f"),
                    self._fmt_val(ema50,  ".2f"),
                    self._fmt_val(ema200, ".2f"),
                )
            macd_row   = "<tr><td><b>MACD / Hist</b></td><td>{} / {}</td></tr>".format(
                self._fmt_val(macd, ".4f"), self._fmt_val(macd_h, ".4f")
            ) if macd is not None else ""
            stoch_row  = "<tr><td><b>Stoch K</b></td><td>{:.1f}</td></tr>".format(stoch_k) if stoch_k is not None else ""
            vol_row    = "<tr><td><b>Volume Ratio</b></td><td>{:.2f}x avg</td></tr>".format(vol_r) if vol_r is not None else ""

            # Pattern row
            pattern_row = ""
            if pattern:
                p_name  = pattern.get("pattern", "None")
                p_label = _PATTERN_LABELS.get(p_name, p_name.replace("_", " ").title())
                p_qual  = pattern.get("quality", "N/A").title()
                p_dir_  = pattern.get("direction", "")
                pat_bg  = "#e8f8f5" if p_dir_ == "buy" else "#fdf0f0" if p_dir_ == "sell" else "#f4f6f8"
                pattern_row = """<tr style="background:{bg};"><td><b>Pattern (1H)</b></td><td><b>{lbl}</b> [{qual}]</td></tr>""".format(
                    bg=pat_bg, lbl=p_label, qual=p_qual
                )

            # Zone rows
            zone_html = ""
            if zone:
                zl = format_price(zone["zone_low"],  price)
                zh = format_price(zone["zone_high"], price)
                zt = zone["type"].upper()
                bg = "#e8f8f5" if zone["type"] == "support" else "#fdf0f0"
                zone_html = """
                <tr style="background:{bg};">
                  <td><b>Active Zone ({zt})</b></td>
                  <td><b>${zl} – ${zh}</b> &nbsp; ({tc}x touches)</td>
                </tr>""".format(bg=bg, zt=zt, zl=zl, zh=zh, tc=zone.get("touch_count", 0))
            else:
                if sup_z:
                    sl_lo = format_price(sup_z["zone_low"],  price)
                    sl_hi = format_price(sup_z["zone_high"], price)
                    dist  = abs(price - sup_z["zone_high"]) / price * 100
                    zone_html += "<tr><td><b>Nearest Support</b></td><td>${} – ${} &nbsp;<span style='color:#888;'>({:.1f}% below)</span></td></tr>".format(sl_lo, sl_hi, dist)
                if res_z:
                    rl = format_price(res_z["zone_low"],  price)
                    rh = format_price(res_z["zone_high"], price)
                    dist = abs(res_z["zone_low"] - price) / price * 100
                    zone_html += "<tr><td><b>Nearest Resistance</b></td><td>${} – ${} &nbsp;<span style='color:#888;'>({:.1f}% above)</span></td></tr>".format(rl, rh, dist)

            # Verdict
            if signal:
                verdict_bg    = "#e8f8f5"
                verdict_color = "#00b894"
                verdict_text  = "✅ SIGNAL FIRED: {} — check signal email for full trade setup.".format(signal)
            elif direct == "buy" and zone:
                verdict_bg    = "#fff8e1"
                verdict_color = "#e17055"
                verdict_text  = "🟡 Near support zone — WAIT for candle confirmation before buying."
            elif direct == "sell" and zone:
                verdict_bg    = "#fdf0f0"
                verdict_color = "#d63031"
                verdict_text  = "🔴 Near resistance — DO NOT BUY. Wait for pullback to support zone."
            else:
                verdict_bg    = "#f4f6f8"
                verdict_color = "#636e72"
                verdict_text  = "⚪ Price mid-range between zones — NO TRADE. Wait for price to reach a zone."

            cards += """
            <div style="background:#fff;border-radius:10px;margin-bottom:20px;
                        box-shadow:0 2px 8px rgba(0,0,0,0.1);overflow:hidden;">
              <div style="background:#2d3436;color:white;padding:14px 20px;">
                <span style="font-size:17px;font-weight:bold;">{name}</span>
                <span style="opacity:0.6;font-size:13px;margin-left:8px;">({symbol})</span>
                <span style="float:right;font-size:20px;font-weight:bold;">${p}</span>
              </div>

              <div style="padding:14px 20px;">
                <table style="width:100%;border-collapse:collapse;font-size:14px;">
                  <tr><td style="color:#666;width:40%;padding:4px 0;"><b>Session</b></td><td>{session}</td></tr>
                  {ticker_rows}
                  {atr_row}
                  {rsi_row}
                  {ema_rows}
                  {macd_row}
                  {stoch_row}
                  {vol_row}
                  {pattern_row}
                  <tr style="background:#f0f4ff;"><td colspan="2" style="padding:6px 4px 2px;font-size:12px;color:#888;font-weight:bold;text-transform:uppercase;letter-spacing:0.5px;">Trend</td></tr>
                  <tr><td style="color:#666;padding:4px 0;"><b>Weekly</b></td><td>{te_w} {w_lbl}</td></tr>
                  <tr><td style="color:#666;padding:4px 0;"><b>Daily</b></td><td>{te_d} {d_lbl}</td></tr>
                  <tr><td style="color:#666;padding:4px 0;"><b>4H</b></td><td>{te_h4} {h4_lbl}</td></tr>
                  {zone_html}
                </table>
              </div>

              <div style="background:{verdict_bg};border-left:4px solid {verdict_color};
                          padding:12px 20px;font-size:14px;font-weight:bold;color:{verdict_color};">
                {verdict_text}
              </div>
            </div>""".format(
                name        = name,
                symbol      = symbol,
                p           = p,
                session     = session,
                ticker_rows = ticker_rows,
                atr_row     = atr_row,
                rsi_row     = rsi_row,
                ema_rows    = ema_rows,
                macd_row    = macd_row,
                stoch_row   = stoch_row,
                vol_row     = vol_row,
                pattern_row = pattern_row,
                te_w        = te(w_dir),
                w_lbl       = get_trend_label(w_dir),
                te_d        = te(d_dir),
                d_lbl       = get_trend_label(d_dir),
                te_h4       = te(h4_dir),
                h4_lbl      = get_trend_label(h4_dir),
                zone_html   = zone_html,
                verdict_bg  = verdict_bg,
                verdict_color = verdict_color,
                verdict_text  = verdict_text,
            )

        return """<!DOCTYPE html>
<html><head><meta charset="UTF-8"></head>
<body style="font-family:Arial,sans-serif;background:#f4f6f8;padding:20px;margin:0;">
  <div style="max-width:640px;margin:auto;">
    <div style="background:#1e272e;color:white;padding:18px 24px;border-radius:10px 10px 0 0;">
      <h1 style="margin:0;font-size:20px;">📊 Commodity Signal Bot — Report</h1>
      <p style="margin:6px 0 0;opacity:0.7;font-size:13px;">{run_time}</p>
    </div>
    {cards}
    <div style="text-align:center;font-size:12px;color:#999;padding:10px;">
      Analysis only — not financial advice. Next run in ~30 minutes.
    </div>
  </div>
</body></html>""".format(
            run_time = run_time.strftime("%Y-%m-%d %H:%M UTC"),
            cards    = cards,
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _zone_strength(self, zone: dict) -> str:
        if zone.get("weekly_confluence"): return "Very Strong (Weekly)"
        if zone.get("daily_confluence"):  return "Strong (Daily)"
        if zone.get("high_volume_node"):  return "Strong (Vol Node)"
        if zone.get("round_number"):      return "Moderate (Round#)"
        tc = zone.get("touch_count", 0)
        if tc >= 3: return "Moderate"
        return "Standard"

    def _rsi_label(self, ind: dict) -> str:
        if ind.get("rsi_strong_os"):    return "🟢 STRONGLY OVERSOLD"
        if ind.get("rsi_oversold"):     return "🟢 Oversold"
        if ind.get("rsi_turning_up"):   return "🟢 Turning Up"
        if ind.get("rsi_bull_div"):     return "🟢 Bullish Divergence"
        if ind.get("rsi_strong_ob"):    return "🔴 STRONGLY OVERBOUGHT"
        if ind.get("rsi_overbought"):   return "🔴 Overbought"
        if ind.get("rsi_turning_down"): return "🔴 Turning Down"
        if ind.get("rsi_bear_div"):     return "🔴 Bearish Divergence"
        return "⚪ Neutral"

    def _vol_label(self, ind: dict) -> str:
        ratio = ind.get("vol_ratio") or 1.0
        if ind.get("climax_vol"):  return "⚡ CLIMAX ({:.1f}x avg)".format(ratio)
        if ind.get("high_volume"): return "🟢 High ({:.1f}x avg)".format(ratio)
        if ind.get("low_volume"):  return "🔴 Low ({:.1f}x avg)".format(ratio)
        return "⚪ Normal ({:.1f}x avg)".format(ratio)

    def _fmt_val(self, val, fmt: str = ".2f") -> str:
        if val is None: return "N/A"
        try:
            import math
            if math.isnan(val): return "N/A"
            return format(val, fmt)
        except Exception:
            return "N/A"

    def _risk_note(self, stype, rr, indicators, liquidity, trend, zone) -> str:
        notes = []
        sl = rr.get("stop_loss")
        if sl:
            notes.append("Hard stop loss at ${} — respect it.".format(
                format_price(sl, rr.get("entry", sl))
            ))
        if rr.get("rr_quality") == "CAUTION":
            notes.append("R:R below 2:1 — reduce position size.")
        if indicators.get("climax_vol"):
            notes.append("Climax volume present — be ready for sharp reversal.")
        if liquidity.get("sweep_detected"):
            notes.append("Liquidity sweep confirmed — high-conviction reversal setup.")
        if not trend.get("aligned") and trend.get("partial"):
            notes.append("Not fully aligned across timeframes — use tighter targets.")
        if zone and zone.get("touch_count", 0) == 4:
            notes.append("4th zone test — breakout probability rising, use tight SL.")
        if stype == "WATCH":
            notes.append("Signal is WATCH grade — await additional confirmation before entering.")
        if not notes:
            notes.append("Standard setup — follow your normal position sizing rules.")
        return " | ".join(notes)
