"""
analysis/support_resistance.py

ATR-based S/R zone detection.
Adapted from the crypto bot's proven engine with commodity-specific tweaks:
- Wider tolerance for commodity price swings
- Round number detection tuned for Gold ($50/$100/$500), Silver ($0.50/$1/$5), Oil ($1/$5/$10)
- Zone scoring includes daily/weekly confluence bonus
"""

from typing import Dict, List, Optional, Tuple

from utils.helpers import (
    calculate_atr,
    find_swing_highs,
    find_swing_lows,
    is_round_number,
    price_is_near_zone,
)
from utils.logger import get_logger

logger = get_logger(__name__)


class SupportResistanceDetector:
    """One instance per instrument symbol."""

    def __init__(self, symbol: str, config: dict) -> None:
        self._symbol = symbol
        self._cfg    = config["support_resistance"]
        self._zones: Dict[str, List[dict]] = {}

    def refresh(self, candles_by_tf: Dict[str, List[dict]]) -> None:
        """Recompute all S/R zones from provided candle data."""
        for tf, candles in candles_by_tf.items():
            if len(candles) < 20:
                continue
            highs  = [c["high"]   for c in candles]
            lows   = [c["low"]    for c in candles]
            closes = [c["close"]  for c in candles]
            vols   = [c["volume"] for c in candles]
            atr    = calculate_atr(highs, lows, closes)
            if atr == 0:
                continue
            self._zones[tf] = self._detect_zones(candles, highs, lows, vols, atr, tf)
            logger.debug(
                "S/R %s/%s: %d zones (ATR=%.3f)",
                self._symbol, tf, len(self._zones[tf]), atr
            )

    def get_zone_at_price(
        self, price: float, timeframe: str, atr: float = 0.0
    ) -> Optional[dict]:
        if atr > 0 and price > 0:
            buf = (atr * 0.5) / price
        else:
            buf = 0.005
        for z in self._zones.get(timeframe, []):
            if z["invalidated"]:
                continue
            if z["touch_count"] >= self._cfg["max_touches_before_discard"]:
                continue
            if price_is_near_zone(price, z["zone_low"], z["zone_high"], buf):
                return z
        return None

    def get_nearest_support(self, price: float, timeframe: str) -> Optional[dict]:
        candidates = [
            z for z in self._zones.get(timeframe, [])
            if not z["invalidated"]
            and z["type"] == "support"
            and z["zone_high"] < price
            and z["touch_count"] < self._cfg["max_touches_before_discard"]
        ]
        if not candidates:
            return None
        candidates.sort(key=lambda z: (price - z["zone_high"], -z["touch_count"]))
        return candidates[0]

    def get_nearest_resistance(self, price: float, timeframe: str) -> Optional[dict]:
        candidates = [
            z for z in self._zones.get(timeframe, [])
            if not z["invalidated"]
            and z["type"] == "resistance"
            and z["zone_low"] > price
            and z["touch_count"] < self._cfg["max_touches_before_discard"]
        ]
        if not candidates:
            return None
        candidates.sort(key=lambda z: (z["zone_low"] - price, -z["touch_count"]))
        return candidates[0]

    def get_all_zones(self, timeframe: str) -> List[dict]:
        return [z for z in self._zones.get(timeframe, []) if not z["invalidated"]]

    def enrich_confluence(self, zone: dict, higher_tfs: List[str]) -> dict:
        """Add daily/weekly confluence flags."""
        zone["daily_confluence"]  = self._has_confluence(zone, "1d")
        zone["weekly_confluence"] = self._has_confluence(zone, "1wk")
        return zone

    def update_invalidations(self, latest_candle: dict, timeframe: str) -> None:
        close    = latest_candle["close"]
        body_top = max(latest_candle["open"], latest_candle["close"])
        body_bot = min(latest_candle["open"], latest_candle["close"])
        for z in self._zones.get(timeframe, []):
            if z["invalidated"]:
                continue
            if z["type"] == "support" and body_top < z["zone_low"]:
                z["invalidated"] = True
                logger.info("Zone invalidated (support broken): %.3f–%.3f", z["zone_low"], z["zone_high"])
            elif z["type"] == "resistance" and body_bot > z["zone_high"]:
                z["invalidated"] = True
                logger.info("Zone invalidated (resistance broken): %.3f–%.3f", z["zone_low"], z["zone_high"])

    # ─── Private ────────────────────────────────────────────────────────────

    def _detect_zones(
        self, candles, highs, lows, vols, atr, timeframe
    ) -> List[dict]:
        tolerance  = atr * self._cfg["atr_zone_multiplier"]
        lookback   = self._cfg["swing_lookback"]

        sh = find_swing_highs(highs, lookback=lookback)
        sl = find_swing_lows(lows,   lookback=lookback)

        res_zones = self._cluster(sh, candles, vols, atr, tolerance, "resistance", timeframe)
        sup_zones = self._cluster(sl, candles, vols, atr, tolerance, "support",    timeframe)

        all_z = res_zones + sup_zones
        min_t = self._cfg["min_touches"]
        return [z for z in all_z if z["touch_count"] >= min_t]

    def _cluster(
        self, swings, candles, vols, atr, tolerance, zone_type, timeframe
    ) -> List[dict]:
        if not swings:
            return []

        avg_vol = sum(vols) / len(vols) if vols else 1.0
        clusters: List[List[Tuple[int, float]]] = []

        for idx, price in swings:
            placed = False
            for cluster in clusters:
                mean = sum(p for _, p in cluster) / len(cluster)
                if abs(price - mean) <= tolerance:
                    cluster.append((idx, price))
                    placed = True
                    break
            if not placed:
                clusters.append([(idx, price)])

        zones = []
        for cluster in clusters:
            prices  = [p for _, p in cluster]
            indices = [i for i, _ in cluster]
            center  = sum(prices) / len(prices)
            half    = tolerance / 2

            zone_low  = center - half
            zone_high = center + half
            touch_cnt = len(cluster)
            first_idx = min(indices)
            last_idx  = max(indices)

            # Departure strength (body of candle after first touch in ATR multiples)
            dep = 0.0
            if first_idx + 1 < len(candles) and atr > 0:
                c = candles[first_idx + 1]
                dep = abs(c["close"] - c["open"]) / atr

            # High volume at touch?
            high_vol = any(
                vols[i] >= avg_vol * 1.5 for i in indices if i < len(vols)
            )

            zones.append({
                "zone_low":           zone_low,
                "zone_high":          zone_high,
                "midpoint":           center,
                "type":               zone_type,
                "touch_count":        touch_cnt,
                "first_touch_idx":    first_idx,
                "last_touch_idx":     last_idx,
                "departure_strength": dep,
                "is_fresh":           touch_cnt < 3,
                "round_number":       is_round_number(center, self._cfg["round_number_tolerance_pct"] / 100),
                "daily_confluence":   False,
                "weekly_confluence":  False,
                "high_volume_node":   high_vol,
                "invalidated":        False,
                "timeframe":          timeframe,
            })

        return zones

    def _has_confluence(self, zone: dict, higher_tf: str) -> bool:
        for hz in self._zones.get(higher_tf, []):
            if hz["invalidated"]:
                continue
            if price_is_near_zone(zone["midpoint"], hz["zone_low"], hz["zone_high"], 0.005):
                return True
        return False


# ─── Scoring (used by confidence scorer) ─────────────────────────────────────

def score_zone(zone: dict, cfg: dict) -> int:
    score = 0
    tc = zone.get("touch_count", 0)

    if tc >= 3:
        score += 20
    elif tc == 2:
        score += 12

    if tc == 1:
        score += 10
    elif tc == 2:
        score += 5
    elif tc == 4:
        score -= 5

    if zone.get("departure_strength", 0) >= cfg.get("explosion_multiplier", 1.8):
        score += 10
    if zone.get("round_number"):
        score += 8
    if zone.get("weekly_confluence"):
        score += 15
    elif zone.get("daily_confluence"):
        score += 10
    if zone.get("high_volume_node"):
        score += 10

    return score
