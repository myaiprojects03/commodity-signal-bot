"""
alerts/email_notifier.py

Gmail SMTP email notifier.

Setup:
  1. Enable 2-Step Verification on your Google account.
  2. Go to: Google Account → Security → App Passwords
  3. Generate an App Password for "Mail"
  4. Set EMAIL_SENDER, EMAIL_PASSWORD, EMAIL_RECIPIENT in .env
  5. Optionally set EMAIL_SIGNAL_RECIPIENT for a second email that
     receives trade signals only (no 30-min summary reports).

No paid service needed. Works on PythonAnywhere free tier.
"""

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from utils.logger import get_logger

logger = get_logger(__name__)


class EmailNotifier:

    def __init__(self, config: dict) -> None:
        self._cfg              = config["email"]
        self._sender           = os.getenv("EMAIL_SENDER", "")
        self._password         = os.getenv("EMAIL_PASSWORD", "")
        self._recipient        = os.getenv("EMAIL_RECIPIENT", "")
        self._signal_recipient = os.getenv("EMAIL_SIGNAL_RECIPIENT", "")
        self._enabled          = self._cfg.get("enabled", True)

        if self._enabled and not all([self._sender, self._password, self._recipient]):
            logger.warning(
                "Email not fully configured. "
                "Set EMAIL_SENDER, EMAIL_PASSWORD, EMAIL_RECIPIENT in .env"
            )
            self._enabled = False

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
        Send an email. Returns True on success.

        is_signal=True  → sent to EMAIL_RECIPIENT + EMAIL_SIGNAL_RECIPIENT
        is_signal=False → sent to EMAIL_RECIPIENT only (reports, summaries)

        Sends both plain text and HTML (multipart/alternative).
        Falls back to plain text only if html_body is None.
        """
        if not self._enabled:
            logger.info("Email disabled — would have sent: %s", subject)
            return False

        # Build recipient list
        recipients = [self._recipient]
        if is_signal and self._signal_recipient:
            recipients.append(self._signal_recipient)

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"]    = self._sender
            msg["To"]      = ", ".join(recipients)

            msg.attach(MIMEText(plain_text, "plain", "utf-8"))
            if html_body:
                msg.attach(MIMEText(html_body, "html", "utf-8"))

            smtp_server = self._cfg.get("smtp_server", "smtp.gmail.com")
            smtp_port   = self._cfg.get("smtp_port", 587)

            with smtplib.SMTP(smtp_server, smtp_port, timeout=30) as server:
                server.ehlo()
                server.starttls()
                server.login(self._sender, self._password)
                server.sendmail(self._sender, recipients, msg.as_string())

            logger.info("Email sent: %s → %s", subject, ", ".join(recipients))
            return True

        except smtplib.SMTPAuthenticationError:
            logger.error(
                "Gmail auth failed. "
                "Use an App Password (not your main password). "
                "See: myaccount.google.com/apppasswords"
            )
            return False
        except smtplib.SMTPException as exc:
            logger.error("SMTP error: %s", exc)
            return False
        except Exception as exc:
            logger.error("Email send failed: %s", exc)
            return False

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