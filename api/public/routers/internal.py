"""
Internal API Router
Handles internal communication between microservices.
"""

import logging
import os
from typing import Dict

from fastapi import APIRouter, HTTPException, Header, status
from pydantic import BaseModel

from api.public.websocket import public_ws_manager

# Setup logging
logger = logging.getLogger(__name__)

# Router instance
router = APIRouter(prefix="/internal", tags=["Internal"])

# Get internal API key from environment
INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY", "")


class NotifyTicketRequest(BaseModel):
    """Request model for ticket notification"""
    user_id: str
    ticket_data: Dict


def verify_internal_api_key(x_internal_api_key: str = Header(...)) -> None:
    """
    Verify internal API key from request header.

    Args:
        x_internal_api_key: API key from X-Internal-Api-Key header

    Raises:
        HTTPException: If API key is invalid
    """
    if not INTERNAL_API_KEY:
        logger.error("INTERNAL_API_KEY not configured in environment")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal API not configured"
        )

    if x_internal_api_key != INTERNAL_API_KEY:
        logger.warning("Invalid internal API key attempt")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key"
        )


@router.post("/notify-ticket-created")
async def notify_ticket_created(
    request: NotifyTicketRequest,
    x_internal_api_key: str = Header(...)
) -> Dict[str, str]:
    """
    Notify bots about ticket creation via WebSocket.
    Internal endpoint for Admin API.

    Args:
        request: Notification request with user_id and ticket_data
        x_internal_api_key: Internal API key

    Returns:
        Success message
    """
    verify_internal_api_key(x_internal_api_key)

    try:
        await public_ws_manager.notify_ticket_created(
            request.user_id,
            request.ticket_data
        )
        logger.info(f"Broadcasted ticket_created for user {request.user_id} to bots")
        return {"status": "success", "message": "Notification sent to bots"}

    except Exception as e:
        logger.error(f"Error broadcasting ticket_created: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to broadcast notification"
        )


@router.post("/notify-ticket-updated")
async def notify_ticket_updated(
    request: NotifyTicketRequest,
    x_internal_api_key: str = Header(...)
) -> Dict[str, str]:
    """
    Notify bots about ticket update via WebSocket.
    Internal endpoint for Admin API.

    Args:
        request: Notification request with user_id and ticket_data
        x_internal_api_key: Internal API key

    Returns:
        Success message
    """
    verify_internal_api_key(x_internal_api_key)

    try:
        await public_ws_manager.notify_ticket_updated(
            request.user_id,
            request.ticket_data
        )
        logger.info(f"Broadcasted ticket_updated for user {request.user_id} to bots")
        return {"status": "success", "message": "Notification sent to bots"}

    except Exception as e:
        logger.error(f"Error broadcasting ticket_updated: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to broadcast notification"
        )


@router.post("/notify-ticket-completed")
async def notify_ticket_completed(
    request: NotifyTicketRequest,
    x_internal_api_key: str = Header(...)
) -> Dict[str, str]:
    """
    Notify bots about ticket completion via WebSocket.
    Internal endpoint for Admin API.

    Args:
        request: Notification request with user_id and ticket_data
        x_internal_api_key: Internal API key

    Returns:
        Success message
    """
    verify_internal_api_key(x_internal_api_key)

    try:
        await public_ws_manager.notify_ticket_completed(
            request.user_id,
            request.ticket_data
        )
        logger.info(f"Broadcasted ticket_completed for user {request.user_id} to bots")
        return {"status": "success", "message": "Notification sent to bots"}

    except Exception as e:
        logger.error(f"Error broadcasting ticket_completed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to broadcast notification"
        )
