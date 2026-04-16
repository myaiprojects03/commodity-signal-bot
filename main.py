"""
main.py

Entry point for Commodity Signal Bot.

Usage:
  python main.py              # Run the bot (scheduled every 30 minutes)
  python main.py --test       # Run one cycle immediately and print output
  python main.py --email-test # Send a test email to verify credentials

Deployment (PythonAnywhere free tier):
  1. Upload files to PythonAnywhere
  2. Set .env credentials
  3. pip install -r requirements.txt --user
  4. Add scheduled task: python /path/to/main.py (every 30 min)
     OR run: python main.py (runs forever with built-in scheduler)
"""

import argparse
import os
import sys
import time

import schedule
import yaml
from dotenv import load_dotenv

from utils.logger import configure_root_logger, get_logger


# ─────────────────────────────────────────────────────────────────────────────
# Config Loading
# ─────────────────────────────────────────────────────────────────────────────

def load_config(path: str = "config.yaml") -> dict:
    if not os.path.exists(path):
        print(f"ERROR: config.yaml not found at {path}", file=sys.stderr)
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    if not isinstance(config, dict):
        print("ERROR: config.yaml is invalid.", file=sys.stderr)
        sys.exit(1)
    return config


def validate_config(config: dict) -> None:
    required = ["instruments", "timeframes", "indicators", "support_resistance",
                "trend", "risk_reward", "signals", "sessions", "email",
                "database", "scheduler"]
    missing = [s for s in required if s not in config]
    if missing:
        print(f"ERROR: Missing config sections: {missing}", file=sys.stderr)
        sys.exit(1)
    if not config.get("instruments"):
        print("ERROR: No instruments configured.", file=sys.stderr)
        sys.exit(1)


# ─────────────────────────────────────────────────────────────────────────────
# Modes
# ─────────────────────────────────────────────────────────────────────────────

def run_live(config: dict) -> None:
    """Start the bot with a 30-minute schedule loop."""
    from core.engine import SignalEngine

    logger = get_logger("main")
    logger.info("Starting Commodity Signal Bot — Live Mode")
    logger.info(
        "Instruments: %s",
        ", ".join(i["name"] for i in config["instruments"])
    )
    logger.info(
        "Signal interval: every %d minutes",
        config["scheduler"]["run_interval_minutes"]
    )

    engine = SignalEngine(config)

    interval = config["scheduler"]["run_interval_minutes"]

    # Run immediately on startup
    logger.info("Running initial cycle...")
    try:
        engine.run()
    except Exception as exc:
        logger.error("Initial cycle error: %s", exc, exc_info=True)

    # Schedule recurring runs
    schedule.every(interval).minutes.do(_safe_run, engine)

    logger.info("Scheduler active. Running every %d minutes. Press Ctrl+C to stop.", interval)

    try:
        while True:
            schedule.run_pending()
            time.sleep(30)
    except KeyboardInterrupt:
        logger.info("Shutdown requested.")
    finally:
        engine.shutdown()
        logger.info("Bot stopped.")


def run_test(config: dict) -> None:
    """Run one cycle immediately with full console output."""
    from core.engine import SignalEngine

    print("\n" + "=" * 50)
    print("  COMMODITY SIGNAL BOT — TEST MODE")
    print("=" * 50)
    print("Running one analysis cycle...\n")

    engine = SignalEngine(config)
    engine.run()
    engine.shutdown()

    print("\nTest cycle complete.")


def run_email_test(config: dict) -> None:
    """Send a test email to verify Gmail credentials."""
    from alerts.email_notifier import EmailNotifier

    print("\nSending test email...")
    notifier = EmailNotifier(config)
    success  = notifier.test_connection()

    if success:
        print("✅ Test email sent successfully!")
        print(f"   Check inbox: {os.getenv('EMAIL_RECIPIENT', '(not set)')}")
    else:
        print("❌ Test email FAILED.")
        print("   Check EMAIL_SENDER, EMAIL_PASSWORD, EMAIL_RECIPIENT in .env")
        print("   Use Gmail App Password (not your main password).")
        print("   Setup: myaccount.google.com/apppasswords")


def _safe_run(engine) -> None:
    """Wrapper that catches errors so the scheduler keeps running."""
    logger = get_logger("scheduler")
    try:
        engine.run()
    except Exception as exc:
        logger.error("Cycle error: %s", exc, exc_info=True)


# ─────────────────────────────────────────────────────────────────────────────
# Entry Point
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Commodity Signal Bot — Gold, Silver, WTI Oil"
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Run one cycle immediately (no scheduler, full console output)",
    )
    parser.add_argument(
        "--email-test",
        action="store_true",
        help="Send a test email to verify Gmail credentials",
    )
    args = parser.parse_args()

    config = load_config("config.yaml")
    validate_config(config)

    log_file = (
        config["system"]["log_file_path"]
        if config["system"].get("log_to_file")
        else None
    )
    configure_root_logger(
        log_file=log_file,
        level=config["system"].get("log_level", "INFO"),
    )

    if args.email_test:
        run_email_test(config)
    elif args.test:
        run_test(config)
    else:
        run_live(config)


if __name__ == "__main__":
    main()
