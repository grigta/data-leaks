"""
Security event logger for critical security events.

Provides specialized logging for security-sensitive operations:
- Failed login attempts
- Rate limit exceeded events
- Suspicious activity detection
- Database connection failures
- Service lifecycle events
- High error rate alerts
- Telegram alerting for critical events

ASYNC vs SYNC METHODS:
    Synchronous methods (no await needed):
    - log_failed_login()
    - log_successful_login()
    - log_rate_limit_exceeded()
    - log_suspicious_activity()
    - log_unauthorized_access_attempt()
    - log_data_access()

    Asynchronous methods (must use await in async context):
    - log_db_connection_failure()    - sends critical Telegram alert
    - log_service_startup()          - sends info Telegram alert
    - log_service_shutdown()         - sends info Telegram alert
    - log_high_error_rate()          - sends critical Telegram alert
    - log_server_error()             - sends warning alert if >5 errors/min
    - log_rate_limit_user_exceeded() - sends warning alert if >100 requests

    For fire-and-forget in sync code, use _sync variants (logs only, no alerts):
    - log_db_connection_failure_sync()
    - log_service_startup_sync()
    - log_service_shutdown_sync()
"""
import asyncio
import time
from collections import defaultdict
from typing import Optional, Dict, Any, List
from api.common.logging_config import get_logger
from api.common.notifier import get_notifier


