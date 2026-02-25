"""
Internal API Router
Handles internal communication between microservices.
These endpoints are only accessible within the Docker network.
"""

import logging
from typing import Dict

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from api.public.websocket import public_ws_manager, publish_user_notification, WebSocketEventType

# Setup logging
logger = logging.getLogger(__name__)

# Router instance
router = APIRouter(prefix="/internal", tags=["Internal"])


class NotifyTicketRequest(BaseModel):
    """Request model for ticket notification"""
    user_id: str
    ticket_data: Dict


class NotifyBalanceRequest(BaseModel):
    """Request model for balance update notification"""
    user_id: str
    balance_data: Dict


class NotifyThreadMessageRequest(BaseModel):
    """Request model for thread message notification from admin"""
    user_id: str
    message_data: Dict


class NotifyThreadStatusRequest(BaseModel):
    """Request model for thread status update from admin"""
    user_id: str
    status_data: Dict


@router.post("/notify-ticket-created")
async def notify_ticket_created(
    request: NotifyTicketRequest,
) -> Dict[str, str]:
    """
    Notify bots about ticket creation via WebSocket.
    Internal endpoint for Admin API.
    """
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
) -> Dict[str, str]:
    """
    Notify bots about ticket update via WebSocket.
    Internal endpoint for Admin API.
    """
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
) -> Dict[str, str]:
    """
    Notify bots about ticket completion via WebSocket.
    Internal endpoint for Admin API.
    """
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


@router.post("/notify-thread-message")
async def notify_thread_message(
    request: NotifyThreadMessageRequest,
) -> Dict[str, str]:
    """
    Notify user about a new message in their support thread via WebSocket.
    Internal endpoint called by Admin API when admin replies.
    Uses Redis pub/sub to reach the correct worker holding the user's WebSocket.
    """
    try:
        await publish_user_notification(
            request.user_id,
            WebSocketEventType.THREAD_MESSAGE_ADDED,
            request.message_data
        )
        logger.info(f"Published thread_message_added for user {request.user_id}")
        return {"status": "success", "message": "Notification published"}

    except Exception as e:
        logger.error(f"Error publishing thread_message_added: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send notification"
        )


@router.post("/notify-thread-status")
async def notify_thread_status(
    request: NotifyThreadStatusRequest,
) -> Dict[str, str]:
    """
    Notify user about their support thread status change via WebSocket.
    Internal endpoint called by Admin API when admin updates thread status.
    Uses Redis pub/sub to reach the correct worker holding the user's WebSocket.
    """
    try:
        await publish_user_notification(
            request.user_id,
            WebSocketEventType.THREAD_STATUS_UPDATED,
            request.status_data
        )
        logger.info(f"Published thread_status_updated for user {request.user_id}")
        return {"status": "success", "message": "Notification published"}

    except Exception as e:
        logger.error(f"Error publishing thread_status_updated: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send notification"
        )


@router.post("/notify-balance-updated")
async def notify_balance_updated(
    request: NotifyBalanceRequest,
) -> Dict[str, str]:
    """
    Notify user about balance change (e.g. refund after ticket rejection).
    Internal endpoint called by Worker API.
    Uses Redis pub/sub to reach the correct worker holding the user's WebSocket.
    """
    try:
        await publish_user_notification(
            request.user_id,
            WebSocketEventType.BALANCE_UPDATED,
            request.balance_data
        )
        logger.info(f"Published balance_updated for user {request.user_id}")
        return {"status": "success", "message": "Balance notification published"}

    except Exception as e:
        logger.error(f"Error publishing balance_updated: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send balance notification"
        )
