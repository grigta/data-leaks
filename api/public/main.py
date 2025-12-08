"""
Public API FastAPI application.
"""
import asyncio
import time
from collections import defaultdict
from typing import Dict, List

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from api.public.routers import auth_router, search_router, ecommerce_router, stats_router, enrichment_router, billing_router, news_router, tickets_router, internal_router, support, contact, maintenance_router, admin_router, phone_lookup_router, subscriptions_router
from api.common.database import dispose_engine
from api.public.websocket import public_ws_manager
from api.public.dependencies import get_current_user_ws
from api.common.models_postgres import User
from datetime import datetime
import os
import uuid
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from api.public.dependencies import limiter

# Structured logging imports
from api.common.logging_config import setup_logging, get_logger
from api.common.middleware import CorrelationIdMiddleware, PerformanceMetricsMiddleware, SecurityEventMiddleware, get_error_rate_metrics
from api.common.security_logger import SecurityEventLogger


# Setup structured logging
log_level = os.getenv('LOG_LEVEL', 'INFO')
json_enabled = os.getenv('LOG_JSON_ENABLED', 'true').lower() in ('true', '1', 'yes')
setup_logging(service_name="public_api", log_level=log_level, json_enabled=json_enabled)
logger = get_logger(__name__)
security_logger = SecurityEventLogger("public_api")

# User rate limit tracking for abuse detection
# Format: {user_key: [timestamp1, timestamp2, ...]}
_user_rate_limit_hits: Dict[str, List[float]] = defaultdict(list)
_user_rate_limit_window = 300  # 5 minutes window
_user_rate_limit_abuse_threshold = 100  # Alert if >100 rate limit hits


def _track_user_rate_limit(user_key: str) -> int:
    """
    Track rate limit hit for a user and return current count in window.

    Args:
        user_key: Unique identifier for the user (username or IP)

    Returns:
        Number of rate limit hits in the current window
    """
    current_time = time.time()
    cutoff = current_time - _user_rate_limit_window

    # Add current hit
    _user_rate_limit_hits[user_key].append(current_time)

    # Clean up old entries for this user
    _user_rate_limit_hits[user_key] = [
        ts for ts in _user_rate_limit_hits[user_key]
        if ts > cutoff
    ]

    # Periodic cleanup of old user entries
    if len(_user_rate_limit_hits) > 1000:
        _cleanup_user_rate_limits()

    return len(_user_rate_limit_hits[user_key])


def _cleanup_user_rate_limits() -> None:
    """Clean up old user rate limit tracking entries."""
    current_time = time.time()
    cutoff = current_time - _user_rate_limit_window

    keys_to_remove = []
    for user_key, timestamps in _user_rate_limit_hits.items():
        # Filter timestamps
        _user_rate_limit_hits[user_key] = [ts for ts in timestamps if ts > cutoff]
        # Mark for removal if empty
        if not _user_rate_limit_hits[user_key]:
            keys_to_remove.append(user_key)

    for key in keys_to_remove:
        del _user_rate_limit_hits[key]

# Create FastAPI app
app = FastAPI(
    title="SSN Public API",
    version="1.0.0",
    description="Public API for SSN search and e-commerce"
)

# Register SlowAPI limiter
app.state.limiter = limiter


# Custom rate limit handler with security logging
async def custom_rate_limit_handler(request: Request, exc: RateLimitExceeded):
    """Handle rate limit exceeded with security logging and user abuse detection."""
    client_ip = request.headers.get("cf-connecting-ip") or \
                request.headers.get("x-forwarded-for", "").split(",")[0].strip() or \
                (request.client.host if request.client else "unknown")

    # Log the rate limit event
    security_logger.log_rate_limit_exceeded(
        ip=client_ip,
        endpoint=request.url.path,
        limit=str(exc.detail)
    )

    # Try to get username from request.state (set by auth middleware/dependency)
    username = None
    if hasattr(request.state, 'user') and request.state.user:
        username = getattr(request.state.user, 'username', None)
    elif hasattr(request.state, 'username'):
        username = request.state.username

    # Track rate limit hits per user/IP
    user_key = username if username else f"ip:{client_ip}"
    hit_count = _track_user_rate_limit(user_key)

    # If user exceeds abuse threshold, send alert
    if hit_count > _user_rate_limit_abuse_threshold:
        try:
            await security_logger.log_rate_limit_user_exceeded(
                username=username or "anonymous",
                ip=client_ip,
                count=hit_count,
                endpoint=request.url.path
            )
        except Exception as e:
            logger.warning(f"Failed to log user rate limit exceeded: {e}")

    return await _rate_limit_exceeded_handler(request, exc)


app.add_exception_handler(RateLimitExceeded, custom_rate_limit_handler)

