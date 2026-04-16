"""
alerts/email_notifier.py

Resend HTTP API email notifier.
Replaces Gmail SMTP (blocked on Railway free tier).

Setup:
  1. Sign up at resend.com and get an API key.
  2. Set RESEND_API_KEY in Railway environment variables.
  3. EMAIL_SENDER, EMAIL_RECIPIENT, EMAIL_SIGNAL_RECIPIENT still read from env.
"""

import os
import resend
from typing import Optional

from utils.logger import get_logger

logger = get_logger(__name__)


class EmailNotifier:

    def __init__(self, config: dict) -> None:
        self._cfg              = config["email"]
        self._sender           = os.getenv("EMAIL_SENDER", "")
        self._recipient        = os.getenv("EMAIL_RECIPIENT", "")
        self._signal_recipient = os.getenv("EMAIL_SIGNAL_RECIPIENT", "")
        self._enabled          = self._cfg.get("enabled", True)

        api_key = os.getenv("RESEND_API_KEY", "")
        if self._enabled and not all([api_key, self._recipient]):
            logger.warning(
                "Email not fully configured. "
                "Set RESEND_API_KEY and EMAIL_RECIPIENT in Railway variables."
            )
            self._enabled = False
        else:
            resend.api_key = api_key

        if self._signal_recipient:
            logger.info(
                "Signal recipient configured: %s "
                "(receives trade signals only, not reports)",
                self._signal_recipient,
            )

    def send(
        self,
        subject: str,
        plain_text: str,
        html_body: Optional[str] = None,
        is_signal: bool = False,
    ) -> bool:
        """
        Send an email via Resend HTTP API. Returns True on success.

        is_signal=True  → sent to EMAIL_RECIPIENT + EMAIL_SIGNAL_RECIPIENT
        is_signal=False → sent to EMAIL_RECIPIENT only (reports, summaries)
        """
        if not self._enabled:
            logger.info("Email disabled — would have sent: %s", subject)
            return False

        # Build recipient list
        recipients = [self._recipient]
        if is_signal and self._signal_recipient:
            recipients.append(self._signal_recipient)

        # Build HTML fallback if not provided
        body_html = html_body if html_body else f"<pre style='font-family:monospace'>{plain_text}</pre>"

        for to_addr in recipients:
            try:
                resend.Emails.send({
                    "from": "Commodity Bot <onboarding@resend.dev>",
                    "to": to_addr,
                    "subject": subject,
                    "html": body_html,
                })
                logger.info("Email sent: %s → %s", subject, to_addr)
            except Exception as exc:
                logger.error("Email send failed to %s: %s", to_addr, exc)
                return False

        return True

    def test_connection(self) -> bool:
        """Send a test email to verify credentials."""
        subject = "[Commodity Bot] Connection Test ✅"
        body    = (
            "Your Commodity Signal Bot email is working correctly.\n\n"
            "You will receive:\n"
            "  • Signal alerts when high-confidence setups are detected\n"
            "  • Status updates every 30 minutes\n\n"
            "Instruments monitored: Gold (GC=F), Silver (SI=F), WTI Oil (CL=F)\n"
        )
        return self.send(subject, body)