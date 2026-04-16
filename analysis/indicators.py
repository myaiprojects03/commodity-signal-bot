"""
analysis/indicators.py

Computes all technical indicators from a candle list.
Returns a single IndicatorBundle dict used by the confidence scorer.

Indicators used (chosen for commodity trading accuracy):
  - EMA 20 / 50 / 200     → trend direction & dynamic S/R
  - RSI (14)              → momentum overbought/oversold (75/25 thresholds for commodities)
  - MACD (12/26/9)        → momentum confirmation & crossovers
  - Bollinger Bands (20,2) → volatility & squeeze detection
  - Stochastic (14,3)     → short-term reversal confirmation
  - ATR (14)              → volatility & SL sizing
  - Volume analysis       → confirms move strength
"""

import math
from typing import List

from utils.helpers import (
    calculate_atr,
    calculate_bollinger_bands,
    calculate_ema,
    calculate_macd,
    calculate_rsi,
    calculate_stochastic,
)
from utils.logger import get_logger

logger = get_logger(__name__)


def compute_indicators(candles: List[dict], config: dict) -> dict:
    """
    Compute all technical indicators from a list of candles.
    
    Parameters
    ----------
    candles : list of dicts with keys: open, high, low, close, volume
    config  : full config dict

    Returns
    -------
    dict — IndicatorBundle
    """
    if len(candles) < 30:
        return _empty_bundle()

    cfg = config["indicators"]
    closes = [c["close"] for c in candles]
    highs  = [c["high"]  for c in candles]
    lows   = [c["low"]   for c in candles]
    vols   = [c["volume"] for c in candles]

    # ── EMAs ──────────────────────────────────────────────
    ema20  = calculate_ema(closes, cfg["ema_fast"])
    ema50  = calculate_ema(closes, cfg["ema_slow"])
    ema200 = calculate_ema(closes, cfg["ema_long"])

    cur_ema20  = _last_valid(ema20)
    cur_ema50  = _last_valid(ema50)
    cur_ema200 = _last_valid(ema200)
    cur_close  = closes[-1]

    # EMA trend signals
    ema_bullish  = (
        cur_ema20 is not None and cur_ema50 is not None
        and cur_ema20 > cur_ema50
        and cur_close > cur_ema20
    )
    ema_bearish  = (
        cur_ema20 is not None and cur_ema50 is not None
        and cur_ema20 < cur_ema50
        and cur_close < cur_ema20
    )
    ema_above_200 = cur_ema200 is not None and cur_close > cur_ema200
    ema_below_200 = cur_ema200 is not None and cur_close < cur_ema200

    # Golden cross / death cross (20 vs 50)
    prev_ema20 = _last_valid(ema20, offset=2)
    prev_ema50 = _last_valid(ema50, offset=2)
    golden_cross = (
        prev_ema20 is not None and prev_ema50 is not None
        and prev_ema20 <= prev_ema50 and cur_ema20 > cur_ema50
    )
    death_cross  = (
        prev_ema20 is not None and prev_ema50 is not None
        and prev_ema20 >= prev_ema50 and cur_ema20 < cur_ema50
    )

    # ── RSI ───────────────────────────────────────────────
    rsi_vals  = calculate_rsi(closes, cfg["rsi_period"])
    cur_rsi   = _last_valid(rsi_vals)
    prev_rsi  = _last_valid(rsi_vals, offset=2)

    rsi_overbought       = cur_rsi is not None and cur_rsi >= cfg["rsi_overbought"]
    rsi_oversold         = cur_rsi is not None and cur_rsi <= cfg["rsi_oversold"]
    rsi_strong_ob        = cur_rsi is not None and cur_rsi >= cfg["rsi_strong_overbought"]
    rsi_strong_os        = cur_rsi is not None and cur_rsi <= cfg["rsi_strong_oversold"]
    rsi_turning_down     = (
        cur_rsi is not None and prev_rsi is not None
        and rsi_overbought and cur_rsi < prev_rsi
    )
    rsi_turning_up       = (
        cur_rsi is not None and prev_rsi is not None
        and rsi_oversold and cur_rsi > prev_rsi
    )

    # RSI Divergence — bullish: price lower low but RSI higher low
    rsi_bull_div, rsi_bear_div = _detect_rsi_divergence(closes, rsi_vals)

    # ── MACD ──────────────────────────────────────────────
    macd_line, signal_line, histogram = calculate_macd(
        closes, cfg["macd_fast"], cfg["macd_slow"], cfg["macd_signal"]
    )
    cur_macd   = _last_valid(macd_line)
    cur_sig    = _last_valid(signal_line)
    cur_hist   = _last_valid(histogram)
    prev_macd  = _last_valid(macd_line, offset=2)
    prev_sig   = _last_valid(signal_line, offset=2)

    macd_bullish_cross = (
        prev_macd is not None and prev_sig is not None
        and cur_macd is not None and cur_sig is not None
        and prev_macd <= prev_sig and cur_macd > cur_sig
    )
    macd_bearish_cross = (
        prev_macd is not None and prev_sig is not None
        and cur_macd is not None and cur_sig is not None
        and prev_macd >= prev_sig and cur_macd < cur_sig
    )
    macd_above_zero   = cur_macd is not None and cur_macd > 0
    macd_hist_rising  = (
        cur_hist is not None and _last_valid(histogram, offset=2) is not None
        and cur_hist > _last_valid(histogram, offset=2)
    )

    # ── Bollinger Bands ───────────────────────────────────
    bb_upper, bb_mid, bb_lower = calculate_bollinger_bands(
        closes, cfg["bb_period"], cfg["bb_std"]
    )
    cur_bb_upper = _last_valid(bb_upper)
    cur_bb_mid   = _last_valid(bb_mid)
    cur_bb_lower = _last_valid(bb_lower)

    bb_squeeze = False
    if cur_bb_upper is not None and cur_bb_lower is not None and cur_bb_mid is not None:
        bb_width    = (cur_bb_upper - cur_bb_lower) / cur_bb_mid
        bb_upper_20 = _get_slice(bb_upper, 20)
        bb_lower_20 = _get_slice(bb_lower, 20)
        bb_mid_20   = _get_slice(bb_mid, 20)
        widths_20   = [
            (u - l) / m if m > 0 else 0
            for u, l, m in zip(bb_upper_20, bb_lower_20, bb_mid_20)
            if not (math.isnan(u) or math.isnan(l) or math.isnan(m))
        ]
        if widths_20:
            avg_width = sum(widths_20) / len(widths_20)
            bb_squeeze = bb_width < avg_width * 0.7  # narrower than 70% of recent avg

    price_at_upper = (
        cur_bb_upper is not None and cur_close >= cur_bb_upper * 0.998
    )
    price_at_lower = (
        cur_bb_lower is not None and cur_close <= cur_bb_lower * 1.002
    )

    # ── Stochastic ────────────────────────────────────────
    stoch_k, stoch_d = calculate_stochastic(
        highs, lows, closes, cfg["stoch_k"], cfg["stoch_d"]
    )
    cur_sk    = _last_valid(stoch_k)
    cur_sd    = _last_valid(stoch_d)
    prev_sk   = _last_valid(stoch_k, offset=2)
    prev_sd   = _last_valid(stoch_d, offset=2)

    stoch_oversold    = cur_sk is not None and cur_sk <= cfg["stoch_oversold"]
    stoch_overbought  = cur_sk is not None and cur_sk >= cfg["stoch_overbought"]
    stoch_bull_cross  = (
        prev_sk is not None and prev_sd is not None
        and cur_sk is not None and cur_sd is not None
        and prev_sk <= prev_sd and cur_sk > cur_sd
        and cur_sk <= 40  # only meaningful when in lower zone
    )
    stoch_bear_cross  = (
        prev_sk is not None and prev_sd is not None
        and cur_sk is not None and cur_sd is not None
        and prev_sk >= prev_sd and cur_sk < cur_sd
        and cur_sk >= 60
    )

    # ── ATR ───────────────────────────────────────────────
    atr = calculate_atr(highs, lows, closes, cfg["atr_period"])

    # ── Volume ────────────────────────────────────────────
    vol_high_mult   = cfg["volume_high_multiplier"]
    vol_climax_mult = cfg["volume_climax_multiplier"]

    avg_vol_10  = _avg(vols, 10)
    cur_vol     = vols[-1] if vols else 0
    vol_ratio   = cur_vol / avg_vol_10 if avg_vol_10 > 0 else 1.0
    high_volume = vol_ratio >= vol_high_mult
    climax_vol  = vol_ratio >= vol_climax_mult
    low_volume  = vol_ratio < 0.7

    return {
        # Raw values
        "close":      cur_close,
        "ema20":      cur_ema20,
        "ema50":      cur_ema50,
        "ema200":     cur_ema200,
        "rsi":        cur_rsi,
        "macd":       cur_macd,
        "macd_sig":   cur_sig,
        "macd_hist":  cur_hist,
        "bb_upper":   cur_bb_upper,
        "bb_mid":     cur_bb_mid,
        "bb_lower":   cur_bb_lower,
        "stoch_k":    cur_sk,
        "stoch_d":    cur_sd,
        "atr":        atr,
        "volume":     cur_vol,
        "vol_ratio":  vol_ratio,

        # EMA signals
        "ema_bullish":    ema_bullish,
        "ema_bearish":    ema_bearish,
        "ema_above_200":  ema_above_200,
        "ema_below_200":  ema_below_200,
        "golden_cross":   golden_cross,
        "death_cross":    death_cross,

        # RSI signals
        "rsi_overbought":   rsi_overbought,
        "rsi_oversold":     rsi_oversold,
        "rsi_strong_ob":    rsi_strong_ob,
        "rsi_strong_os":    rsi_strong_os,
        "rsi_turning_down": rsi_turning_down,
        "rsi_turning_up":   rsi_turning_up,
        "rsi_bull_div":     rsi_bull_div,
        "rsi_bear_div":     rsi_bear_div,

        # MACD signals
        "macd_bullish_cross": macd_bullish_cross,
        "macd_bearish_cross": macd_bearish_cross,
        "macd_above_zero":    macd_above_zero,
        "macd_hist_rising":   macd_hist_rising,

        # BB signals
        "bb_squeeze":      bb_squeeze,
        "price_at_upper":  price_at_upper,
        "price_at_lower":  price_at_lower,

        # Stochastic
        "stoch_oversold":   stoch_oversold,
        "stoch_overbought": stoch_overbought,
        "stoch_bull_cross": stoch_bull_cross,
        "stoch_bear_cross": stoch_bear_cross,

        # Volume
        "high_volume":  high_volume,
        "climax_vol":   climax_vol,
        "low_volume":   low_volume,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _last_valid(vals: list, offset: int = 1):
    """Return the last non-NaN value, going back `offset` positions from end."""
    target = len(vals) - offset
    for i in range(target, -1, -1):
        if i >= 0 and not math.isnan(vals[i]):
            return vals[i]
    return None


def _avg(vals: list, n: int) -> float:
    window = [v for v in vals[-n:] if v and not math.isnan(v)]
    return sum(window) / len(window) if window else 0.0


def _get_slice(vals: list, n: int) -> list:
    return vals[-n:] if len(vals) >= n else vals


def _detect_rsi_divergence(
    closes: list, rsi_vals: list
) -> tuple:
    """
    Detect bullish and bearish RSI divergence over last 20 candles.
    
    Bullish: price makes lower low, RSI makes higher low → reversal up
    Bearish: price makes higher high, RSI makes lower high → reversal down
    """
    window = 20
    if len(closes) < window or len(rsi_vals) < window:
        return False, False

    p = closes[-window:]
    r = [v for v in rsi_vals[-window:] if not math.isnan(v)]

    if len(r) < 5:
        return False, False

    # Find two recent lows and two recent highs in price
    # Simple approach: compare first half vs second half extremes
    mid = len(p) // 2
    p1_low  = min(p[:mid])
    p2_low  = min(p[mid:])
    p1_high = max(p[:mid])
    p2_high = max(p[mid:])

    r_mid = len(r) // 2
    r1_low  = min(r[:r_mid])
    r2_low  = min(r[r_mid:])
    r1_high = max(r[:r_mid])
    r2_high = max(r[r_mid:])

    # Bullish divergence: price lower low but RSI higher low
    bull_div = p2_low < p1_low * 0.998 and r2_low > r1_low * 1.02

    # Bearish divergence: price higher high but RSI lower high
    bear_div = p2_high > p1_high * 1.002 and r2_high < r1_high * 0.98

    return bull_div, bear_div


def _empty_bundle() -> dict:
    nan = float("nan")
    return {k: None for k in [
        "close", "ema20", "ema50", "ema200", "rsi", "macd", "macd_sig",
        "macd_hist", "bb_upper", "bb_mid", "bb_lower", "stoch_k", "stoch_d",
        "atr", "volume", "vol_ratio",
    ]} | {k: False for k in [
        "ema_bullish", "ema_bearish", "ema_above_200", "ema_below_200",
        "golden_cross", "death_cross", "rsi_overbought", "rsi_oversold",
        "rsi_strong_ob", "rsi_strong_os", "rsi_turning_down", "rsi_turning_up",
        "rsi_bull_div", "rsi_bear_div", "macd_bullish_cross", "macd_bearish_cross",
        "macd_above_zero", "macd_hist_rising", "bb_squeeze",
        "price_at_upper", "price_at_lower", "stoch_oversold", "stoch_overbought",
        "stoch_bull_cross", "stoch_bear_cross", "high_volume", "climax_vol", "low_volume",
    ]}
