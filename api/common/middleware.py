"""
FastAPI middleware for logging, correlation IDs, and security monitoring.
"""
import time
import uuid
import os
from typing import Dict, Callable
from collections import defaultdict
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from api.common.logging_config import (
    get_logger,
    set_correlation_id,
    clear_correlation_id,
    get_correlation_id
)


logger = get_logger(__name__)


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """
    Middleware for handling correlation IDs.

    - Extracts X-Request-ID from incoming request headers
    - Generates a new UUID if header is not present
    - Sets correlation ID in context for all logs
    - Adds X-Request-ID to response headers
    """

    def __init__(self, app, header_name: str = None):
        super().__init__(app)
        self.header_name = header_name or os.getenv('CORRELATION_ID_HEADER', 'X-Request-ID')

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request and manage correlation ID."""
        # Extract or generate correlation ID
        correlation_id = request.headers.get(self.header_name.lower()) or str(uuid.uuid4())

        # Set in context for logging
        set_correlation_id(correlation_id)

        # Get client IP (considering proxies)
        client_ip = self._get_client_ip(request)

        # Log request start
        logger.info(
            "Request started",
            extra={
                "method": request.method,
                "path": request.url.path,
                "client_ip": client_ip,
                "user_agent": request.headers.get("user-agent", "unknown")[:200]
            }
        )

        try:
            # Process request
            response = await call_next(request)

            # Add correlation ID to response headers
            response.headers[self.header_name] = correlation_id

            return response

        finally:
            # Clear correlation ID context
            clear_correlation_id()

    def _get_client_ip(self, request: Request) -> str:
        """Get client IP address, considering proxies."""
        # Check Cloudflare header first
        cf_connecting_ip = request.headers.get("cf-connecting-ip")
        if cf_connecting_ip:
            return cf_connecting_ip

        # Check X-Forwarded-For
        x_forwarded_for = request.headers.get("x-forwarded-for")
        if x_forwarded_for:
            return x_forwarded_for.split(",")[0].strip()

        # Check X-Real-IP
        x_real_ip = request.headers.get("x-real-ip")
        if x_real_ip:
            return x_real_ip

        # Fallback to direct client IP
        if request.client:
            return request.client.host

        return "unknown"


# Global request metrics tracking for error rate calculation
# These are shared across all middleware instances
_request_metrics: Dict[str, list] = defaultdict(list)  # {timestamp: [status_code, ...]}
_metrics_window_seconds = 300  # 5 minute window
_metrics_lock_time = 0.0  # Simple mutex using timestamp


def get_error_rate_metrics(window_seconds: int = 300) -> tuple:
    """
    Get error rate metrics for the given window.

    Returns:
        Tuple of (error_count, total_requests, error_rate_percent)
    """
    current_time = time.time()
    cutoff = current_time - window_seconds

    total_requests = 0
    error_count = 0

    for timestamp_key, status_codes in list(_request_metrics.items()):
        try:
            ts = float(timestamp_key)
            if ts > cutoff:
                for status_code in status_codes:
                    total_requests += 1
                    if status_code >= 500:
                        error_count += 1
        except (ValueError, TypeError):
            pass

    error_rate = (error_count / total_requests * 100) if total_requests > 0 else 0.0
    return error_count, total_requests, error_rate


def _cleanup_old_metrics() -> None:
    """Clean up old metrics outside the tracking window."""
    current_time = time.time()
    cutoff = current_time - _metrics_window_seconds

    keys_to_remove = []
    for timestamp_key in list(_request_metrics.keys()):
        try:
            ts = float(timestamp_key)
            if ts <= cutoff:
                keys_to_remove.append(timestamp_key)
        except (ValueError, TypeError):
            keys_to_remove.append(timestamp_key)

    for key in keys_to_remove:
        del _request_metrics[key]


class PerformanceMetricsMiddleware(BaseHTTPMiddleware):
    """
    Middleware for tracking request performance metrics.

    - Measures request processing time
    - Logs request completion with duration
    - Warns about slow requests
    - Adds X-Response-Time header
    - Tracks request counts and error rates for alerting
    """

    def __init__(self, app, slow_request_threshold_ms: int = None):
        super().__init__(app)
        self.slow_request_threshold_ms = slow_request_threshold_ms or int(
            os.getenv('LOG_SLOW_REQUEST_THRESHOLD_MS', '1000')
        )

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request and track performance metrics."""
        start_time = time.time()

        # Get client IP for logging
        client_ip = self._get_client_ip(request)

        try:
            response = await call_next(request)
        except Exception as e:
            # Calculate duration even on error
            duration_ms = (time.time() - start_time) * 1000

            logger.error(
                "Request failed with exception",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "client_ip": client_ip,
                    "duration_ms": round(duration_ms, 2),
                    "error": str(e)
                }
            )
            raise

        # Calculate duration
        duration_ms = (time.time() - start_time) * 1000

        # Track metrics for error rate calculation (bucket by second for efficiency)
        timestamp_bucket = str(int(time.time()))
        _request_metrics[timestamp_bucket].append(response.status_code)

        # Periodic cleanup of old metrics
        if len(_request_metrics) > 600:  # More than 10 minutes of buckets
            _cleanup_old_metrics()

        # Determine log level based on status code
        if response.status_code >= 500:
            logger.error(
                "Request completed with server error",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": round(duration_ms, 2),
                    "client_ip": client_ip
                }
            )
        elif response.status_code >= 400:
            logger.warning(
                "Request completed with client error",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": round(duration_ms, 2),
                    "client_ip": client_ip
                }
            )
        else:
            logger.info(
                "Request completed",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": round(duration_ms, 2),
                    "client_ip": client_ip
                }
            )

        # Log slow request warning
        if duration_ms > self.slow_request_threshold_ms:
            logger.warning(
                "Slow request detected",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "duration_ms": round(duration_ms, 2),
                    "threshold_ms": self.slow_request_threshold_ms,
                    "client_ip": client_ip
                }
            )

        # Add response time header
        response.headers["X-Response-Time"] = f"{duration_ms:.2f}ms"

        return response

    def _get_client_ip(self, request: Request) -> str:
        """Get client IP address, considering proxies."""
        cf_connecting_ip = request.headers.get("cf-connecting-ip")
        if cf_connecting_ip:
            return cf_connecting_ip

        x_forwarded_for = request.headers.get("x-forwarded-for")
        if x_forwarded_for:
            return x_forwarded_for.split(",")[0].strip()

        x_real_ip = request.headers.get("x-real-ip")
        if x_real_ip:
            return x_real_ip

        if request.client:
            return request.client.host

        return "unknown"


