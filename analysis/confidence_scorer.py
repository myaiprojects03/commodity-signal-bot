"""
analysis/confidence_scorer.py

Master confidence scoring engine for commodity signals.

Score contributions:
  S/R Zones:        up to +75  (zone quality, freshness, confluence)
  Indicator Suite:  up to +50  (RSI, MACD, EMA, Stoch — multi-indicator confluence)
  Candle Pattern:   up to +15
  Volume:           up to +15
  Trend alignment:  up to +20
  Session:          up to +10
  R:R:              up to +10

Penalties:
  Counter-trend:    -15
  Asian pre-market: -5
  Climax vol w/o pattern: -8
  Failed swing:     -8
  4th zone test:    -5
  Low volume:       -15

Hard Discard Rules:
  1. Dead zone session
  2. R:R < minimum
  3. Zone exhausted (5+ touches)
  4. All 3 TFs counter-trend
  5. Climax vol without rejection candle
  6. Score < min_confidence_score after scoring
"""

import math
from typing import Optional

from analysis.support_resistance import score_zone
from analysis.trend import score_trend
from utils.helpers import clamp, normalize_score
from utils.logger import get_logger

logger = get_logger(__name__)

_RAW_MIN = -60
_RAW_MAX = 195


class ConfidenceScorer:

    def __init__(self, config: dict) -> None:
        self._cfg    = config["signals"]
        self._sr_cfg = config["support_resistance"]
        self._min    = self._cfg["min_confidence_score"]
        self._strong = self._cfg["strong_threshold"]
        self._elite  = self._cfg["elite_threshold"]

    def score(
        self,
        direction: str,
        zone: Optional[dict],
        support_zone: Optional[dict],
        resistance_zone: Optional[dict],
        trend_bias: dict,
        pattern_result: Optional[dict],
        indicators: dict,
        session_result: dict,
        rr_result: dict,
        current_price: float,
        candles: list,
    ) -> dict:
        """Full scoring pipeline. Returns scoring result dict."""

        # ── Hard Discards ────────────────────────────────────────────────────
        discard, reason = self._hard_discards(
            zone, trend_bias, session_result, rr_result, pattern_result, indicators
        )
        if discard:
            return _discard(reason)

        # ── Score Accumulation ───────────────────────────────────────────────
        contributions = {}
        penalties     = {}
        raw = 0

        # S/R Zone
        sr_score = score_zone(zone, self._sr_cfg) if zone else 0
        contributions["zone"] = sr_score
        raw += sr_score

        # Candle Pattern
        pat_score = 0
        if pattern_result:
            from analysis.candle_patterns import pattern_aligns
            if pattern_aligns(pattern_result, direction):
                pat_score = pattern_result.get("score", 0)
        contributions["pattern"] = pat_score
        raw += pat_score

        # Indicator confluence score
        ind_score, ind_breakdown = self._score_indicators(indicators, direction)
        contributions.update(ind_breakdown)
        raw += ind_score

        # Volume
        vol_score = self._score_volume(indicators, pattern_result, penalties, raw)
        contributions["volume"] = vol_score
        raw += vol_score

        # Trend
        trend_score = score_trend(trend_bias, direction)
        contributions["trend"] = trend_score
        raw += trend_score

        # Counter-trend penalty
        if trend_bias.get("counter"):
            penalties["counter_trend"] = -15
            raw -= 15
        elif not trend_bias.get("aligned") and not trend_bias.get("partial"):
            penalties["weak_alignment"] = -5
            raw -= 5

        # Failed swing penalty
        h4 = trend_bias.get("h4", {})
        if h4.get("failed_swing") and trend_bias.get("h4_aligned"):
            penalties["failed_swing"] = -8
            raw -= 8

        # Session
        sess_adj = session_result.get("score_adjustment", 0)
        contributions["session"] = sess_adj
        raw += sess_adj

        # R:R
        rr_score = rr_result.get("score", 0)
        contributions["rr"] = rr_score
        raw += rr_score

        # Zone 4th test penalty
        if zone and zone.get("touch_count", 0) == 4:
            penalties["zone_4th_test"] = -5
            raw -= 5

        # ── Normalise ────────────────────────────────────────────────────────
        normalised = normalize_score(raw, _RAW_MIN, _RAW_MAX)
        final = int(clamp(normalised, 0, 100))

        if final < self._min:
            return _discard(f"score {final}/100 below threshold {self._min}")

        label = self._label(final)
        stype = "BUY" if direction == "buy" else "SELL"
        if final < self._cfg["moderate_threshold"] + 5:
            stype = "WATCH"

        return {
            "score":         final,
            "raw_score":     raw,
            "signal_type":   stype,
            "label":         label,
            "discard":       False,
            "discard_reason": "",
            "contributions": contributions,
            "penalties":     penalties,
        }

    # ─── Indicator scoring ───────────────────────────────────────────────────

    def _score_indicators(self, ind: dict, direction: str) -> tuple:
        """
        Score the indicator suite. Multiple confirming indicators = higher score.
        No single indicator is relied upon — confluence is the key.
        """
        score = 0
        breakdown = {}
        is_buy = direction == "buy"

        # EMA alignment
        if is_buy:
            if ind.get("ema_bullish"):      score += 8;  breakdown["ema_trend"] = 8
            if ind.get("ema_above_200"):    score += 5;  breakdown["ema_200"] = 5
            if ind.get("golden_cross"):     score += 5;  breakdown["golden_cross"] = 5
        else:
            if ind.get("ema_bearish"):      score += 8;  breakdown["ema_trend"] = 8
            if ind.get("ema_below_200"):    score += 5;  breakdown["ema_200"] = 5
            if ind.get("death_cross"):      score += 5;  breakdown["death_cross"] = 5

        # RSI confirmation
        rsi = ind.get("rsi")
        if rsi and not math.isnan(rsi):
            if is_buy:
                if ind.get("rsi_oversold"):     score += 8;  breakdown["rsi_oversold"] = 8
                elif ind.get("rsi_strong_os"):  score += 12; breakdown["rsi_strong_os"] = 12
                elif ind.get("rsi_turning_up"): score += 6;  breakdown["rsi_turning_up"] = 6
                elif ind.get("rsi_bull_div"):   score += 10; breakdown["rsi_bull_div"] = 10
            else:
                if ind.get("rsi_overbought"):    score += 8;  breakdown["rsi_ob"] = 8
                elif ind.get("rsi_strong_ob"):   score += 12; breakdown["rsi_strong_ob"] = 12
                elif ind.get("rsi_turning_down"):score += 6;  breakdown["rsi_turning_down"] = 6
                elif ind.get("rsi_bear_div"):    score += 10; breakdown["rsi_bear_div"] = 10

        # MACD confirmation
        if is_buy:
            if ind.get("macd_bullish_cross"): score += 8;  breakdown["macd_cross"] = 8
            elif ind.get("macd_above_zero") and ind.get("macd_hist_rising"):
                                              score += 4;  breakdown["macd_mom"] = 4
        else:
            if ind.get("macd_bearish_cross"): score += 8;  breakdown["macd_cross"] = 8
            elif not ind.get("macd_above_zero") and not ind.get("macd_hist_rising"):
                                              score += 4;  breakdown["macd_mom"] = 4

        # Stochastic (additional confirmation)
        if is_buy:
            if ind.get("stoch_bull_cross"):   score += 5;  breakdown["stoch"] = 5
            elif ind.get("stoch_oversold"):   score += 3;  breakdown["stoch"] = 3
        else:
            if ind.get("stoch_bear_cross"):   score += 5;  breakdown["stoch"] = 5
            elif ind.get("stoch_overbought"): score += 3;  breakdown["stoch"] = 3

        # Bollinger Bands
        if is_buy and ind.get("price_at_lower"): score += 4; breakdown["bb_level"] = 4
        if not is_buy and ind.get("price_at_upper"): score += 4; breakdown["bb_level"] = 4
        if ind.get("bb_squeeze"): score += 3; breakdown["bb_squeeze"] = 3  # breakout setup

        return score, breakdown

    def _score_volume(self, ind: dict, pattern, penalties: dict, raw: int) -> int:
        if ind.get("high_volume"):   return 12
        if ind.get("climax_vol"):
            rejection = pattern and pattern.get("pattern") in {
                "PIN_BAR", "SHOOTING_STAR", "BULLISH_ENGULF", "BEARISH_ENGULF",
                "LIQ_SWEEP_BULL", "LIQ_SWEEP_BEAR"
            }
            if rejection:
                return 15
            penalties["climax_no_rejection"] = -8
            return -8
        if ind.get("low_volume"):
            penalties["low_volume"] = -15
            return -15
        return 5  # normal volume

    def _hard_discards(
        self, zone, trend_bias, session, rr, pattern, indicators
    ) -> tuple:
        if session.get("discard"):
            return True, session.get("discard_reason", "Dead zone")
        if rr.get("discard"):
            return True, rr.get("discard_reason", "R:R below minimum")
        if zone and zone.get("touch_count", 0) >= self._sr_cfg.get("max_touches_before_discard", 5):
            return True, f"Zone exhausted ({zone['touch_count']} touches)"
        if trend_bias.get("opposing_count", 0) >= 2 and trend_bias.get("opposing_count", 0) >= sum([
            trend_bias.get("weekly_aligned", False),
            trend_bias.get("daily_aligned", False),
            trend_bias.get("h4_aligned", False),
        ]):
            if sum([trend_bias.get(f"{tf}_aligned", False) for tf in ["weekly","daily","h4"]]) == 0:
                return True, "All 3 timeframes counter-trend"
        if indicators.get("climax_vol") and not (pattern and pattern.get("pattern") in {
            "PIN_BAR", "SHOOTING_STAR", "BULLISH_ENGULF", "BEARISH_ENGULF",
            "LIQ_SWEEP_BULL", "LIQ_SWEEP_BEAR"
        }):
            return True, "Climax volume without rejection candle"
        return False, ""

    def _label(self, score: int) -> str:
        if score >= self._elite:  return "ELITE"
        if score >= self._strong: return "STRONG"
        return "MODERATE"


def _discard(reason: str) -> dict:
    return {
        "score": 0, "raw_score": 0, "signal_type": None, "label": None,
        "discard": True, "discard_reason": reason,
        "contributions": {}, "penalties": {},
    }