# Add middleware (order matters: last added = first executed)
app.add_middleware(SecurityEventMiddleware)
app.add_middleware(PerformanceMetricsMiddleware)
app.add_middleware(CorrelationIdMiddleware)

# Configure CORS
allowed_origins = os.getenv('ALLOWED_ORIGINS', '*').split(',')
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth_router, prefix="/auth", tags=["Authentication"])
app.include_router(search_router, prefix="/search", tags=["Search"])
app.include_router(ecommerce_router, prefix="/ecommerce", tags=["E-commerce"])
app.include_router(stats_router, prefix="/stats", tags=["Statistics"])
app.include_router(enrichment_router, prefix="/enrichment", tags=["Enrichment"])
app.include_router(billing_router, prefix="/billing", tags=["Billing"])
app.include_router(news_router, prefix="/news", tags=["News"])
app.include_router(tickets_router, prefix="/tickets", tags=["User Tickets"])
app.include_router(support.router, prefix="/support", tags=["Support"])
app.include_router(contact.router, prefix="/contact", tags=["Contact"])
app.include_router(maintenance_router, prefix="/maintenance", tags=["Maintenance"])
app.include_router(admin_router, prefix="/admin", tags=["Admin"])
app.include_router(phone_lookup_router, prefix="/phone-lookup", tags=["Phone Lookup"])
app.include_router(subscriptions_router, prefix="/subscriptions", tags=["Subscriptions"])
app.include_router(internal_router, tags=["Internal"])


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "service": "public_api"
    }


# WebSocket endpoint for regular users
@app.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    current_user: User = Depends(get_current_user_ws)
):
    """
    WebSocket endpoint for regular users to receive real-time ticket updates.
    """
    user_id = str(current_user.id)
    username = current_user.username

    try:
        # Connect the user
        await public_ws_manager.connect(websocket, user_id, username)

        # Keep connection alive and handle incoming messages
        while True:
            try:
                # Wait for messages from client (optional, can be used for ping/pong)
                data = await websocket.receive_text()
                logger.debug(f"Received message from user {username}: {data}")

                # Echo back as heartbeat confirmation
                await websocket.send_json({
                    "event_type": "heartbeat",
                    "data": {"message": "pong"},
                    "timestamp": datetime.utcnow().isoformat()
                })
            except WebSocketDisconnect:
                logger.info(f"WebSocket disconnected for user {username}")
                break
            except Exception as e:
                logger.error(f"Error in WebSocket loop for user {username}: {e}")
                break

    except Exception as e:
        logger.error(f"WebSocket error for user {username}: {e}")
    finally:
        # Clean up connection
        public_ws_manager.disconnect(user_id)


