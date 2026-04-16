"""
alerts/email_notifier.py

Gmail OAuth2 email notifier.
Uses Gmail REST API over HTTPS — works on Railway free tier.
"""

import os
import base64
import json
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

import requests
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

from utils.logger import get_logger

logger = get_logger(__name__)


def _get_credentials() -> Credentials:
    creds = Credentials(
        token=None,
        refresh_token=os.getenv("GMAIL_REFRESH_TOKEN"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.getenv("GMAIL_CLIENT_ID"),
        client_secret=os.getenv("GMAIL_CLIENT_SECRET"),
        scopes=["https://www.googleapis.com/auth/gmail.send"],
    )
    creds.refresh(Request())
    return creds


class EmailNotifier:

    def __init__(self, config: dict) -> None:
        self._cfg              = config["email"]
        self._sender           = os.getenv("EMAIL_SENDER", "")
        self._recipient        = os.getenv("EMAIL_RECIPIENT", "")
        self._signal_recipient = os.getenv("EMAIL_SIGNAL_RECIPIENT", "")
        self._enabled          = self._cfg.get("enabled", True)

        required = [
            os.getenv("GMAIL_CLIENT_ID"),
            os.getenv("GMAIL_CLIENT_SECRET"),
            os.getenv("GMAIL_REFRESH_TOKEN"),
            self._recipient,
        ]
        if self._enabled and not all(required):
            logger.warning(
                "Email not fully configured. "
                "Set GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, "
                "GMAIL_REFRESH_TOKEN, EMAIL_RECIPIENT in Railway variables."
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
        if not self._enabled:
            logger.info("Email disabled — would have sent: %s", subject)
            return False

        recipients = [self._recipient]
        if is_signal and self._signal_recipient:
            recipients.append(self._signal_recipient)

        body_html = html_body if html_body else f"<pre style='font-family:monospace'>{plain_text}</pre>"

        try:
            creds = _get_credentials()
        except Exception as exc:
            logger.error("OAuth token refresh failed: %s", exc)
            return False

        for to_addr in recipients:
            try:
                msg = MIMEMultipart("alternative")
                msg["Subject"] = subject
                msg["From"]    = self._sender
                msg["To"]      = to_addr
                msg.attach(MIMEText(plain_text, "plain", "utf-8"))
                msg.attach(MIMEText(body_html, "html", "utf-8"))

                raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()

                response = requests.post(
                    f"https://gmail.googleapis.com/gmail/v1/users/{self._sender}/messages/send",
                    headers={
                        "Authorization": f"Bearer {creds.token}",
                        "Content-Type": "application/json",
                    },
                    json={"raw": raw},
                    timeout=30,
                )

                if response.status_code == 200:
                    logger.info("Email sent: %s → %s", subject, to_addr)
                else:
                    logger.error("Gmail API error to %s: %s", to_addr, response.text)
                    return False

            except Exception as exc:
                logger.error("Email send failed to %s: %s", to_addr, exc)
                return False

        return True

    def test_connection(self) -> bool:
        subject = "[Commodity Bot] Connection Test ✅"
        body    = (
            "Your Commodity Signal Bot email is working correctly.\n\n"
            "You will receive:\n"
            "  • Signal alerts when high-confidence setups are detected\n"
            "  • Status updates every 30 minutes\n\n"
            "Instruments monitored: Gold (GC=F), Silver (SI=F), WTI Oil (CL=F)\n"
        )
        return self.send(subject, body)