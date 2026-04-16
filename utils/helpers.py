"""utils/helpers.py — Shared math and price utilities."""

from typing import List, Optional, Tuple
import math


# ─────────────────────────────────────────────────────────────────────────────
# ATR
# ─────────────────────────────────────────────────────────────────────────────

def calculate_atr(
    highs: List[float],
    lows: List[float],
    closes: List[float],
    period: int = 14,
) -> float:
    """Wilder's ATR calculation. Returns 0.0 if insufficient data."""
    if len(highs) < period + 1:
        if len(highs) < 2:
            return 0.0
        period = len(highs) - 1

    trs = []
    for i in range(1, len(highs)):
        h, l, prev_c = highs[i], lows[i], closes[i - 1]
        tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
        trs.append(tr)

    if not trs:
        return 0.0

    # Simple average for first ATR, then Wilder smoothing
    if len(trs) < period:
        return sum(trs) / len(trs)

    atr = sum(trs[:period]) / period
    for tr in trs[period:]:
        atr = (atr * (period - 1) + tr) / period

    return atr


# ─────────────────────────────────────────────────────────────────────────────
# Indicators
# ─────────────────────────────────────────────────────────────────────────────

def calculate_ema(prices: List[float], period: int) -> List[float]:
    """Exponential Moving Average. Returns list same length as input (NaN-padded)."""
    if len(prices) < period:
        return [float("nan")] * len(prices)

    result = [float("nan")] * len(prices)
    k = 2 / (period + 1)

    # Seed with SMA of first `period` values
    seed = sum(prices[:period]) / period
    result[period - 1] = seed

    for i in range(period, len(prices)):
        result[i] = prices[i] * k + result[i - 1] * (1 - k)

    return result