# WebSocket endpoint for bot
@app.websocket("/ws/bot")
async def bot_websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for Telegram bot to receive all ticket events.
    Requires BOT_API_KEY authentication via X-Bot-Api-Key header or query parameter (deprecated).
    """
    connection_id = str(uuid.uuid4())

    try:
        # Validate API key - prefer header, fallback to query param for backward compatibility
        api_key = websocket.headers.get("x-bot-api-key") or websocket.query_params.get("api_key")
        expected_key = os.getenv('BOT_API_KEY')

        if not expected_key:
            logger.error("BOT_API_KEY not configured in environment")
            await websocket.close(code=1008, reason="Server configuration error")
            return

        if not api_key or api_key != expected_key:
            logger.warning(f"Bot connection attempt with invalid API key from {websocket.client}")
            await websocket.close(code=1008, reason="Invalid API key")
            return

        # Accept connection
        await websocket.accept()
        logger.info(f"Bot connected with connection_id: {connection_id}")

        # Register bot connection
        await public_ws_manager.connect_bot(websocket, connection_id)

        # Send welcome message
        await websocket.send_json({
            "event_type": "connection_established",
            "data": {
                "message": "Bot connected successfully",
                "connection_id": connection_id
            },
            "timestamp": datetime.utcnow().isoformat()
        })

        # Keep connection alive and handle incoming messages
        while True:
            try:
                # Wait for messages from bot (optional heartbeat)
                data = await websocket.receive_text()
                logger.debug(f"Received message from bot {connection_id}: {data}")

                # Echo back as heartbeat confirmation
                await websocket.send_json({
                    "event_type": "heartbeat",
                    "data": {"message": "pong"},
                    "timestamp": datetime.utcnow().isoformat()
                })
            except WebSocketDisconnect:
                logger.info(f"Bot WebSocket disconnected: {connection_id}")
                break
            except Exception as e:
                logger.error(f"Error in bot WebSocket loop {connection_id}: {e}")
                break

    except Exception as e:
        logger.error(f"Bot WebSocket error {connection_id}: {e}")
    finally:
        # Clean up connection
        public_ws_manager.disconnect_bot(connection_id)
        logger.info(f"Bot connection cleaned up: {connection_id}")


# Exception handlers
from fastapi.exceptions import RequestValidationError


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle validation exceptions with detailed logging."""
    client_ip = request.headers.get("cf-connecting-ip") or \
                request.headers.get("x-forwarded-for", "").split(",")[0].strip() or \
                (request.client.host if request.client else "unknown")

    logger.error(
        "Validation error",
        extra={
            "path": request.url.path,
            "errors": exc.errors(),
            "client_ip": client_ip
        }
    )

    # Log as suspicious activity for potential attack patterns
    security_logger.log_suspicious_activity(
        ip=client_ip,
        activity_type="validation_error",
        details={"path": request.url.path, "error_count": len(exc.errors())}
    )

    return JSONResponse(
        status_code=422,
        content={
            "detail": exc.errors(),
            "timestamp": datetime.now().isoformat()
        }
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions."""
    client_ip = request.headers.get("cf-connecting-ip") or \
                request.headers.get("x-forwarded-for", "").split(",")[0].strip() or \
                (request.client.host if request.client else "unknown")

    # Log authentication failures
    if exc.status_code == 401:
        security_logger.log_failed_login(
            username="unknown",
            ip=client_ip,
            reason=str(exc.detail),
            extra={"path": request.url.path}
        )

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.detail,
            "timestamp": datetime.now().isoformat()
        }
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle general exceptions."""
    client_ip = request.headers.get("cf-connecting-ip") or \
                request.headers.get("x-forwarded-for", "").split(",")[0].strip() or \
                (request.client.host if request.client else "unknown")

    logger.error(
        "Unhandled exception",
        exc_info=True,
        extra={
            "path": request.url.path,
            "error_type": type(exc).__name__,
            "client_ip": client_ip
        }
    )

    # Track server errors for aggregated alerting
    await security_logger.log_server_error(
        path=request.url.path,
        error_type=type(exc).__name__,
        client_ip=client_ip
    )

    # Check for database-related errors
    error_str = str(exc).lower()
    error_type = type(exc).__name__.lower()
    if any(db_indicator in error_str or db_indicator in error_type
           for db_indicator in ['database', 'connection', 'pool', 'sqlalchemy', 'asyncpg', 'postgres']):
        await security_logger.log_db_connection_failure(exc)

    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "timestamp": datetime.now().isoformat()
        }
    )


# Background task for error rate monitoring
_error_rate_monitor_task = None
_error_rate_threshold = 10.0  # Alert if error rate > 10%
_error_rate_check_interval = 60  # Check every 60 seconds
_error_rate_window = 300  # 5 minute window


async def _monitor_error_rate():
    """Background task to monitor error rate and send alerts."""
    while True:
        try:
            await asyncio.sleep(_error_rate_check_interval)

            # Get error rate metrics
            error_count, total_requests, error_rate = get_error_rate_metrics(_error_rate_window)

            # Only check if we have enough requests
            if total_requests >= 10 and error_rate > _error_rate_threshold:
                await security_logger.log_high_error_rate(
                    error_count=error_count,
                    total_requests=total_requests,
                    error_rate_percent=error_rate,
                    window_seconds=_error_rate_window
                )
                logger.warning(
                    f"High error rate detected: {error_rate:.2f}% ({error_count}/{total_requests})"
                )

        except asyncio.CancelledError:
            logger.info("Error rate monitor task cancelled")
            break
        except Exception as e:
            logger.error(f"Error in error rate monitor: {e}", exc_info=True)
            # Continue monitoring even after errors
            await asyncio.sleep(10)


# Startup/shutdown events
@app.on_event("startup")
async def startup_event():
    """Startup event handler."""
    global _error_rate_monitor_task

    logger.info("Public API starting up...")
    await security_logger.log_service_startup(
        version="1.0.0",
        config={
            "workers": os.getenv('UVICORN_WORKERS', '4'),
            "pool_size": os.getenv('DB_POOL_SIZE', '40'),
            "log_level": log_level,
            "json_logging": json_enabled
        }
    )

    # Start error rate monitoring task
    _error_rate_monitor_task = asyncio.create_task(_monitor_error_rate())
    logger.info("Error rate monitor started")


@app.on_event("shutdown")
async def shutdown_event():
    """Shutdown event handler."""
    global _error_rate_monitor_task

    # Stop error rate monitoring task
    if _error_rate_monitor_task:
        _error_rate_monitor_task.cancel()
        try:
            await _error_rate_monitor_task
        except asyncio.CancelledError:
            pass
        logger.info("Error rate monitor stopped")

    await security_logger.log_service_shutdown("graceful")
    logger.info("Public API shutting down...")
    try:
        logger.info("Closing database connections...")
        await dispose_engine()
        logger.info("Database connections closed successfully")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}", exc_info=True)
