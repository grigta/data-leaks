"""
Worker API FastAPI application.
Provides worker authentication and ticket management for qwertyworkforever.top.
"""
import os
from typing import Optional
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from api.worker.routers.auth import router as auth_router
from api.worker.routers.tickets import router as tickets_router
from api.worker.routers.wallet import router as wallet_router
from api.worker.routers.shift import router as shift_router
from api.worker.websocket import ws_manager
from api.common.database import dispose_engine
from api.common.auth import decode_access_token

import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle startup and shutdown events."""
    logger.info("Worker API starting up...")
    yield
    logger.info("Worker API shutting down...")
    try:
        await dispose_engine()
        logger.info("Database connections closed")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")


app = FastAPI(
    title="Worker API",
    description="Worker portal API for ticket management",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

# CORS
allowed_origins = os.getenv('ALLOWED_ORIGINS', 'https://qwertyworkforever.top').split(',')
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth_router, prefix="/auth")
app.include_router(tickets_router, prefix="/tickets")
app.include_router(wallet_router, prefix="/wallet")
app.include_router(shift_router, prefix="/shift")


@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "worker_api",
        "version": "1.0.0"
    }


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: Optional[str] = Query(None)):
    """WebSocket for real-time worker notifications. Supports optional JWT auth for online tracking."""
    user_id = None

    # Try to authenticate if token provided
    if token:
        try:
            payload = decode_access_token(token)
            user_id = payload.get("user_id")
            if user_id:
                logger.info(f"Worker WS authenticated: user_id={user_id}")
        except Exception as e:
            logger.warning(f"Worker WS auth failed: {e}")
            # Still allow connection, just without tracking

    await ws_manager.connect(websocket, user_id=user_id)
    try:
        while True:
            # Keep connection alive, ignore incoming messages
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, user_id=user_id)
    except Exception:
        ws_manager.disconnect(websocket, user_id=user_id)


@app.post("/internal/notify-new-ticket", tags=["Internal"])
async def notify_new_ticket():
    """Called by public_api when a new ManualSSNTicket is created."""
    await ws_manager.broadcast("NEW_TICKET")
    return {"status": "ok"}


@app.post("/internal/notify-shift-from-admin", tags=["Internal"])
async def notify_shift_from_admin(request: Request):
    """Called by admin_api when admin force-stops a worker's shift."""
    data = await request.json()
    worker_id = data.get("worker_id")
    shift_data = data.get("shift_data")
    if worker_id and shift_data:
        await ws_manager.send_to_worker(worker_id, "SHIFT_UPDATED", shift_data)
    return {"status": "ok"}


@app.get("/internal/online-workers", tags=["Internal"])
async def get_online_workers():
    """Return list of online worker user IDs. Called by admin_api."""
    return {"online_worker_ids": ws_manager.get_online_worker_ids()}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api.worker.main:app",
        host="0.0.0.0",
        port=8003,
        reload=True,
        log_level="info"
    )