def calculate_rsi(closes: List[float], period: int = 14) -> List[float]:
    """RSI using Wilder smoothing. Returns list same length as input."""
    if len(closes) < period + 1:
        return [float("nan")] * len(closes)

    result = [float("nan")] * len(closes)
    gains, losses = [], []

    for i in range(1, len(closes)):
        diff = closes[i] - closes[i - 1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(closes)):
        if i > period:
            avg_gain = (avg_gain * (period - 1) + gains[i - 1]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i - 1]) / period

        if avg_loss == 0:
            result[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            result[i] = 100 - (100 / (1 + rs))

    return result


def calculate_macd(
    closes: List[float],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> Tuple[List[float], List[float], List[float]]:
    """Returns (macd_line, signal_line, histogram)."""
    ema_fast = calculate_ema(closes, fast)
    ema_slow = calculate_ema(closes, slow)

    macd_line = [
        (f - s) if not (math.isnan(f) or math.isnan(s)) else float("nan")
        for f, s in zip(ema_fast, ema_slow)
    ]

    valid_macd = [v for v in macd_line if not math.isnan(v)]
    if len(valid_macd) < signal:
        sig_line = [float("nan")] * len(macd_line)
        histogram = [float("nan")] * len(macd_line)
        return macd_line, sig_line, histogram

    # Build signal from valid macd values
    sig_vals = calculate_ema(valid_macd, signal)
    # Realign back
    nan_prefix = len(macd_line) - len(valid_macd)
    sig_line = [float("nan")] * nan_prefix + sig_vals
    histogram = [
        (m - s) if not (math.isnan(m) or math.isnan(s)) else float("nan")
        for m, s in zip(macd_line, sig_line)
    ]

    return macd_line, sig_line, histogram


def calculate_bollinger_bands(
    closes: List[float],
    period: int = 20,
    std_mult: float = 2.0,
) -> Tuple[List[float], List[float], List[float]]:
    """Returns (upper_band, middle_band, lower_band)."""
    n = len(closes)
    upper = [float("nan")] * n
    middle = [float("nan")] * n
    lower = [float("nan")] * n

    for i in range(period - 1, n):
        window = closes[i - period + 1 : i + 1]
        avg = sum(window) / period
        variance = sum((x - avg) ** 2 for x in window) / period
        std = math.sqrt(variance)
        middle[i] = avg
        upper[i] = avg + std_mult * std
        lower[i] = avg - std_mult * std

    return upper, middle, lower


def calculate_stochastic(
    highs: List[float],
    lows: List[float],
    closes: List[float],
    k_period: int = 14,
    d_period: int = 3,
) -> Tuple[List[float], List[float]]:
    """Returns (%K, %D). %K is fast stoch, %D is smoothed."""
    n = len(closes)
    k_vals = [float("nan")] * n

    for i in range(k_period - 1, n):
        window_h = highs[i - k_period + 1 : i + 1]
        window_l = lows[i - k_period + 1 : i + 1]
        highest = max(window_h)
        lowest = min(window_l)
        if highest == lowest:
            k_vals[i] = 50.0
        else:
            k_vals[i] = ((closes[i] - lowest) / (highest - lowest)) * 100

    # %D = SMA of %K
    valid_k = [(i, v) for i, v in enumerate(k_vals) if not math.isnan(v)]
    d_vals = [float("nan")] * n

    if len(valid_k) >= d_period:
        k_only = [v for _, v in valid_k]
        for i in range(d_period - 1, len(k_only)):
            window = k_only[i - d_period + 1 : i + 1]
            d_vals[valid_k[i][0]] = sum(window) / d_period

    return k_vals, d_vals


# ─────────────────────────────────────────────────────────────────────────────
# Swing Detection
# ─────────────────────────────────────────────────────────────────────────────

def find_swing_highs(
    highs: List[float], lookback: int = 5
) -> List[Tuple[int, float]]:
    """Return (index, price) pairs for all swing highs."""
    result = []
    for i in range(lookback, len(highs) - lookback):
        window = highs[i - lookback : i + lookback + 1]
        if highs[i] == max(window):
            result.append((i, highs[i]))
    return result


def find_swing_lows(
    lows: List[float], lookback: int = 5
) -> List[Tuple[int, float]]:
    """Return (index, price) pairs for all swing lows."""
    result = []
    for i in range(lookback, len(lows) - lookback):
        window = lows[i - lookback : i + lookback + 1]
        if lows[i] == min(window):
            result.append((i, lows[i]))
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Price Utilities
# ─────────────────────────────────────────────────────────────────────────────

def is_round_number(price: float, tolerance_pct: float = 0.003) -> bool:
    """True if price is within tolerance_pct of a round number."""
    if price <= 0:
        return False
    magnitudes = [1, 5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000]
    for mag in magnitudes:
        nearest = round(price / mag) * mag
        if nearest > 0 and abs(price - nearest) / nearest <= tolerance_pct:
            return True
    return False


def price_is_near_zone(
    price: float,
    zone_low: float,
    zone_high: float,
    buffer_pct: float = 0.005,
) -> bool:
    """True if price is inside the zone or within buffer_pct of its edges."""
    buffer = price * buffer_pct
    return (zone_low - buffer) <= price <= (zone_high + buffer)


def format_price(price: Optional[float], reference: float = 0.0) -> str:
    """Format a price with appropriate decimal places based on magnitude."""
    if price is None or math.isnan(price):
        return "N/A"
    if reference >= 1000 or price >= 1000:
        return f"{price:,.2f}"
    if reference >= 10 or price >= 10:
        return f"{price:.3f}"
    return f"{price:.5f}"


def clamp(value: float, min_val: float, max_val: float) -> float:
    return max(min_val, min(max_val, value))


def normalize_score(raw: float, raw_min: float, raw_max: float) -> float:
    if raw_max == raw_min:
        return 50.0
    return ((raw - raw_min) / (raw_max - raw_min)) * 100


def safe_divide(a: float, b: float, default: float = 0.0) -> float:
    if b == 0:
        return default
    return a / b
