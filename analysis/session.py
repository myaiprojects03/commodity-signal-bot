"""
analysis/session.py

Session classifier for commodities (COMEX/NYMEX).
NY session is most liquid for Gold, Silver, WTI Oil.
"""

from datetime import datetime, timezone
from utils.logger import get_logger

logger = get_logger(__name__)


class SessionClassifier:

    def __init__(self, config: dict) -> None:
        self._sessions = config["sessions"]

    def classify(self) -> dict:
        now      = datetime.now(timezone.utc)
        hour_min = now.hour * 60 + now.minute

        for name, cfg in self._sessions.items():
            start_h, start_m = map(int, cfg["start"].split(":"))
            end_h,   end_m   = map(int, cfg["end"].split(":"))
            start_t = start_h * 60 + start_m
            end_t   = end_h   * 60 + end_m

            # Handle dead_zone that wraps midnight
            if start_t > end_t:
                in_session = hour_min >= start_t or hour_min < end_t
            else:
                in_session = start_t <= hour_min < end_t

            if in_session:
                adj     = cfg["score_adjustment"]
                discard = adj <= -999
                return {
                    "session":        name,
                    "score_adjustment": adj,
                    "discard":        discard,
                    "discard_reason": f"Dead zone session ({name}) — no commodity signals",
                    "utc_hour":       now.hour,
                    "utc_minute":     now.minute,
                }

        return {
            "session":        "unknown",
            "score_adjustment": 0,
            "discard":        False,
            "discard_reason": "",
            "utc_hour":       now.hour,
            "utc_minute":     now.minute,
        }


def format_session_label(result: dict) -> str:
    name = result.get("session", "Unknown").replace("_", " ").title()
    adj  = result.get("score_adjustment", 0)
    sign = "+" if adj >= 0 else ""
    return f"{name} ({sign}{adj} pts)"