class SecurityEventLogger:
    """
    Specialized logger for security-related events.

    Usage:
        security_logger = SecurityEventLogger("public_api")
        security_logger.log_failed_login("user123", "192.168.1.100", "invalid_password")
    """

    def __init__(self, service_name: str):
        """
        Initialize security event logger.

        Args:
            service_name: Name of the service (e.g., "public_api", "admin_api")
        """
        self.service_name = service_name
        self.logger = get_logger(f"security.{service_name}")
        self.notifier = get_notifier(service_name)

        # Track server errors for aggregated alerting
        # Format: {error_key: [timestamp1, timestamp2, ...]}
        self._error_timestamps: Dict[str, List[float]] = defaultdict(list)
        self._error_window_seconds = 60  # Track errors in 60s window
        self._error_threshold = 5  # Alert after 5 errors in window

    def log_failed_login(
        self,
        username: str,
        ip: str,
        reason: str,
        extra: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Log failed login attempt.

        IMPORTANT: Never log actual passwords or sensitive credentials.

        Args:
            username: Username or partial identifier (masked if needed)
            ip: Client IP address
            reason: Reason for failure (e.g., "invalid_password", "user_not_found")
            extra: Additional context
        """
        log_data = {
            "event": "failed_login",
            "username": self._mask_sensitive(username),
            "ip": ip,
            "reason": reason
        }
        if extra:
            log_data.update(extra)

        self.logger.warning("Failed login attempt", extra=log_data)

    def log_successful_login(
        self,
        username: str,
        ip: str,
        user_id: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Log successful login.

        Args:
            username: Username
            ip: Client IP address
            user_id: User ID
            extra: Additional context
        """
        log_data = {
            "event": "successful_login",
            "username": username,
            "ip": ip
        }
        if user_id:
            log_data["user_id"] = user_id
        if extra:
            log_data.update(extra)

        self.logger.info("Successful login", extra=log_data)

    def log_rate_limit_exceeded(
        self,
        ip: str,
        endpoint: str,
        limit: str,
        extra: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Log rate limit exceeded event.

        Args:
            ip: Client IP address
            endpoint: API endpoint that was rate limited
            limit: Rate limit that was exceeded (e.g., "100/hour")
            extra: Additional context
        """
        log_data = {
            "event": "rate_limit_exceeded",
            "ip": ip,
            "endpoint": endpoint,
            "limit": limit
        }
        if extra:
            log_data.update(extra)

        self.logger.warning("Rate limit exceeded", extra=log_data)

    def log_suspicious_activity(
        self,
        ip: str,
        activity_type: str,
        details: Dict[str, Any],
        extra: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Log suspicious activity detected.

        Args:
            ip: Client IP address
            activity_type: Type of suspicious activity (e.g., "sql_injection_attempt",
                          "path_traversal", "duplicate_email_attempt")
            details: Details about the suspicious activity
            extra: Additional context
        """
        log_data = {
            "event": "suspicious_activity",
            "ip": ip,
            "activity_type": activity_type,
            "details": details
        }
        if extra:
            log_data.update(extra)

        self.logger.warning("Suspicious activity detected", extra=log_data)

    async def log_db_connection_failure(
        self,
        error: Exception,
        extra: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Log database connection failure and send critical alert.

        Args:
            error: Exception that occurred
            extra: Additional context
        """
        log_data = {
            "event": "db_connection_failure",
            "error_type": type(error).__name__,
            "error_message": str(error)
        }
        if extra:
            log_data.update(extra)

        self.logger.error("Database connection failure", extra=log_data)

        # Send critical alert to Telegram
        if self.notifier:
            try:
                message = f"<b>Database Connection Failure</b>\n"
                message += f"{type(error).__name__}: {str(error)[:200]}"
                await self.notifier.send_critical_alert(message, event_type="db_failure")
            except Exception as e:
                self.logger.warning(f"Failed to send Telegram alert: {e}")

    async def log_service_startup(
        self,
        version: str,
        config: Dict[str, Any]
    ) -> None:
        """
        Log service startup event and send info alert.

        IMPORTANT: Never include secrets in config dict.

        Args:
            version: Service version
            config: Non-sensitive configuration (workers count, pool size, etc.)
        """
        # Filter out any potential secrets
        safe_config = {k: v for k, v in config.items()
                       if not any(secret in k.lower()
                                 for secret in ['secret', 'password', 'key', 'token'])}

        log_data = {
            "event": "service_startup",
            "version": version,
            "config": safe_config
        }

        self.logger.info("Service starting", extra=log_data)

        # Send info alert to Telegram
        if self.notifier:
            try:
                config_str = ", ".join(f"{k}={v}" for k, v in safe_config.items())
                message = f"<b>Service Started</b>\n"
                message += f"Version: {version}\n"
                message += f"Config: {config_str[:200]}"
                await self.notifier.send_info_alert(message, event_type="service_startup")
            except Exception as e:
                self.logger.warning(f"Failed to send Telegram alert: {e}")

    async def log_service_shutdown(
        self,
        reason: str,
        extra: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Log service shutdown event and send info alert.

        Args:
            reason: Reason for shutdown (e.g., "graceful", "error", "signal")
            extra: Additional context
        """
        log_data = {
            "event": "service_shutdown",
            "reason": reason
        }
        if extra:
            log_data.update(extra)

        self.logger.info("Service shutting down", extra=log_data)

        # Send info alert to Telegram
        if self.notifier:
            try:
                message = f"<b>Service Shutdown</b>\n"
                message += f"Reason: {reason}"
                await self.notifier.send_info_alert(message, event_type="service_shutdown")
            except Exception as e:
                self.logger.warning(f"Failed to send Telegram alert: {e}")

    async def log_high_error_rate(
        self,
        error_count: int,
        total_requests: int,
        error_rate_percent: float,
        window_seconds: int = 300,
        extra: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Log high error rate alert and send critical alert.

        Args:
            error_count: Number of errors in the window
            total_requests: Total requests in the window
            error_rate_percent: Error rate as percentage
            window_seconds: Time window in seconds
            extra: Additional context
        """
        log_data = {
            "event": "high_error_rate",
            "error_count": error_count,
            "total_requests": total_requests,
            "error_rate_percent": round(error_rate_percent, 2),
            "window_seconds": window_seconds
        }
        if extra:
            log_data.update(extra)

        self.logger.error("High error rate detected", extra=log_data)

        # Send critical alert to Telegram
        if self.notifier:
            try:
                message = f"<b>High Error Rate Detected</b>\n"
                message += f"Rate: {round(error_rate_percent, 2)}%\n"
                message += f"Errors: {error_count}/{total_requests}\n"
                message += f"Window: {window_seconds}s"
                await self.notifier.send_critical_alert(message, event_type="high_error_rate")
            except Exception as e:
                self.logger.warning(f"Failed to send Telegram alert: {e}")

    def log_unauthorized_access_attempt(
        self,
        ip: str,
        path: str,
        method: str,
        reason: str,
        extra: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Log unauthorized access attempt.

        Args:
            ip: Client IP address
            path: Requested path
            method: HTTP method
            reason: Reason for denial
            extra: Additional context
        """
        log_data = {
            "event": "unauthorized_access",
            "ip": ip,
            "path": path,
            "method": method,
            "reason": reason
        }
        if extra:
            log_data.update(extra)

        self.logger.warning("Unauthorized access attempt", extra=log_data)

    def log_data_access(
        self,
        user_id: str,
        action: str,
        resource_type: str,
        resource_id: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Log sensitive data access for audit trail.

        Args:
            user_id: ID of user accessing data
            action: Type of action (read, update, delete)
            resource_type: Type of resource (user, order, transaction)
            resource_id: ID of resource accessed
            extra: Additional context
        """
        log_data = {
            "event": "data_access",
            "user_id": user_id,
            "action": action,
            "resource_type": resource_type
        }
        if resource_id:
            log_data["resource_id"] = resource_id
        if extra:
            log_data.update(extra)

        self.logger.info("Data access", extra=log_data)

    def _mask_sensitive(self, value: str, visible_chars: int = 4) -> str:
        """
        Mask sensitive values, showing only first few characters.

        Args:
            value: Value to mask
            visible_chars: Number of characters to show

        Returns:
            Masked value (e.g., "user****")
        """
        if not value or len(value) <= visible_chars:
            return "****"
        return value[:visible_chars] + "****"

    def _cleanup_old_errors(self, error_key: str) -> None:
        """Remove old error timestamps outside the tracking window."""
        current_time = time.time()
        cutoff = current_time - self._error_window_seconds
        self._error_timestamps[error_key] = [
            ts for ts in self._error_timestamps[error_key]
            if ts > cutoff
        ]

    async def log_server_error(
        self,
        path: str,
        error_type: str,
        client_ip: str,
        extra: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Log server error (500) and track for aggregated alerting.

        Sends warning alert if >5 errors occur within 60 seconds.

        Args:
            path: Request path that caused the error
            error_type: Type of exception
            client_ip: Client IP address
            extra: Additional context
        """
        log_data = {
            "event": "server_error",
            "path": path,
            "error_type": error_type,
            "ip": client_ip
        }
        if extra:
            log_data.update(extra)

        self.logger.error("Server error (500)", extra=log_data)

        # Track error for aggregation
        error_key = "server_errors"
        current_time = time.time()
        self._error_timestamps[error_key].append(current_time)
        self._cleanup_old_errors(error_key)

        # Check if we should send an alert
        error_count = len(self._error_timestamps[error_key])
        if error_count >= self._error_threshold and self.notifier:
            try:
                message = f"<b>Multiple 500 Errors</b>\n"
                message += f"Count: {error_count} in {self._error_window_seconds}s\n"
                message += f"Last error: {error_type}\n"
                message += f"Path: {path}"
                await self.notifier.send_warning_alert(message, event_type="multiple_500_errors")
            except Exception as e:
                self.logger.warning(f"Failed to send Telegram alert: {e}")

    async def log_rate_limit_user_exceeded(
        self,
        username: str,
        ip: str,
        count: int,
        endpoint: str,
        extra: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Log rate limit abuse by specific user and alert if threshold exceeded.

        Sends warning alert if count > 100 requests.

        Args:
            username: Username of the rate-limited user
            ip: Client IP address
            count: Number of requests from this user
            endpoint: Rate-limited endpoint
            extra: Additional context
        """
        log_data = {
            "event": "user_rate_limit_exceeded",
            "username": username,
            "ip": ip,
            "count": count,
            "endpoint": endpoint
        }
        if extra:
            log_data.update(extra)

        self.logger.warning("User rate limit exceeded", extra=log_data)

        # Send warning alert if count is high (potential abuse)
        if count > 100 and self.notifier:
            try:
                message = f"<b>User Rate Limit Exceeded</b>\n"
                message += f"User: {self._mask_sensitive(username)}\n"
                message += f"IP: {ip}\n"
                message += f"Count: {count}\n"
                message += f"Endpoint: {endpoint}"
                await self.notifier.send_warning_alert(message, event_type="user_rate_limit_abuse")
            except Exception as e:
                self.logger.warning(f"Failed to send Telegram alert: {e}")

    # =========================================================================
    # SYNC WRAPPERS (for use in synchronous code - logs only, no Telegram alerts)
    # =========================================================================

    def log_db_connection_failure_sync(
        self,
        error: Exception,
        extra: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Synchronous version of log_db_connection_failure.
        Logs the event but does NOT send Telegram alert.

        Use this when you cannot await (e.g., in synchronous code paths).
        For full functionality with alerts, use the async version.

        Args:
            error: Exception that occurred
            extra: Additional context
        """
        log_data = {
            "event": "db_connection_failure",
            "error_type": type(error).__name__,
            "error_message": str(error)
        }
        if extra:
            log_data.update(extra)

        self.logger.error("Database connection failure", extra=log_data)

    def log_service_startup_sync(
        self,
        version: str,
        config: Dict[str, Any]
    ) -> None:
        """
        Synchronous version of log_service_startup.
        Logs the event but does NOT send Telegram alert.

        Use this when you cannot await (e.g., in synchronous code paths).
        For full functionality with alerts, use the async version.

        Args:
            version: Service version
            config: Non-sensitive configuration
        """
        safe_config = {k: v for k, v in config.items()
                       if not any(secret in k.lower()
                                 for secret in ['secret', 'password', 'key', 'token'])}

        log_data = {
            "event": "service_startup",
            "version": version,
            "config": safe_config
        }

        self.logger.info("Service starting", extra=log_data)

    def log_service_shutdown_sync(
        self,
        reason: str,
        extra: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Synchronous version of log_service_shutdown.
        Logs the event but does NOT send Telegram alert.

        Use this when you cannot await (e.g., in synchronous code paths).
        For full functionality with alerts, use the async version.

        Args:
            reason: Reason for shutdown
            extra: Additional context
        """
        log_data = {
            "event": "service_shutdown",
            "reason": reason
        }
        if extra:
            log_data.update(extra)

        self.logger.info("Service shutting down", extra=log_data)
