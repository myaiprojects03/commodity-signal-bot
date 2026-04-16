"""
analysis/trend.py

Multi-timeframe trend engine (ported from crypto bot, adapted for commodities).
Works with 3 timeframes: Weekly (macro), Daily (structural), H4 (signal).
"""

from typing import Dict, List, Tuple

from utils.helpers import find_swing_highs, find_swing_lows
from utils.logger import get_logger

logger = get_logger(__name__)

UPTREND   = "uptrend"
DOWNTREND = "downtrend"
RANGE     = "range"
STRONG    = "strong"
MODERATE  = "moderate"
WEAK      = "weak"


class TrendAnalyzer:

    def __init__(self, symbol: str, config: dict) -> None:
        self._symbol = symbol
        self._cfg    = config["trend"]
        self._states: Dict[str, dict] = {}

    def analyse(self, candles_by_tf: Dict[str, List[dict]]) -> None:
        for tf, candles in candles_by_tf.items():
            if len(candles) < self._cfg["min_swings_for_structure"] * 4:
                self._states[tf] = _empty_state(tf)
                continue
            self._states[tf] = self._analyse_tf(candles, tf)

    def get_bias(self, signal_direction: str) -> dict:
        weekly = self._states.get("1wk", _empty_state("1wk"))
        daily  = self._states.get("1d",  _empty_state("1d"))
        h4     = self._states.get("4h",  _empty_state("4h"))
        h1     = self._states.get("1h",  _empty_state("1h"))

        is_buy = signal_direction.lower() == "buy"

        def aligns(s):
            return s["direction"] == (UPTREND if is_buy else DOWNTREND)

        def opposes(s):
            return s["direction"] == (DOWNTREND if is_buy else UPTREND)

        w_ok = aligns(weekly); d_ok = aligns(daily); h4_ok = aligns(h4)
        w_op = opposes(weekly); d_op = opposes(daily); h4_op = opposes(h4)

        aligned_count  = sum([w_ok, d_ok, h4_ok])
        opposing_count = sum([w_op, d_op, h4_op])

        return {
            "weekly":  weekly, "daily":  daily, "h4":  h4, "h1": h1,
            "aligned": aligned_count == 3,
            "partial": aligned_count == 2,
            "counter": opposing_count >= 2,
            "weekly_aligned": w_ok, "daily_aligned": d_ok, "h4_aligned": h4_ok,
            "weekly_opposes": w_op, "daily_opposes": d_op, "h4_opposes": h4_op,
            "opposing_count": opposing_count,
        }

    def _analyse_tf(self, candles: List[dict], tf: str) -> dict:
        highs = [c["high"] for c in candles]
        lows  = [c["low"]  for c in candles]
        lb    = self._cfg["swing_lookback"]
        mins  = self._cfg["min_swings_for_structure"]

        sh = find_swing_highs(highs, lb)
        sl = find_swing_lows(lows, lb)

        if len(sh) < mins or len(sl) < mins:
            return _empty_state(tf)

        direction = _classify(sh, sl, mins)
        strength  = _strength(sh, sl, direction, mins)
        failed    = _failed_swing(sh, sl, direction, self._cfg["failed_swing_tolerance_pct"] / 100)
        slope     = _slope(sh, sl, direction, mins)

        return {
            "direction":    direction,
            "strength":     strength,
            "failed_swing": failed,
            "swing_highs":  sh[-mins:],
            "swing_lows":   sl[-mins:],
            "slope":        slope,
            "timeframe":    tf,
        }


def score_trend(bias: dict, signal_direction: str) -> int:
    score = 0
    if bias["aligned"]:
        score += 20
    elif bias["partial"]:
        score += 12
    else:
        score += 5
    h4 = bias.get("h4", {})
    if h4.get("failed_swing") and bias.get("h4_aligned"):
        score -= 8
    return score


def get_trend_label(direction: str) -> str:
    return {"uptrend": "Bullish", "downtrend": "Bearish", "range": "Range"}.get(direction, "Unknown")


# ─── Private helpers ─────────────────────────────────────────────────────────

def _classify(sh, sl, n) -> str:
    rh = [p for _, p in sh[-n:]]
    rl = [p for _, p in sl[-n:]]
    hh = all(rh[i] > rh[i-1] for i in range(1, len(rh)))
    hl = all(rl[i] > rl[i-1] for i in range(1, len(rl)))
    lh = all(rh[i] < rh[i-1] for i in range(1, len(rh)))
    ll = all(rl[i] < rl[i-1] for i in range(1, len(rl)))
    if hh and hl: return UPTREND
    if lh and ll: return DOWNTREND
    return RANGE


def _strength(sh, sl, direction, n) -> str:
    if direction == RANGE:
        return WEAK
    pairs = min(len(sh), len(sl), n)
    sizes = [sh[i][1] - sl[i][1] for i in range(pairs)]
    if len(sizes) < 2:
        return MODERATE
    ratio = sizes[-1] / sizes[-2] if sizes[-2] != 0 else 1.0
    if ratio >= 0.9: return STRONG
    if ratio >= 0.65: return MODERATE
    return WEAK


def _failed_swing(sh, sl, direction, tol) -> bool:
    if direction == RANGE or len(sh) < 3 or len(sl) < 3:
        return False
    if direction == UPTREND:
        return (sh[-1][1] <= sh[-2][1] * (1 + tol)) and (sl[-1][1] < sl[-2][1])
    return (sl[-1][1] >= sl[-2][1] * (1 - tol)) and (sh[-1][1] > sh[-2][1])


def _slope(sh, sl, direction, n) -> float:
    if direction == RANGE:
        return 0.0
    pairs = min(len(sh), len(sl), n)
    if pairs < 2:
        return 0.0
    mids = [((sh[i][1]+sl[i][1])/2, (sh[i][0]+sl[i][0])/2) for i in range(pairs)]
    slopes = []
    for i in range(1, len(mids)):
        dp = mids[i][0] - mids[i-1][0]
        di = mids[i][1] - mids[i-1][1]
        if di > 0 and mids[i-1][0] > 0:
            slopes.append((dp / mids[i-1][0]) / di)
    return sum(slopes) / len(slopes) if slopes else 0.0


def _empty_state(tf) -> dict:
    return {
        "direction": RANGE, "strength": WEAK, "failed_swing": False,
        "swing_highs": [], "swing_lows": [], "slope": 0.0, "timeframe": tf,
    }
