"""
analysis/liquidity.py

Liquidity analysis: equal highs/lows, stop hunts, fair value gaps (FVG).
These are some of the highest-conviction reversal signals available.
"""

from typing import List, Optional
from utils.logger import get_logger

logger = get_logger(__name__)


class LiquidityAnalyzer:

    def __init__(self, config: dict) -> None:
        self._cfg = config["liquidity"]

    def analyse(self, candles: List[dict], current_price: float) -> dict:
        if len(candles) < 10:
            return _empty()

        tol_pct   = self._cfg["equal_level_tolerance_pct"] / 100
        min_eq    = self._cfg["min_equal_levels"]
        rev_cndls = self._cfg["sweep_reversal_candles"]

        highs = [c["high"]  for c in candles]
        lows  = [c["low"]   for c in candles]

        buy_pools  = _find_equal_levels(lows,  tol_pct, min_eq)
        sell_pools = _find_equal_levels(highs, tol_pct, min_eq)

        sweep, sweep_lvl, sweep_dir = _detect_sweep(candles, rev_cndls, tol_pct)

        bull_fvg = _find_fvg(candles, "bull")
        bear_fvg = _find_fvg(candles, "bear")

        return {
            "buy_side_pools":   buy_pools,
            "sell_side_pools":  sell_pools,
            "sweep_detected":   sweep,
            "sweep_level":      sweep_lvl,
            "sweep_direction":  sweep_dir,
            "nearest_bull_fvg": bull_fvg,
            "nearest_bear_fvg": bear_fvg,
        }


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _find_equal_levels(
    price_series: List[float], tol_pct: float, min_count: int
) -> List[dict]:
    """Find clusters of equal highs or equal lows (liquidity pools)."""
    pools = []
    used  = [False] * len(price_series)

    for i in range(len(price_series)):
        if used[i]:
            continue
        cluster = [price_series[i]]
        indices = [i]
        for j in range(i + 1, len(price_series)):
            if used[j]:
                continue
            if abs(price_series[j] - price_series[i]) / max(price_series[i], 1) <= tol_pct:
                cluster.append(price_series[j])
                indices.append(j)
                used[j] = True

        if len(cluster) >= min_count:
            pools.append({
                "level":   sum(cluster) / len(cluster),
                "count":   len(cluster),
                "indices": indices,
            })
        used[i] = True

    return pools


def _detect_sweep(
    candles: List[dict], reversal_candles: int, tol_pct: float
) -> tuple:
    """
    Detect a stop hunt / liquidity sweep.

    Pattern:
    - Price briefly spikes beyond a prior high or low (triggers stops)
    - Then strongly reverses within `reversal_candles` bars

    Returns: (sweep_detected, sweep_level, direction)
    """
    if len(candles) < reversal_candles + 5:
        return False, 0.0, None

    # Look at the last 20 candles
    window = candles[-20:]
    n      = len(window)

    for i in range(2, n - reversal_candles):
        c = window[i]
        # Collect prior highs and lows (from 10 candles before spike)
        prior = window[max(0, i - 10) : i]
        if not prior:
            continue

        prior_high = max(x["high"] for x in prior)
        prior_low  = min(x["low"]  for x in prior)

        # Bullish sweep: spike below prior low → reversal up
        if c["low"] < prior_low * (1 - tol_pct):
            post = window[i : i + reversal_candles]
            if post and post[-1]["close"] > prior_low:
                return True, c["low"], "bull"

        # Bearish sweep: spike above prior high → reversal down
        if c["high"] > prior_high * (1 + tol_pct):
            post = window[i : i + reversal_candles]
            if post and post[-1]["close"] < prior_high:
                return True, c["high"], "bear"

    return False, 0.0, None


def _find_fvg(candles: List[dict], direction: str) -> Optional[dict]:
    """
    Find the most recent Fair Value Gap (FVG / imbalance).

    Bullish FVG: candle[n-1].high < candle[n+1].low  → gap between them
    Bearish FVG: candle[n-1].low  > candle[n+1].high → gap between them
    """
    if len(candles) < 3:
        return None

    for i in range(len(candles) - 1, 1, -1):
        prev2 = candles[i - 2]
        prev1 = candles[i - 1]  # noqa — middle candle (unused)
        curr  = candles[i]

        if direction == "bull":
            gap_low  = prev2["high"]
            gap_high = curr["low"]
            if gap_high > gap_low:
                return {"gap_low": gap_low, "gap_high": gap_high,
                        "midpoint": (gap_low + gap_high) / 2}
        else:
            gap_low  = curr["high"]
            gap_high = prev2["low"]
            if gap_low < gap_high:
                return {"gap_low": gap_low, "gap_high": gap_high,
                        "midpoint": (gap_low + gap_high) / 2}

    return None


def score_liquidity(result: dict) -> int:
    score = 0
    if result.get("sweep_detected"):           score += 15
    if len(result.get("sell_side_pools", [])) > 0: score += 5
    if len(result.get("buy_side_pools",  [])) > 0: score += 5
    if result.get("nearest_bull_fvg"):         score += 8
    if result.get("nearest_bear_fvg"):         score += 8
    return score


def format_liquidity_label(result: dict) -> dict:
    fvg_parts = []
    if result.get("nearest_bull_fvg"):
        f = result["nearest_bull_fvg"]
        fvg_parts.append(f"Bull FVG {f['gap_low']:.2f}–{f['gap_high']:.2f}")
    if result.get("nearest_bear_fvg"):
        f = result["nearest_bear_fvg"]
        fvg_parts.append(f"Bear FVG {f['gap_low']:.2f}–{f['gap_high']:.2f}")

    buy_p  = result.get("buy_side_pools",  [])
    sell_p = result.get("sell_side_pools", [])
    eq_str = f"{len(buy_p)} buy-side / {len(sell_p)} sell-side pools" if (buy_p or sell_p) else "None"

    return {
        "fvg":          ", ".join(fvg_parts) if fvg_parts else "None",
        "equal_levels": eq_str,
    }


def _empty() -> dict:
    return {
        "buy_side_pools":   [],
        "sell_side_pools":  [],
        "sweep_detected":   False,
        "sweep_level":      0.0,
        "sweep_direction":  None,
        "nearest_bull_fvg": None,
        "nearest_bear_fvg": None,
    }
