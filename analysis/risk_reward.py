"""analysis/risk_reward.py — SL/TP/RR engine with 3 take-profit levels."""

from typing import List, Optional
from utils.logger import get_logger

logger = get_logger(__name__)


class RiskRewardEngine:

    def __init__(self, config: dict) -> None:
        self._cfg = config["risk_reward"]

    def calculate(
        self,
        direction: str,
        entry: float,
        zone: dict,
        atr: float,
        support_zones: List[dict],
        resistance_zones: List[dict],
    ) -> dict:
        """
        Calculate SL and 3 TP levels.

        SL:  placed beyond zone boundary + 0.5×ATR buffer
        TP1: nearest S/R level (conservative)
        TP2: next S/R level (standard)
        TP3: major level (extended / trend run)
        """
        buf = atr * self._cfg["sl_atr_buffer_multiplier"]

        if direction == "buy":
            sl = zone["zone_low"] - buf
            tps = self._find_tps_buy(entry, resistance_zones, atr)
        else:
            sl = zone["zone_high"] + buf
            tps = self._find_tps_sell(entry, support_zones, atr)

        tp1 = tps[0] if len(tps) > 0 else None
        tp2 = tps[1] if len(tps) > 1 else None
        tp3 = tps[2] if len(tps) > 2 else None

        risk = abs(entry - sl)
        if risk == 0:
            return _discard_rr("zero risk distance")

        rr1 = abs(tp1 - entry) / risk if tp1 else 0
        rr2 = abs(tp2 - entry) / risk if tp2 else 0
        rr3 = abs(tp3 - entry) / risk if tp3 else 0
        rr_ratio = rr1  # primary R:R based on TP1

        min_rr = self._cfg["min_rr_ratio"]
        if rr_ratio < min_rr and rr_ratio > 0:
            return _discard_rr(f"R:R {rr_ratio:.2f} below minimum {min_rr}")

        if rr_ratio >= self._cfg["high_rr_ratio"]:
            quality = "HIGH"
            score   = 10
        elif rr_ratio >= self._cfg["standard_rr_ratio"]:
            quality = "STANDARD"
            score   = 5
        elif rr_ratio >= min_rr:
            quality = "CAUTION"
            score   = 0
        else:
            return _discard_rr(f"R:R {rr_ratio:.2f} below minimum")

        return {
            "entry":      entry,
            "stop_loss":  sl,
            "tp1":        tp1,
            "tp2":        tp2,
            "tp3":        tp3,
            "rr_ratio":   round(rr_ratio, 2),
            "rr_quality": quality,
            "score":      score,
            "discard":    False,
            "discard_reason": "",
        }

    def _find_tps_buy(self, entry, resistance_zones, atr) -> list:
        """Find up to 3 TP levels above entry from resistance zones + ATR multiples."""
        targets = sorted(
            [z["midpoint"] for z in resistance_zones if z["midpoint"] > entry],
        )
        # Fill missing TPs with ATR multiples
        if not targets:
            return [entry + atr * 2, entry + atr * 3.5, entry + atr * 6]
        if len(targets) == 1:
            targets += [targets[0] + atr * 1.5, targets[0] + atr * 3]
        if len(targets) == 2:
            targets.append(targets[1] + atr * 2)
        return targets[:3]

    def _find_tps_sell(self, entry, support_zones, atr) -> list:
        """Find up to 3 TP levels below entry from support zones + ATR multiples."""
        targets = sorted(
            [z["midpoint"] for z in support_zones if z["midpoint"] < entry],
            reverse=True,
        )
        if not targets:
            return [entry - atr * 2, entry - atr * 3.5, entry - atr * 6]
        if len(targets) == 1:
            targets += [targets[0] - atr * 1.5, targets[0] - atr * 3]
        if len(targets) == 2:
            targets.append(targets[1] - atr * 2)
        return targets[:3]


def _discard_rr(reason: str) -> dict:
    return {
        "entry": 0, "stop_loss": 0,
        "tp1": None, "tp2": None, "tp3": None,
        "rr_ratio": 0, "rr_quality": "DISCARD",
        "score": 0, "discard": True,
        "discard_reason": reason,
    }


def format_rr_label(rr: dict) -> str:
    ratio   = rr.get("rr_ratio", 0)
    quality = rr.get("rr_quality", "")
    tag = {"HIGH": "★★★", "STANDARD": "★★", "CAUTION": "★", "DISCARD": "✗"}.get(quality, "")
    return f"{ratio:.1f}:1  {tag}"
