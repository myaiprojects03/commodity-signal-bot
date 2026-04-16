"""
data/fetcher.py  — Binance REST backend

Symbols:
  GC=F  → XAUUSDT  (Gold vs USDT, Binance Futures)
  SI=F  → XAGUSDT  (Silver vs USDT, Binance Futures)

No API key required.
"""

import time
import requests
from typing import Dict, List, Optional

from utils.logger import get_logger

logger = get_logger(__name__)

_BINANCE_SYMBOLS = {
    "GC=F": "XAUUSDT",
    "SI=F": "XAGUSDT",
}

_BINANCE_INTERVALS = {
    "15m": "15m",
    "1h":  "1h",
    "1d":  "1d",
    "1wk": "1w",
}

_BAR_COUNTS = {
    "15m": 500,
    "1h":  500,
    "1d":  365,
    "1wk": 104,
}

_BINANCE_KLINES  = "https://fapi.binance.com/fapi/v1/klines"
_BINANCE_TICKER  = "https://fapi.binance.com/fapi/v1/ticker/24hr"


def build_candle(open_time, open_price, high, low, close, volume):
    return {
        "open_time": open_time,
        "open":      open_price,
        "high":      high,
        "low":       low,
        "close":     close,
        "volume":    volume,
    }


class DataFetcher:
    """
    Fetches OHLCV candles + 24h ticker stats using Binance Futures public REST API.
    No API key required.
    """

    def __init__(self, config: dict) -> None:
        self._cfg = config
        self._cache: Dict[str, Dict[str, List[dict]]] = {}
        self._ticker_cache: Dict[str, dict] = {}   # 24h stats keyed by symbol

    # ── Public API ────────────────────────────────────────────────────────────

    def fetch_all(self, instruments: list, timeframes: list) -> None:
        """Fetch OHLCV candles + 24h ticker for every instrument."""
        for inst in instruments:
            symbol = inst["symbol"]
            self._cache.setdefault(symbol, {})

            # Fetch 24h ticker first (single fast call)
            ticker = self._fetch_ticker(symbol)
            if ticker:
                self._ticker_cache[symbol] = ticker
                logger.info("Fetched 24h ticker: %s", symbol)

            # Fetch candles per timeframe
            for tf in timeframes:
                candles = self._fetch(symbol, tf)
                if candles:
                    self._cache[symbol][tf] = candles
                    logger.info("Fetched %d candles: %s / %s", len(candles), symbol, tf)
                else:
                    logger.warning("No data returned: %s / %s", symbol, tf)
                time.sleep(0.3)

    def get_candles(self, symbol: str, timeframe: str, count: Optional[int] = None) -> List[dict]:
        candles = self._cache.get(symbol, {}).get(timeframe, [])
        if count:
            return candles[-count:]
        return candles

    def get_current_price(self, symbol: str) -> Optional[float]:
        for tf in ("1h", "15m"):
            candles = self._cache.get(symbol, {}).get(tf, [])
            if candles:
                return candles[-1]["close"]
        return None

    def get_ticker_24h(self, symbol: str) -> dict:
        """
        Returns 24h stats dict with keys:
          high_24h, low_24h, volume_24h, quote_volume_24h,
          price_change_24h, price_change_pct_24h, open_24h,
          last_price, count_24h
        Returns empty dict if unavailable.
        """
        return self._ticker_cache.get(symbol, {})

    def aggregate_to_4h(self, symbol: str) -> List[dict]:
        candles_1h = self._cache.get(symbol, {}).get("1h", [])
        if len(candles_1h) < 4:
            return []
        result = []
        for i in range(0, len(candles_1h) - (len(candles_1h) % 4), 4):
            group = candles_1h[i:i + 4]
            if len(group) < 4:
                break
            result.append(build_candle(
                open_time  = group[0]["open_time"],
                open_price = group[0]["open"],
                high       = max(c["high"] for c in group),
                low        = min(c["low"]  for c in group),
                close      = group[-1]["close"],
                volume     = sum(c["volume"] for c in group),
            ))
        return result

    # ── Private ───────────────────────────────────────────────────────────────

    def _fetch(self, symbol: str, interval: str) -> List[dict]:
        binance_sym = _BINANCE_SYMBOLS.get(symbol)
        if binance_sym is None:
            logger.warning("No Binance mapping for %s — skipping", symbol)
            return []

        binance_interval = _BINANCE_INTERVALS.get(interval)
        if not binance_interval:
            logger.warning("Unsupported interval %s — skipping", interval)
            return []

        limit = _BAR_COUNTS.get(interval, 300)

        try:
            resp = requests.get(
                _BINANCE_KLINES,
                params={"symbol": binance_sym, "interval": binance_interval, "limit": limit},
                timeout=10,
            )
            resp.raise_for_status()
            raw = resp.json()

            if not raw:
                logger.warning("Empty response for %s / %s", symbol, interval)
                return []

            candles = []
            for k in raw:
                candles.append(build_candle(
                    open_time  = int(k[0]) // 1000,
                    open_price = float(k[1]),
                    high       = float(k[2]),
                    low        = float(k[3]),
                    close      = float(k[4]),
                    volume     = float(k[5]),
                ))

            # Drop last in-progress candle for intraday
            if len(candles) > 1 and interval in ("15m", "1h"):
                candles = candles[:-1]

            return candles

        except Exception as exc:
            logger.error("Binance kline error %s / %s: %s", symbol, interval, exc)
            return []

    def _fetch_ticker(self, symbol: str) -> dict:
        """Fetch 24h rolling ticker stats from Binance Futures."""
        binance_sym = _BINANCE_SYMBOLS.get(symbol)
        if not binance_sym:
            return {}
        try:
            resp = requests.get(
                _BINANCE_TICKER,
                params={"symbol": binance_sym},
                timeout=10,
            )
            resp.raise_for_status()
            t = resp.json()
            return {
                "high_24h":            float(t.get("highPrice", 0) or 0),
                "low_24h":             float(t.get("lowPrice",  0) or 0),
                "volume_24h":          float(t.get("volume",    0) or 0),
                "quote_volume_24h":    float(t.get("quoteVolume", 0) or 0),
                "price_change_24h":    float(t.get("priceChange", 0) or 0),
                "price_change_pct_24h": float(t.get("priceChangePercent", 0) or 0),
                "open_24h":            float(t.get("openPrice", 0) or 0),
                "last_price":          float(t.get("lastPrice", 0) or 0),
                "count_24h":           int(t.get("count", 0) or 0),
                "weighted_avg_price":  float(t.get("weightedAvgPrice", 0) or 0),
            }
        except Exception as exc:
            logger.error("Binance ticker error %s: %s", symbol, exc)
            return {}