class SecurityEventMiddleware(BaseHTTPMiddleware):
    """
    Middleware for monitoring security-related events.

    Tracks and logs:
    - Multiple authentication failures from same IP
    - Access to non-existent endpoints (404s)
    - Large payload attempts
    - Suspicious patterns
    """

    def __init__(self, app):
        super().__init__(app)
        # In-memory tracking (with TTL cleanup)
        self._auth_failures: Dict[str, list] = defaultdict(list)
        self._not_found_requests: Dict[str, list] = defaultdict(list)
        self._cleanup_interval = 60  # seconds
        self._last_cleanup = time.time()

        # Thresholds
        self._auth_failure_threshold = 5  # failures per minute
        self._not_found_threshold = 10  # 404s per minute
        self._max_payload_size = 1024 * 1024  # 1MB

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request and monitor security events."""
        # Periodic cleanup
        self._cleanup_old_entries()

        client_ip = self._get_client_ip(request)

        # Check for large payload
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > self._max_payload_size:
                    logger.warning(
                        "Large payload attempt detected",
                        extra={
                            "event_type": "large_payload",
                            "client_ip": client_ip,
                            "content_length": int(content_length),
                            "path": request.url.path
                        }
                    )
            except ValueError:
                pass

        # Process request
        response = await call_next(request)

        # Track authentication failures
        if response.status_code in (401, 403):
            self._track_auth_failure(client_ip, request.url.path)

        # Track 404s (potential scanning)
        if response.status_code == 404:
            self._track_not_found(client_ip, request.url.path)

        return response

    def _track_auth_failure(self, client_ip: str, path: str) -> None:
        """Track authentication failures and log if threshold exceeded."""
        current_time = time.time()
        self._auth_failures[client_ip].append(current_time)

        # Count recent failures (last minute)
        recent_failures = [
            t for t in self._auth_failures[client_ip]
            if current_time - t < 60
        ]
        self._auth_failures[client_ip] = recent_failures

        if len(recent_failures) >= self._auth_failure_threshold:
            logger.warning(
                "Multiple authentication failures detected",
                extra={
                    "event_type": "multiple_auth_failures",
                    "client_ip": client_ip,
                    "count": len(recent_failures),
                    "path": path,
                    "window_seconds": 60
                }
            )

    def _track_not_found(self, client_ip: str, path: str) -> None:
        """Track 404 requests and log if threshold exceeded."""
        current_time = time.time()
        self._not_found_requests[client_ip].append((current_time, path))

        # Count recent 404s (last minute)
        recent_404s = [
            entry for entry in self._not_found_requests[client_ip]
            if current_time - entry[0] < 60
        ]
        self._not_found_requests[client_ip] = recent_404s

        if len(recent_404s) >= self._not_found_threshold:
            paths = [entry[1] for entry in recent_404s[-5:]]  # Last 5 paths
            logger.warning(
                "Potential scanning detected",
                extra={
                    "event_type": "potential_scanning",
                    "client_ip": client_ip,
                    "count": len(recent_404s),
                    "recent_paths": paths,
                    "window_seconds": 60
                }
            )

    def _cleanup_old_entries(self) -> None:
        """Clean up old tracking entries."""
        current_time = time.time()
        if current_time - self._last_cleanup < self._cleanup_interval:
            return

        self._last_cleanup = current_time
        cutoff_time = current_time - 120  # Keep 2 minutes of data

        # Clean auth failures
        for ip in list(self._auth_failures.keys()):
            self._auth_failures[ip] = [
                t for t in self._auth_failures[ip]
                if t > cutoff_time
            ]
            if not self._auth_failures[ip]:
                del self._auth_failures[ip]

        # Clean 404 tracking
        for ip in list(self._not_found_requests.keys()):
            self._not_found_requests[ip] = [
                entry for entry in self._not_found_requests[ip]
                if entry[0] > cutoff_time
            ]
            if not self._not_found_requests[ip]:
                del self._not_found_requests[ip]

    def _get_client_ip(self, request: Request) -> str:
        """Get client IP address, considering proxies."""
        cf_connecting_ip = request.headers.get("cf-connecting-ip")
        if cf_connecting_ip:
            return cf_connecting_ip

        x_forwarded_for = request.headers.get("x-forwarded-for")
        if x_forwarded_for:
            return x_forwarded_for.split(",")[0].strip()

        x_real_ip = request.headers.get("x-real-ip")
        if x_real_ip:
            return x_real_ip

        if request.client:
            return request.client.host

        return "unknown"
