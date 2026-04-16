"""
storage/db.py

Lightweight SQLite database for signal logging and cooldown persistence.
Uses Python's built-in sqlite3 — no extra dependencies.
"""

import os
import sqlite3
import time
from datetime import datetime, timezone
from typing import List, Optional

from utils.logger import get_logger

logger = get_logger(__name__)


class SignalDatabase:

    def __init__(self, config: dict) -> None:
        self._path      = config["database"]["path"]
        self._retention = config["database"]["retention_days"]
        self._conn: Optional[sqlite3.Connection] = None

    def connect(self) -> None:
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        self._conn = sqlite3.connect(self._path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._create_tables()
        logger.info("Database connected: %s", self._path)

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def _create_tables(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS signals (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp   REAL    NOT NULL,
                symbol      TEXT    NOT NULL,
                name        TEXT    NOT NULL,
                signal_type TEXT    NOT NULL,
                direction   TEXT    NOT NULL,
                price       REAL    NOT NULL,
                score       INTEGER NOT NULL,
                label       TEXT    NOT NULL,
                timeframe   TEXT,
                rr_ratio    REAL,
                tp1         REAL,
                tp2         REAL,
                tp3         REAL,
                stop_loss   REAL,
                sent        INTEGER DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS events (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL    NOT NULL,
                event     TEXT    NOT NULL,
                detail    TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_signals_symbol ON signals(symbol);
            CREATE INDEX IF NOT EXISTS idx_signals_ts     ON signals(timestamp);
        """)
        self._conn.commit()

    def log_signal(
        self,
        symbol: str,
        name: str,
        signal_type: str,
        direction: str,
        price: float,
        score: int,
        label: str,
        timeframe: str = "",
        rr_ratio: float = 0.0,
        tp1: Optional[float] = None,
        tp2: Optional[float] = None,
        tp3: Optional[float] = None,
        stop_loss: Optional[float] = None,
    ) -> None:
        if not self._conn:
            return
        try:
            self._conn.execute(
                """INSERT INTO signals
                   (timestamp, symbol, name, signal_type, direction, price,
                    score, label, timeframe, rr_ratio, tp1, tp2, tp3, stop_loss)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (time.time(), symbol, name, signal_type, direction, price,
                 score, label, timeframe, rr_ratio, tp1, tp2, tp3, stop_loss),
            )
            self._conn.commit()
        except sqlite3.Error as exc:
            logger.error("DB log_signal error: %s", exc)

    def log_event(self, event: str, detail: str = "") -> None:
        if not self._conn:
            return
        try:
            self._conn.execute(
                "INSERT INTO events (timestamp, event, detail) VALUES (?,?,?)",
                (time.time(), event, detail),
            )
            self._conn.commit()
        except sqlite3.Error as exc:
            logger.error("DB log_event error: %s", exc)

    def get_recent_signals(self, hours: int = 24) -> List[dict]:
        if not self._conn:
            return []
        since = time.time() - hours * 3600
        rows  = self._conn.execute(
            "SELECT * FROM signals WHERE timestamp > ? ORDER BY timestamp DESC",
            (since,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_daily_summary(self) -> dict:
        signals = self.get_recent_signals(24)
        buys    = [s for s in signals if s["direction"] == "buy"]
        sells   = [s for s in signals if s["direction"] == "sell"]
        avg_sc  = sum(s["score"] for s in signals) / len(signals) if signals else 0
        top     = max(signals, key=lambda s: s["score"]) if signals else None
        return {
            "total":   len(signals),
            "buys":    len(buys),
            "sells":   len(sells),
            "avg_score": round(avg_sc, 1),
            "top_signal": top,
        }

    def cleanup(self) -> None:
        if not self._conn:
            return
        cutoff = time.time() - self._retention * 86400
        try:
            self._conn.execute("DELETE FROM signals WHERE timestamp < ?", (cutoff,))
            self._conn.execute("DELETE FROM events  WHERE timestamp < ?", (cutoff,))
            self._conn.commit()
            logger.info("Database cleanup complete (retention: %d days)", self._retention)
        except sqlite3.Error as exc:
            logger.error("DB cleanup error: %s", exc)
