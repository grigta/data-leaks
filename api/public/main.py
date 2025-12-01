"""
Public API FastAPI application.
"""
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from api.public.routers import auth_router, search_router, ecommerce_router, stats_router, enrichment_router, billing_router, news_router, tickets_router, internal_router, support, contact, maintenance_router, admin_router
from api.common.database import dispose_engine
from api.public.websocket import public_ws_manager
from api.public.dependencies import get_current_user_ws
from api.common.models_postgres import User
from datetime import datetime
import logging
import os
import uuid
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from api.public.dependencies import limiter


# Configure logging
logging.basicConfig(level=os.getenv('LOG_LEVEL', 'INFO'))
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="SSN Public API",
    version="1.0.0",
    description="Public API for SSN search and e-commerce"
)

# Register SlowAPI limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

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
    logger.error(f"[VALIDATION-ERROR] Path: {request.url.path}")
    logger.error(f"[VALIDATION-ERROR] Errors: {exc.errors()}")
    logger.error(f"[VALIDATION-ERROR] Body: {exc.body if hasattr(exc, 'body') else 'N/A'}")
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
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "timestamp": datetime.now().isoformat()
        }
    )


# Startup/shutdown events
@app.on_event("startup")
async def startup_event():
    """Startup event handler."""
    logger.info("Public API starting up...")


@app.on_event("shutdown")
async def shutdown_event():
    """Shutdown event handler."""
    logger.info("Public API shutting down...")
    try:
        logger.info("Closing database connections...")
        await dispose_engine()
        logger.info("Database connections closed successfully")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}", exc_info=True)
