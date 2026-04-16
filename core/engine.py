"""
core/engine.py  — Main signal engine (updated with 24h stats + detailed reports).
"""

import time
from datetime import datetime, timezone
from typing import Optional

from alerts.cooldown        import CooldownManager
from alerts.email_notifier  import EmailNotifier
from alerts.formatter       import AlertFormatter
from analysis.candle_patterns   import CandlePatternDetector
from analysis.confidence_scorer import ConfidenceScorer
from analysis.indicators    import compute_indicators
from analysis.liquidity     import LiquidityAnalyzer, score_liquidity
from analysis.risk_reward   import RiskRewardEngine
from analysis.session       import SessionClassifier
from analysis.support_resistance import SupportResistanceDetector
from analysis.trend         import TrendAnalyzer
from data.fetcher           import DataFetcher
from storage.db             import SignalDatabase
from utils.helpers          import calculate_atr
from utils.logger           import get_logger

logger = get_logger(__name__)


class SignalEngine:

    def __init__(self, config: dict) -> None:
        self._cfg = config

        instruments = config["instruments"]
        symbols     = [i["symbol"] for i in instruments]

        self._fetcher = DataFetcher(config)

        self._sr:    dict = {sym: SupportResistanceDetector(sym, config) for sym in symbols}
        self._trend: dict = {sym: TrendAnalyzer(sym, config) for sym in symbols}

        self._patterns  = CandlePatternDetector(config)
        self._liquidity = LiquidityAnalyzer(config)
        self._session   = SessionClassifier(config)
        self._rr        = RiskRewardEngine(config)
        self._scorer    = ConfidenceScorer(config)

        self._formatter = AlertFormatter(config)
        self._notifier  = EmailNotifier(config)
        self._cooldown  = CooldownManager(config)
        self._db        = SignalDatabase(config)

        self._db.connect()
        self._db.log_event("startup", "Commodity Signal Bot started.")

    def run(self) -> None:
        run_time = datetime.now(timezone.utc)
        logger.info("=" * 50)
        logger.info("Cycle start: %s", run_time.strftime("%Y-%m-%d %H:%M UTC"))

        instruments = self._cfg["instruments"]
        timeframes  = ["15m", "1h", "1d", "1wk"]

        logger.info("Fetching market data...")
        self._fetcher.fetch_all(instruments, timeframes)

        run_results = []

        for inst in instruments:
            symbol = inst["symbol"]
            name   = inst["name"]
            logger.info("Analysing: %s (%s)", name, symbol)

            try:
                result = self._analyse_instrument(inst)
                run_results.append(result)
            except Exception as exc:
                logger.error("Error analysing %s: %s", symbol, exc, exc_info=True)
                run_results.append({
                    "name":        name,
                    "symbol":      symbol,
                    "price":       0,
                    "status":      "ERROR: {}".format(exc),
                    "signal_sent": None,
                })

        # Summary report — goes to your email only (is_signal=False by default)
        subject, plain, html = self._formatter.format_summary_email(run_results, run_time)
        self._notifier.send(subject, plain, html)

        logger.info("Cycle complete. Instruments processed: %d", len(run_results))

    def _analyse_instrument(self, instrument: dict) -> dict:
        symbol = instrument["symbol"]
        name   = instrument["name"]

        candles_15m = self._fetcher.get_candles(symbol, "15m")
        candles_1h  = self._fetcher.get_candles(symbol, "1h")
        candles_4h  = self._fetcher.aggregate_to_4h(symbol)
        candles_1d  = self._fetcher.get_candles(symbol, "1d")
        candles_1wk = self._fetcher.get_candles(symbol, "1wk")
        ticker_24h  = self._fetcher.get_ticker_24h(symbol)

        if not candles_1h:
            logger.warning("No 1H candles for %s", symbol)
            return {"name": name, "symbol": symbol, "price": 0,
                    "status": "No data", "signal_sent": None}

        current_price = candles_1h[-1]["close"]

        candles_by_tf = {}
        if candles_1d:  candles_by_tf["1d"]  = candles_1d
        if candles_1wk: candles_by_tf["1wk"] = candles_1wk
        if candles_4h:  candles_by_tf["4h"]  = candles_4h
        if candles_1h:  candles_by_tf["1h"]  = candles_1h

        sr = self._sr[symbol]
        sr.refresh(candles_by_tf)

        for z in sr.get_all_zones("1h"):
            sr.enrich_confluence(z, ["1d", "1wk"])
        for z in sr.get_all_zones("4h"):
            sr.enrich_confluence(z, ["1d", "1wk"])

        if candles_1h:
            sr.update_invalidations(candles_1h[-1], "1h")
        if candles_4h:
            sr.update_invalidations(candles_4h[-1], "4h")

        trend_tfs = {}
        if candles_1wk: trend_tfs["1wk"] = candles_1wk
        if candles_1d:  trend_tfs["1d"]  = candles_1d
        if candles_4h:  trend_tfs["4h"]  = candles_4h
        if candles_1h:  trend_tfs["1h"]  = candles_1h

        ta = self._trend[symbol]
        ta.analyse(trend_tfs)

        indicators_1h  = compute_indicators(candles_1h, self._cfg)
        indicators_15m = {}
        if candles_15m:
            indicators_15m = compute_indicators(candles_15m, self._cfg)

        atr = indicators_1h.get("atr") or calculate_atr(
            [c["high"]  for c in candles_1h[-30:]],
            [c["low"]   for c in candles_1h[-30:]],
            [c["close"] for c in candles_1h[-30:]],
        )

        zone      = sr.get_zone_at_price(current_price, "1h", atr=atr)
        sup_zone  = sr.get_nearest_support(current_price, "1h")
        res_zone  = sr.get_nearest_resistance(current_price, "1h")
        direction = _determine_direction(zone)

        trend_bias_buy = ta.get_bias("buy")
        w_dir  = trend_bias_buy.get("weekly", {}).get("direction", "range")
        d_dir  = trend_bias_buy.get("daily",  {}).get("direction", "range")
        h4_dir = trend_bias_buy.get("h4",     {}).get("direction", "range")
        session = self._session.classify()
        atr_val = indicators_1h.get("atr")

        pattern_1h = None
        if len(candles_1h) >= 3:
            pattern_1h = self._patterns.detect(candles_1h[-3:])

        base_result = {
            "name":         name,
            "symbol":       symbol,
            "price":        current_price,
            "weekly_trend": w_dir,
            "daily_trend":  d_dir,
            "h4_trend":     h4_dir,
            "status":       "OK",
            "signal_sent":  None,
            "zone":         zone,
            "sup_zone":     sup_zone,
            "res_zone":     res_zone,
            "direction":    direction,
            "atr":          atr_val,
            "rsi":          indicators_1h.get("rsi"),
            "macd":         indicators_1h.get("macd"),
            "macd_hist":    indicators_1h.get("macd_hist"),
            "ema20":        indicators_1h.get("ema20"),
            "ema50":        indicators_1h.get("ema50"),
            "ema200":       indicators_1h.get("ema200"),
            "ema_bullish":  indicators_1h.get("ema_bullish"),
            "ema_bearish":  indicators_1h.get("ema_bearish"),
            "bb_upper":     indicators_1h.get("bb_upper"),
            "bb_lower":     indicators_1h.get("bb_lower"),
            "stoch_k":      indicators_1h.get("stoch_k"),
            "vol_ratio":    indicators_1h.get("vol_ratio"),
            "session":      session.get("session", "unknown"),
            "pattern":      pattern_1h,
            "ticker_24h":   ticker_24h,
        }

        if direction is None:
            logger.debug("%s: Price mid-range — no zone", symbol)
            base_result["status"] = "Mid-range"
            base_result["zone"]   = None
            return base_result

        trend_bias = ta.get_bias(direction)

        signal_sent = self._run_pipeline(
            instrument    = instrument,
            direction     = direction,
            current_price = current_price,
            zone          = zone,
            sup_zone      = sup_zone,
            res_zone      = res_zone,
            trend_bias    = trend_bias,
            indicators    = indicators_1h,
            candles_1h    = candles_1h,
            candles_4h    = candles_4h,
            sr            = sr,
            atr           = atr,
            timeframe     = "1h",
        )

        if signal_sent:
            base_result["signal_sent"] = "{} ({}/100)".format(direction.upper(), signal_sent)
            return base_result

        if candles_15m:
            price_15m = candles_15m[-1]["close"]
            zone_15m  = sr.get_zone_at_price(price_15m, "1h", atr=atr)
            dir_15m   = _determine_direction(zone_15m)

            if dir_15m:
                tb_15m = ta.get_bias(dir_15m)
                signal_sent = self._run_pipeline(
                    instrument    = instrument,
                    direction     = dir_15m,
                    current_price = price_15m,
                    zone          = zone_15m,
                    sup_zone      = sup_zone,
                    res_zone      = res_zone,
                    trend_bias    = tb_15m,
                    indicators    = indicators_15m,
                    candles_1h    = candles_15m,
                    candles_4h    = candles_4h,
                    sr            = sr,
                    atr           = atr,
                    timeframe     = "15m",
                )
                if signal_sent:
                    base_result["signal_sent"] = "{} ({}/100) [15m]".format(dir_15m.upper(), signal_sent)

        return base_result

    def _run_pipeline(
        self, instrument, direction, current_price,
        zone, sup_zone, res_zone, trend_bias, indicators,
        candles_1h, candles_4h, sr, atr, timeframe,
    ) -> Optional[int]:
        symbol = instrument["symbol"]

        pattern  = self._patterns.detect(candles_1h[-3:] if len(candles_1h) >= 3 else candles_1h)
        session  = self._session.classify()

        candles_for_liq = candles_4h if candles_4h else candles_1h
        liquidity = self._liquidity.analyse(candles_for_liq, current_price)

        all_zones = sr.get_all_zones("1h")
        sup_list  = [z for z in all_zones if z["type"] == "support"]
        res_list  = [z for z in all_zones if z["type"] == "resistance"]

        if zone:
            rr_result = self._rr.calculate(
                direction        = direction,
                entry            = current_price,
                zone             = zone,
                atr              = atr,
                support_zones    = sup_list,
                resistance_zones = res_list,
            )
        else:
            return None

        scoring = self._scorer.score(
            direction       = direction,
            zone            = zone,
            support_zone    = sup_zone,
            resistance_zone = res_zone,
            trend_bias      = trend_bias,
            pattern_result  = pattern,
            indicators      = indicators,
            session_result  = session,
            rr_result       = rr_result,
            current_price   = current_price,
            candles         = candles_1h,
        )

        if scoring.get("discard"):
            logger.debug("%s %s DISCARDED: %s", symbol, direction.upper(), scoring.get("discard_reason"))
            return None

        if self._cooldown.is_active(symbol, direction):
            rem = self._cooldown.remaining_minutes(symbol, direction)
            logger.debug("%s %s cooldown active (%.0f min remaining)", symbol, direction, rem)
            return None

        subject, plain, html = self._formatter.format_email(
            instrument       = instrument,
            current_price    = current_price,
            direction        = direction,
            scoring_result   = scoring,
            zone             = zone,
            support_zone     = sup_zone,
            resistance_zone  = res_zone,
            trend_bias       = trend_bias,
            pattern_result   = pattern,
            indicators       = indicators,
            liquidity_result = liquidity,
            session_result   = session,
            rr_result        = rr_result,
            timeframe        = timeframe,
        )

        # ── CHANGE: is_signal=True sends to both your email + Imran Ali's email ──
        sent = self._notifier.send(subject, plain, html, is_signal=True)

        if sent:
            self._cooldown.record(symbol, direction)
            self._db.log_signal(
                symbol      = symbol,
                name        = instrument["name"],
                signal_type = scoring.get("signal_type", "WATCH"),
                direction   = direction,
                price       = current_price,
                score       = scoring.get("score", 0),
                label       = scoring.get("label", "MODERATE"),
                timeframe   = timeframe,
                rr_ratio    = rr_result.get("rr_ratio", 0),
                tp1         = rr_result.get("tp1"),
                tp2         = rr_result.get("tp2"),
                tp3         = rr_result.get("tp3"),
                stop_loss   = rr_result.get("stop_loss"),
            )
            logger.info(
                "Signal sent: %s %s | %d/100 [%s] | R:R %.1f | $%.2f",
                symbol, scoring.get("signal_type"),
                scoring.get("score"), scoring.get("label"),
                rr_result.get("rr_ratio", 0), current_price,
            )
            return scoring.get("score")

        return None

    def shutdown(self) -> None:
        self._db.log_event("shutdown", "System shutdown.")
        self._db.cleanup()
        self._db.close()
        logger.info("Engine shutdown complete.")


def _determine_direction(zone):
    if zone is None:
        return None
    if zone["type"] == "support":
        return "buy"
    if zone["type"] == "resistance":
        return "sell"
    return None