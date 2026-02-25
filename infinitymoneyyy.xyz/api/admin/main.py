"""
Admin API FastAPI application.
Provides admin authentication with 2FA support.
"""
import asyncio
import os
from contextlib import asynccontextmanager
from typing import Optional
from fastapi import FastAPI, HTTPException, Request, status, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timedelta
from sqlalchemy import select, update, and_

from api.admin.routers import auth_router, users_router, coupons_router, analytics_router, news_router, workers_router, workers_mgmt_router, tickets_router, stats_router, transactions_router, orders_router, support, contact, maintenance, custom_pricing, internal, errors, settings, test_polygon
from api.admin.websocket import ws_manager
from api.common.database import dispose_engine, async_session_maker
from api.common.models_postgres import SupportThread, MessageStatus
from api.common.auth import decode_access_token
from api.common.models_postgres import User

# Structured logging imports
from api.common.logging_config import setup_logging, get_logger
from api.common.middleware import CorrelationIdMiddleware, PerformanceMetricsMiddleware, SecurityEventMiddleware, get_error_rate_metrics
from api.common.security_logger import SecurityEventLogger

# Setup structured logging
log_level = os.getenv('LOG_LEVEL', 'INFO')
json_enabled = os.getenv('LOG_JSON_ENABLED', 'true').lower() in ('true', '1', 'yes')
setup_logging(service_name="admin_api", log_level=log_level, json_enabled=json_enabled)
logger = get_logger(__name__)
security_logger = SecurityEventLogger("admin_api")

# Background tasks
_error_rate_monitor_task = None
_auto_close_threads_task = None
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


async def _auto_close_answered_threads():
    """Background task: close 'answered' threads after 72 hours of inactivity."""
    while True:
        try:
            await asyncio.sleep(3600)  # check every hour

            cutoff = datetime.utcnow() - timedelta(hours=72)
            async with async_session_maker() as db:
                stmt = (
                    update(SupportThread)
                    .where(
                        and_(
                            SupportThread.status == MessageStatus.answered,
                            SupportThread.last_message_at < cutoff
                        )
                    )
                    .values(status=MessageStatus.closed)
                )
                result = await db.execute(stmt)
                closed_count = result.rowcount
                await db.commit()

                if closed_count > 0:
                    logger.info(f"Auto-closed {closed_count} answered threads (inactive >72h)")

        except asyncio.CancelledError:
            logger.info("Auto-close threads task cancelled")
            break
        except Exception as e:
            logger.error(f"Error in auto-close threads task: {e}", exc_info=True)
            await asyncio.sleep(60)


