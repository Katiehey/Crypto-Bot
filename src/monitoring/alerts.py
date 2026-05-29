import datetime
import logging
import os
import requests
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class AlertManager:
    """Routes structured alerts to local logs and Telegram.

    Credentials are read from TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID env vars.
    If either is absent, Telegram delivery is silently skipped.
    """

    def __init__(self, logger: logging.Logger):
        self.logger = logger
        # Read secrets from environment
        self.telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID")

        if not self.telegram_token or not self.chat_id:
            self.logger.warning(
                "Telegram alerts disabled: missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID"
            )

    def send(self, level: str, message: str, include_info: bool = True):
        """Log an alert locally and forward it to Telegram if the level warrants it.

        Args:
            level: Severity string — INFO, WARNING, ERROR, or CRITICAL.
            message: Human-readable alert body.
            include_info: When True, INFO-level messages are also sent to Telegram.
        """
        timestamp = datetime.datetime.utcnow().isoformat()
        structured_msg = f"[ALERT - {level.upper()}] {timestamp} | {message}"

        # --- Log locally ---
        if level.upper() == "CRITICAL":
            self.logger.critical(structured_msg)
        elif level.upper() == "ERROR":
            self.logger.error(structured_msg)
        elif level.upper() == "WARNING":
            self.logger.warning(structured_msg)
        else:
            self.logger.info(structured_msg)

        # --- Decide if we should send to Telegram ---
        log_level = level.upper()
        should_send = log_level in ["CRITICAL", "ERROR", "WARNING"]
        if include_info and log_level == "INFO":
            should_send = True

        if self.telegram_token and self.chat_id and should_send:
            try:
                url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
                payload = {
                    "chat_id": self.chat_id,
                    "text": structured_msg,
                    "parse_mode": "Markdown",
                }
                resp = requests.post(url, json=payload, timeout=10)
                if resp.status_code != 200:
                    self.logger.error(f"Telegram alert failed: {resp.text}")
            except Exception as e:
                self.logger.error(f"Telegram alert exception: {e}")
