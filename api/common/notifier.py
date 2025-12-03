"""
Telegram notifier for critical system alerts.

Provides asynchronous alert sending to Telegram channel with:
- Rate limiting (max 1 alert per minute per event type)
- Graceful error handling (never blocks main flow)
- Message formatting with severity levels
"""
import os
import time
from typing import Dict, Optional
from datetime import datetime

import aiohttp

from api.common.logging_config import get_logger

logger = get_logger(__name__)


class TelegramNotifier:
    """
    Sends critical alerts to Telegram channel.

    Features:
    - Rate limiting: max 1 alert per minute per event type
    - Graceful degradation: logging errors but not blocking
    - HTML formatting for readability

    Usage:
        notifier = TelegramNotifier(bot_token, channel_id)
        await notifier.send_alert("Database connection failed", "critical")
    """

    # Severity emoji mapping
    SEVERITY_EMOJI = {
        "critical": "\U0001F6A8",  # 🚨
        "warning": "\u26A0\uFE0F",  # ⚠️
        "info": "\u2139\uFE0F",     # ℹ️
    }

    # Severity label mapping
    SEVERITY_LABEL = {
        "critical": "CRITICAL",
        "warning": "WARNING",
        "info": "INFO",
    }

    def __init__(self, bot_token: str, channel_id: str, service_name: str = "unknown"):
        """
        Initialize Telegram notifier.

        Args:
            bot_token: Telegram Bot API token from @BotFather
            channel_id: Channel/chat ID for alerts (use negative for channels)
            service_name: Service name to include in alerts
        """
        self.bot_token = bot_token
        self.channel_id = channel_id
        self.service_name = service_name
        self.api_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

        # Rate limiting: track last alert time per event type
        self._alert_timestamps: Dict[str, float] = {}
        self._rate_limit_seconds = 60  # 1 minute between same event type
        self._cleanup_interval = 120   # Cleanup old entries every 2 minutes
        self._last_cleanup = time.time()

    def _should_send_alert(self, alert_key: str) -> bool:
        """
        Check if alert should be sent based on rate limiting.

        Args:
            alert_key: Unique key for this alert type (e.g., "critical:db_failure")

        Returns:
            True if alert should be sent, False if rate limited
        """
        current_time = time.time()

        # Cleanup old entries periodically
        if current_time - self._last_cleanup > self._cleanup_interval:
            self._cleanup_old_alerts()
            self._last_cleanup = current_time

        # Check if we've sent this alert type recently
        last_sent = self._alert_timestamps.get(alert_key, 0)
        if current_time - last_sent < self._rate_limit_seconds:
            logger.debug(
                f"Alert rate limited: {alert_key}",
                extra={"alert_key": alert_key, "seconds_since_last": current_time - last_sent}
            )
            return False

        # Update timestamp
        self._alert_timestamps[alert_key] = current_time
        return True

    def _cleanup_old_alerts(self) -> None:
        """Remove old alert timestamps to prevent memory growth."""
        current_time = time.time()
        cutoff = current_time - self._cleanup_interval

        # Remove entries older than cleanup interval
        keys_to_remove = [
            key for key, timestamp in self._alert_timestamps.items()
            if timestamp < cutoff
        ]
        for key in keys_to_remove:
            del self._alert_timestamps[key]

        if keys_to_remove:
            logger.debug(f"Cleaned up {len(keys_to_remove)} old alert timestamps")

    def _format_message(self, message: str, severity: str, event_type: str = "") -> str:
        """
        Format alert message with HTML formatting.

        Args:
            message: Alert message text
            severity: Severity level (critical, warning, info)
            event_type: Optional event type for context

        Returns:
            Formatted HTML message
        """
        emoji = self.SEVERITY_EMOJI.get(severity, "\u2139\uFE0F")
        label = self.SEVERITY_LABEL.get(severity, "INFO")
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

        formatted = f"{emoji} <b>{label}</b>\n"
        formatted += f"<b>Service:</b> {self.service_name}\n"
        if event_type:
            formatted += f"<b>Event:</b> {event_type}\n"
        formatted += f"\n{message}\n"
        formatted += f"\n<i>{timestamp}</i>"

        return formatted

    async def send_alert(
        self,
        message: str,
        severity: str = "warning",
        event_type: str = ""
    ) -> bool:
        """
        Send alert to Telegram channel.

        Args:
            message: Alert message text
            severity: Severity level (critical, warning, info)
            event_type: Event type for rate limiting key

        Returns:
            True if sent successfully, False otherwise
        """
        # Create rate limit key
        alert_key = f"{severity}:{event_type}" if event_type else f"{severity}:general"

        # Check rate limiting
        if not self._should_send_alert(alert_key):
            return False

        # Format message
        formatted_message = self._format_message(message, severity, event_type)

        # Prepare request payload
        payload = {
            "chat_id": self.channel_id,
            "text": formatted_message,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.api_url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as response:
                    if response.status == 200:
                        logger.info(
                            "Telegram alert sent",
                            extra={
                                "severity": severity,
                                "event_type": event_type,
                                "channel_id": self.channel_id
                            }
                        )
                        return True
                    else:
                        response_text = await response.text()
                        logger.error(
                            f"Telegram API error: {response.status}",
                            extra={
                                "status": response.status,
                                "response": response_text[:200]
                            }
                        )
                        return False

        except aiohttp.ClientTimeout:
            logger.error("Telegram alert timeout")
            return False
        except aiohttp.ClientError as e:
            logger.error(f"Telegram alert network error: {e}")
            return False
        except Exception as e:
            logger.error(f"Telegram alert unexpected error: {e}", exc_info=True)
            return False

    async def send_critical_alert(self, message: str, event_type: str = "") -> bool:
        """Send critical severity alert."""
        return await self.send_alert(message, severity="critical", event_type=event_type)

    async def send_warning_alert(self, message: str, event_type: str = "") -> bool:
        """Send warning severity alert."""
        return await self.send_alert(message, severity="warning", event_type=event_type)

    async def send_info_alert(self, message: str, event_type: str = "") -> bool:
        """Send info severity alert."""
        return await self.send_alert(message, severity="info", event_type=event_type)


# Global notifier instances per service (multi-singleton pattern)
_notifiers: Dict[str, TelegramNotifier] = {}
# Flag to track if Telegram is not configured (avoid repeated env checks)
_telegram_disabled: bool = False


def get_notifier(service_name: str = "unknown") -> Optional[TelegramNotifier]:
    """
    Get configured TelegramNotifier instance for a specific service.

    Each service gets its own notifier instance to ensure correct
    service name in alerts. Instances are cached per service_name.

    Args:
        service_name: Name of the service for alert context

    Returns:
        TelegramNotifier instance or None if environment variables not set
    """
    global _telegram_disabled

    # Quick return if Telegram is known to be disabled
    if _telegram_disabled:
        return None

    # Normalize service name
    service_name = service_name.strip() or "unknown"

    # Return cached instance if exists
    if service_name in _notifiers:
        return _notifiers[service_name]

    # Check environment variables
    bot_token = os.getenv("TELEGRAM_ALERT_BOT_TOKEN", "").strip()
    channel_id = os.getenv("TELEGRAM_ALERT_CHANNEL_ID", "").strip()

    if not bot_token or not channel_id:
        logger.debug(
            "Telegram alerting disabled: missing TELEGRAM_ALERT_BOT_TOKEN or TELEGRAM_ALERT_CHANNEL_ID"
        )
        _telegram_disabled = True
        return None

    # Create new notifier for this service
    notifier = TelegramNotifier(
        bot_token=bot_token,
        channel_id=channel_id,
        service_name=service_name
    )
    _notifiers[service_name] = notifier

    logger.info(
        "Telegram notifier initialized",
        extra={"service_name": service_name}
    )

    return notifier


def reset_notifier(service_name: Optional[str] = None) -> None:
    """
    Reset notifier instance(s) for testing.

    Args:
        service_name: If provided, reset only this service's notifier.
                     If None, reset all notifiers.
    """
    global _notifiers, _telegram_disabled

    if service_name is not None:
        _notifiers.pop(service_name, None)
    else:
        _notifiers.clear()
        _telegram_disabled = False


# Convenience functions for direct use
async def send_critical_alert(message: str, event_type: str = "", service_name: str = "unknown") -> bool:
    """
    Send critical alert to Telegram (convenience function).

    Args:
        message: Alert message
        event_type: Event type for rate limiting
        service_name: Service name for context

    Returns:
        True if sent, False if not configured or failed
    """
    notifier = get_notifier(service_name)
    if notifier is None:
        return False
    return await notifier.send_critical_alert(message, event_type)


async def send_warning_alert(message: str, event_type: str = "", service_name: str = "unknown") -> bool:
    """
    Send warning alert to Telegram (convenience function).

    Args:
        message: Alert message
        event_type: Event type for rate limiting
        service_name: Service name for context

    Returns:
        True if sent, False if not configured or failed
    """
    notifier = get_notifier(service_name)
    if notifier is None:
        return False
    return await notifier.send_warning_alert(message, event_type)


async def send_info_alert(message: str, event_type: str = "", service_name: str = "unknown") -> bool:
    """
    Send info alert to Telegram (convenience function).

    Args:
        message: Alert message
        event_type: Event type for rate limiting
        service_name: Service name for context

    Returns:
        True if sent, False if not configured or failed
    """
    notifier = get_notifier(service_name)
    if notifier is None:
        return False
    return await notifier.send_info_alert(message, event_type)