# Lifespan context manager for startup/shutdown events
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle startup and shutdown events."""
    global _error_rate_monitor_task, _auto_close_threads_task

    logger.info("Admin API starting up...")
    await security_logger.log_service_startup(
        version="1.0.0",
        config={
            "workers": os.getenv('UVICORN_WORKERS_ADMIN', '2'),
            "log_level": log_level,
            "json_logging": json_enabled
        }
    )

    # Start background tasks
    _error_rate_monitor_task = asyncio.create_task(_monitor_error_rate())
    _auto_close_threads_task = asyncio.create_task(_auto_close_answered_threads())
    logger.info("Background tasks started (error rate monitor, auto-close threads)")

    yield

    # Stop background tasks
    for task in (_error_rate_monitor_task, _auto_close_threads_task):
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
    logger.info("Background tasks stopped")

    await security_logger.log_service_shutdown("graceful")
    logger.info("Admin API shutting down...")
    try:
        logger.info("Closing WebSocket connections...")
        # Close all active WebSocket connections
        for user_id in list(ws_manager.admin_connections.keys()):
            try:
                websocket = ws_manager.admin_connections[user_id]
                await websocket.close()
            except Exception:
                pass
            ws_manager.disconnect(user_id)

        for user_id in list(ws_manager.worker_connections.keys()):
            try:
                websocket = ws_manager.worker_connections[user_id]
                await websocket.close()
            except Exception:
                pass
            ws_manager.disconnect(user_id)

        logger.info("Closing database connections...")
        await dispose_engine()
        logger.info("Database connections closed successfully")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}", exc_info=True)


# Create FastAPI application
app = FastAPI(
    title="SSN Admin API",
    description="Admin API with 2FA authentication for SSN management system",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

# Configure CORS
allowed_origins = os.getenv('ALLOWED_ORIGINS', '*').split(',')
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins if allowed_origins != ['*'] else ['*'],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add middleware (order matters: last added = first executed)
app.add_middleware(SecurityEventMiddleware)
app.add_middleware(PerformanceMetricsMiddleware)
app.add_middleware(CorrelationIdMiddleware)


# Include routers
app.include_router(auth_router, prefix="/auth", tags=["Authentication"])
app.include_router(workers_router)
app.include_router(workers_mgmt_router, tags=["Workers"])
app.include_router(coupons_router, prefix="/coupons", tags=["Coupon Management"])
app.include_router(analytics_router, prefix="/analytics", tags=["Analytics & Statistics"])
app.include_router(news_router, prefix="/news", tags=["News Management"])
app.include_router(tickets_router, tags=["Manual SSN Tickets"])
app.include_router(support.router, tags=["Admin Support"])
app.include_router(contact.router, tags=["Admin Contact"])
app.include_router(stats_router, tags=["Statistics"])
app.include_router(transactions_router, prefix="/transactions", tags=["Transaction Management"])
app.include_router(orders_router, prefix="/orders", tags=["Order Management"])
app.include_router(maintenance.router, prefix="/maintenance", tags=["Maintenance Mode"])
app.include_router(custom_pricing.router, prefix="/custom-pricing", tags=["Custom Pricing"])
app.include_router(users_router, tags=["User Management"])
app.include_router(internal.router, tags=["Internal"])
app.include_router(errors.router, tags=["API Error Logs"])
app.include_router(settings.router, prefix="/settings", tags=["Settings"])
app.include_router(test_polygon.router, tags=["Test Polygon"])


# WebSocket endpoint
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: Optional[str] = Query(None)):
    """
    WebSocket endpoint for real-time admin and worker notifications.

    Requires JWT authentication via query parameter: /admin/ws?token=YOUR_JWT_TOKEN

    Connection flow:
    1. Authenticate using JWT token
    2. Validate user has admin or worker privileges
    3. Establish connection in appropriate channel (admin or worker)
    4. Receive real-time events based on role

    Args:
        websocket: WebSocket connection
        token: JWT authentication token (query parameter)
    """
    # Get client IP for security logging
    client_ip = websocket.headers.get("cf-connecting-ip") or \
                websocket.headers.get("x-forwarded-for", "").split(",")[0].strip() or \
                (websocket.client.host if websocket.client else "unknown")

    # Authentication check
    if not token:
        await websocket.close(code=1008, reason="Authentication required")
        logger.warning("WebSocket connection attempt without token")
        security_logger.log_failed_login("websocket", client_ip, "missing_token")
        return

    try:
        # Decode JWT token
        try:
            payload = decode_access_token(token)
        except HTTPException as e:
            await websocket.close(code=1008, reason="Invalid or expired token")
            logger.warning(f"WebSocket authentication failed: {e.detail}")
            security_logger.log_failed_login("websocket", client_ip, "invalid_token")
            return

        # Extract user_id from payload
        user_id = payload.get("user_id")
        if not user_id:
            await websocket.close(code=1008, reason="Invalid token payload")
            logger.warning("WebSocket token missing user_id")
            security_logger.log_failed_login("websocket", client_ip, "invalid_token_payload")
            return

        # Validate user exists and has required privileges
        async with async_session_maker() as db:
            result = await db.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()

            if not user:
                await websocket.close(code=1008, reason="User not found")
                logger.warning(f"WebSocket connection attempt by non-existent user: {user_id}")
                security_logger.log_failed_login("websocket", client_ip, "user_not_found")
                return

            if not user.is_admin:
                await websocket.close(code=1008, reason="Admin privileges required")
                logger.warning(f"WebSocket connection denied for non-admin user: {user.username}")
                security_logger.log_suspicious_activity(
                    ip=client_ip,
                    activity_type="unauthorized_ws_access",
                    details={"username": user.username, "user_id": str(user_id)}
                )
                return

        # Establish connection
        await ws_manager.connect(
            websocket,
            str(user.id),
            user.username,
            user.is_admin,
            user.worker_role
        )

        try:
            # Keep connection alive and listen for client messages
            while True:
                data = await websocket.receive_text()
                # Future: handle ping/pong or client-to-server messages
                logger.debug(f"Received message from {user.username}: {data}")

        except WebSocketDisconnect:
            logger.info(f"WebSocket disconnected: user={user.username}")
            ws_manager.disconnect(str(user.id))

        except Exception as e:
            logger.error(f"WebSocket error for user {user.username}: {e}", exc_info=True)
            ws_manager.disconnect(str(user.id))
            try:
                await websocket.close()
            except Exception:
                pass

    except Exception as e:
        logger.error(f"WebSocket connection error: {e}", exc_info=True)
        try:
            await websocket.close(code=1011, reason="Internal server error")
        except Exception:
            pass

    finally:
        # Ensure cleanup
        if 'user' in locals() and user:
            ws_manager.disconnect(str(user.id))


# Health check endpoint
@app.get("/health", tags=["Health"])
async def health_check():
    """
    Health check endpoint.

    Returns:
        dict: Service status and version
    """
    return {
        "status": "healthy",
        "service": "admin_api",
        "version": "1.0.0",
        "websocket_connections": ws_manager.get_connection_stats()
    }


# Exception handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions with consistent JSON response."""
    client_ip = request.headers.get("cf-connecting-ip") or \
                request.headers.get("x-forwarded-for", "").split(",")[0].strip() or \
                (request.client.host if request.client else "unknown")

    logger.warning(
        "HTTP exception",
        extra={
            "status_code": exc.status_code,
            "detail": exc.detail,
            "path": str(request.url),
            "client_ip": client_ip
        }
    )

    # Log authentication/authorization failures
    if exc.status_code in (401, 403):
        security_logger.log_failed_login(
            username="admin",
            ip=client_ip,
            reason=str(exc.detail),
            extra={"path": request.url.path}
        )

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.detail,
            "status_code": exc.status_code
        }
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle unexpected exceptions."""
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
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "Internal server error",
            "status_code": 500
        }
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api.admin.main:app",
        host="0.0.0.0",
        port=8002,
        reload=True,
        log_level="info"
    )
