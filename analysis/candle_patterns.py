"""analysis/candle_patterns.py — Candle pattern detector."""

from typing import List, Optional
from utils.logger import get_logger

logger = get_logger(__name__)


class CandlePatternDetector:

    def __init__(self, config: dict) -> None:
        self._cfg = config["candle_patterns"]

    def detect(self, candles: List[dict]) -> Optional[dict]:
        """Detect pattern from the last 1-3 candles. Returns pattern dict or None."""
        if len(candles) < 1:
            return None

        c = candles[-1]  # current
        p = candles[-2] if len(candles) >= 2 else None  # previous
        pp = candles[-3] if len(candles) >= 3 else None  # two back

        wr = self._cfg["pin_bar_wick_ratio"]
        et = self._cfg["engulfing_tolerance_pct"]
        dr = self._cfg["doji_body_ratio"]

        result = (
            self._pin_bar(c, wr)
            or self._engulfing(c, p, et)
            or self._doji(c, dr)
            or self._inside_bar(c, p, self._cfg["inside_bar_tolerance_pct"])
            or self._morning_evening_star(c, p, pp)
            or self._tweezer(c, p, self._cfg["tweezer_tolerance_pct"])
            or self._liquidity_sweep(c, p)
        )

        return result

    # ─── Patterns ────────────────────────────────────────────────────────────

    def _pin_bar(self, c, wr):
        body   = abs(c["close"] - c["open"])
        total  = c["high"] - c["low"]
        if total == 0: return None
        upper  = c["high"] - max(c["open"], c["close"])
        lower  = min(c["open"], c["close"]) - c["low"]

        # Bullish pin bar: long lower wick
        if lower >= wr * body and upper < body:
            return {"pattern": "PIN_BAR", "direction": "buy",
                    "quality": "strong" if lower >= wr * 2 * body else "moderate",
                    "score": 15}
        # Shooting star: long upper wick
        if upper >= wr * body and lower < body:
            return {"pattern": "SHOOTING_STAR", "direction": "sell",
                    "quality": "strong" if upper >= wr * 2 * body else "moderate",
                    "score": 15}
        return None

    def _engulfing(self, c, p, et):
        if p is None: return None
        c_bull = c["close"] > c["open"]
        p_bull = p["close"] > p["open"]
        c_body_bot = min(c["open"], c["close"])
        c_body_top = max(c["open"], c["close"])
        p_body_bot = min(p["open"], p["close"])
        p_body_top = max(p["open"], p["close"])

        tol = abs(p_body_top - p_body_bot) * et

        if c_bull and not p_bull and c_body_bot <= p_body_bot + tol and c_body_top >= p_body_top - tol:
            return {"pattern": "BULLISH_ENGULF", "direction": "buy",
                    "quality": "strong", "score": 12}
        if not c_bull and p_bull and c_body_top >= p_body_top - tol and c_body_bot <= p_body_bot + tol:
            return {"pattern": "BEARISH_ENGULF", "direction": "sell",
                    "quality": "strong", "score": 12}
        return None

    def _doji(self, c, dr):
        total = c["high"] - c["low"]
        if total == 0: return None
        body = abs(c["close"] - c["open"])
        if body / total <= dr:
            return {"pattern": "DOJI", "direction": "neutral",
                    "quality": "weak", "score": 5}
        return None

    def _inside_bar(self, c, p, tol):
        if p is None: return None
        p_low  = p["low"]  * (1 - tol)
        p_high = p["high"] * (1 + tol)
        if c["high"] <= p_high and c["low"] >= p_low:
            direction = "buy" if c["close"] > c["open"] else "sell"
            return {"pattern": "INSIDE_BAR", "direction": direction,
                    "quality": "moderate", "score": 8}
        return None

    def _morning_evening_star(self, c, p, pp):
        if p is None or pp is None: return None
        # Morning star: red → small → green
        pp_bear = pp["close"] < pp["open"]
        c_bull  = c["close"] > c["open"]
        p_small = abs(p["close"] - p["open"]) < abs(pp["close"] - pp["open"]) * 0.5
        if pp_bear and c_bull and p_small:
            return {"pattern": "MORNING_STAR", "direction": "buy",
                    "quality": "strong", "score": 12}
        # Evening star: green → small → red
        pp_bull = pp["close"] > pp["open"]
        c_bear  = c["close"] < c["open"]
        if pp_bull and c_bear and p_small:
            return {"pattern": "EVENING_STAR", "direction": "sell",
                    "quality": "strong", "score": 12}
        return None

    def _tweezer(self, c, p, tol):
        if p is None: return None
        # Tweezer bottom: near-identical lows
        low_diff = abs(c["low"] - p["low"]) / max(c["low"], 1)
        high_diff = abs(c["high"] - p["high"]) / max(c["high"], 1)
        if low_diff <= tol / 100:
            return {"pattern": "TWEEZER_BOTTOM", "direction": "buy",
                    "quality": "moderate", "score": 10}
        if high_diff <= tol / 100:
            return {"pattern": "TWEEZER_TOP", "direction": "sell",
                    "quality": "moderate", "score": 10}
        return None

    def _liquidity_sweep(self, c, p):
        if p is None: return None
        # Brief spike below prior low then strong close above
        if c["low"] < p["low"] and c["close"] > p["low"] and c["close"] > c["open"]:
            return {"pattern": "LIQ_SWEEP_BULL", "direction": "buy",
                    "quality": "strong", "score": 15}
        if c["high"] > p["high"] and c["close"] < p["high"] and c["close"] < c["open"]:
            return {"pattern": "LIQ_SWEEP_BEAR", "direction": "sell",
                    "quality": "strong", "score": 15}
        return None


def pattern_aligns(result: Optional[dict], direction: str) -> bool:
    if not result:
        return False
    pd = result.get("direction", "neutral")
    return pd == direction or pd == "neutral"
