"""Simulated notifications, run as FastAPI background tasks."""
import logging
import time
from datetime import datetime, timezone

from app.config import settings

logger = logging.getLogger(__name__)


def send_notification(email: str, message: str) -> None:
    """Append one line to the notification log.

    FastAPI runs this *after* the HTTP response has been sent, so a slow notification never slows the request down. Failures are logged, never raised, because the user's request has already succeeded by then.
    """
    try:
        if settings.notification_delay_seconds > 0:
            time.sleep(settings.notification_delay_seconds)
        # Keep each notification on exactly one line (no log injection).
        safe_message = message.replace("\r", " ").replace("\n", " ")
        timestamp = datetime.now(timezone.utc).isoformat()
        with open(settings.notification_log_path, "a", encoding="utf-8") as log_file:
            log_file.write(f"[{timestamp}] to={email} | {safe_message}\n")
        logger.info("Notification for %s: %s", email, safe_message)
    except Exception:
        logger.exception("Failed to send notification to %s", email)
