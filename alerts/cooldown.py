"""alerts/cooldown.py — Signal cooldown manager."""

import time
from typing import Dict, Tuple
from utils.logger import get_logger

logger = get_logger(__name__)


class CooldownManager:

    def __init__(self, config: dict) -> None:
        self._minutes = config["signals"]["cooldown_minutes"]
        # key: (symbol, direction) → last_sent_timestamp
        self._store: Dict[Tuple[str, str], float] = {}

    def is_active(self, symbol: str, direction: str) -> bool:
        key  = (symbol, direction)
        last = self._store.get(key)
        if last is None:
            return False
        elapsed = (time.time() - last) / 60
        return elapsed < self._minutes

    def record(self, symbol: str, direction: str) -> None:
        self._store[(symbol, direction)] = time.time()
        logger.debug("Cooldown set: %s %s (%d min)", symbol, direction, self._minutes)

    def remaining_minutes(self, symbol: str, direction: str) -> float:
        key  = (symbol, direction)
        last = self._store.get(key)
        if last is None:
            return 0.0
        elapsed = (time.time() - last) / 60
        return max(0.0, self._minutes - elapsed)

    def active_cooldowns(self) -> list:
        result = []
        for (sym, dirn), ts in self._store.items():
            rem = self.remaining_minutes(sym, dirn)
            if rem > 0:
                result.append({
                    "symbol":             sym,
                    "direction":          dirn,
                    "remaining_minutes":  rem,
                })
        return result
