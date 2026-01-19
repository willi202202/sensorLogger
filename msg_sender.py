# msg_sender.py
"""
MessageSender class for sending alerts via multiple channels:
- NTFY (ntfy.sh push notifications)
- MAIL (Email)
- STDOUT (Console output)
- LOGFILE (File logging)
"""

import json
import logging
import smtplib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional, Any
from dataclasses import asdict
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
#import requests

from config.models import MessageConfig, EnabledChannels


# --------------------------
# Constants
# --------------------------

CONFIG_MESSAGE_PATH = "config/msg_config.json"


# --------------------------
# MessageSender Class
# --------------------------

class MessageSender:
    """
    Sends messages through configured channels (NTFY, Mail, Stdout, Logfile).
    Handles message deduplication based on max_repeat_hours.
    """

    def __init__(self, config_path: str):
        """
        Initialize MessageSender with config.

        Args:
            config_path: Path to msg_config.json
        """
        self.config = MessageConfig.load(config_path)
        self.last_sent: Dict[str, datetime] = {}  # Track last sent time per trigger type
        
        # Setup logging if logfile enabled
        if self.config.logfile.enabled:
            self._setup_logfile()
        else:
            self.logger = None

    def _setup_logfile(self) -> None:
        """Setup file logger for LOGFILE channel."""
        log_path = Path(self.config.logfile.path)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        self.logger = logging.getLogger("msg_sender")
        self.logger.setLevel(logging.INFO)
        
        # Remove existing handlers to avoid duplicates
        self.logger.handlers = []
        
        handler = logging.FileHandler(log_path)
        formatter = logging.Formatter(
            "%(asctime)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)

    def _should_send(self, trigger_key: str) -> bool:
        """
        Check if message should be sent based on max_repeat_hours.

        Args:
            trigger_key: Unique identifier for this trigger type

        Returns:
            True if enough time has passed since last send or never sent
        """
        if trigger_key not in self.last_sent:
            return True
        
        time_since_last = datetime.now() - self.last_sent[trigger_key]
        max_repeat = timedelta(hours=self.config.max_repeat_hours)
        return time_since_last >= max_repeat

    def send(
        self,
        trigger_key: str,
        trigger_title: str,
        enabled_channels: EnabledChannels,
        payload: str,
        payload_full: Optional[str] = None,
    ) -> bool:
        """
        Send message through enabled channels.

        Args:
            trigger_key: Unique identifier for this trigger (e.g., "BAD_VALUES")
            trigger_title: Human-readable title for the message
            enabled_channels: EnabledChannels instance specifying which channels to use
            payload: Message payload (may be truncated for preview)
            payload_full: Full payload for logfile/mail (uses payload if None)

        Returns:
            True if message was sent, False if skipped due to repeat limits
        """
        # Check repeat limit
        if not self._should_send(trigger_key):
            return False

        if payload_full is None:
            payload_full = payload

        # Send through enabled channels
        if enabled_channels.stdout:
            self._send_stdout(trigger_title, payload)

        if enabled_channels.logfile and self.logger:
            self._send_logfile(trigger_title, payload_full)

        if enabled_channels.ntfy:
            self._send_ntfy(trigger_title, payload)

        if enabled_channels.mail:
            self._send_mail(trigger_title, payload_full)

        # Update last sent time
        self.last_sent[trigger_key] = datetime.now()
        return True

    def _send_stdout(self, title: str, payload: str) -> None:
        """Send message to stdout (console)."""
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"\n[{timestamp}] {self.config.subject_prefix}")
            print(f"Title: {title}")
            print(f"Payload:\n{payload}\n")
        except Exception as e:
            print(f"Error sending stdout: {e}")

    def _send_logfile(self, title: str, payload: str) -> None:
        """Send message to logfile."""
        if not self.logger:
            return
        try:
            log_msg = f"{title} | {payload[:self.config.logfile.payload_preview_chars]}"
            self.logger.info(log_msg)
        except Exception as e:
            if self.logger:
                self.logger.error(f"Error logging message: {e}")

    def _send_ntfy(self, title: str, payload: str) -> None:
        """Send push notification via ntfy.sh."""
        if not self.config.ntfy.enabled:
            return

        try:
            url = f"{self.config.ntfy.server}/{self.config.ntfy.topic}"
            
            headers = {
                "Title": f"{self.config.subject_prefix} {title}",
                "Priority": str(self.config.ntfy.priority),
            }
            
            if self.config.ntfy.token:
                headers["Authorization"] = f"Bearer {self.config.ntfy.token}"

            # Truncate payload for preview
            preview = payload[:self.config.ntfy.payload_preview_chars]
            
            response = requests.post(
                url,
                data=preview,
                headers=headers,
                timeout=10
            )
            response.raise_for_status()
            
        except Exception as e:
            self._log_error(f"Error sending ntfy notification: {e}")

    def _send_mail(self, title: str, payload: str) -> None:
        """Send email message."""
        if not self.config.mail.enabled:
            return

        try:
            msg = MIMEMultipart()
            msg["From"] = self.config.mail.sender
            msg["To"] = self.config.mail.recipient
            msg["Subject"] = f"{self.config.subject_prefix} {title}"

            # Truncate payload for preview
            preview = payload[:self.config.mail.payload_preview_chars]
            
            body = f"""
Subject: {self.config.subject_prefix} {title}

{preview}

---
Sent at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            """
            
            msg.attach(MIMEText(body, "plain"))

            # SMTP sending would go here
            # For now, just prepare the message
            self._log_mail_message(msg)
            
        except Exception as e:
            self._log_error(f"Error preparing mail: {e}")

    def _log_mail_message(self, msg: MIMEMultipart) -> None:
        """Log mail message (stub for actual SMTP sending)."""
        try:
            if self.logger:
                self.logger.info(f"Mail prepared: {msg['Subject']} -> {msg['To']}")
        except Exception as e:
            self._log_error(f"Error logging mail message: {e}")

    def _log_error(self, message: str) -> None:
        """Log error message to logfile if available."""
        try:
            if self.logger:
                self.logger.error(message)
            else:
                print(f"ERROR: {message}")
        except Exception:
            print(f"ERROR: {message}")

    def get_last_sent_info(self) -> Dict[str, str]:
        """
        Get information about last sent times for each trigger.

        Returns:
            Dict mapping trigger_key to formatted datetime string
        """
        return {
            key: dt.strftime("%Y-%m-%d %H:%M:%S")
            for key, dt in self.last_sent.items()
        }


# ---------------------------
# Demo / quick test
# ---------------------------

if __name__ == "__main__":
    from config.models import EnabledChannels

    # Initialize sender
    sender = MessageSender(CONFIG_MESSAGE_PATH)

    print("=" * 60)
    print("MESSAGE SENDER TEST")
    print("=" * 60)
    print(f"Subject Prefix: {sender.config.subject_prefix}")
    print(f"Max Repeat Hours: {sender.config.max_repeat_hours}")
    print()

    # Test sending an info message
    test_payload = "This is a test message from the msg_sender demo."
    
    print("Sending test message via enabled channels...")
    result = sender.send(
        trigger_key="TEST_MESSAGE",
        trigger_title="Test: Demo Message",
        enabled_channels=sender.config.info.enabled,
        payload=test_payload,
    )

    print(f"Message sent: {result}")
    print(f"Last sent info: {sender.get_last_sent_info()}")

    # Test repeat limit
    print("\nTesting repeat limit (should be skipped)...")
    result2 = sender.send(
        trigger_key="TEST_MESSAGE",
        trigger_title="Test: Duplicate Message",
        enabled_channels=sender.config.info.enabled,
        payload=test_payload,
    )
    print(f"Second message sent: {result2}")
