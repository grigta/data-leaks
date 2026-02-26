"""
Internal API Router for Admin API.
Handles internal communication from other microservices (e.g., Public API).
These endpoints are only accessible within the Docker network.
"""

import logging
from typing import Dict

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from api.admin.websocket import ws_manager

# Setup logging
logger = logging.getLogger(__name__)

# Router instance
router = APIRouter(prefix="/internal", tags=["Internal"])


class NotifyTicketRequest(BaseModel):
    """Request model for ticket notification"""
    ticket_data: Dict


class NotifyThreadRequest(BaseModel):
    """Request model for thread notification"""
    thread_data: Dict


class NotifyThreadMessageRequest(BaseModel):
    """Request model for thread message notification"""
    message_data: Dict


class NotifyInvoiceRequest(BaseModel):
    """Request model for worker invoice notification"""
    invoice_data: Dict


class NotifyScheduleRequest(BaseModel):
    """Request model for worker schedule notification"""
    schedule_data: Dict


class NotifyShiftRequest(BaseModel):
    """Request model for worker shift status notification"""
    shift_data: Dict


@router.post("/notify-ticket-created")
async def notify_ticket_created(
    request: NotifyTicketRequest,
) -> Dict[str, str]:
    """
    Receive ticket creation notification from Public API and broadcast to admins via WebSocket.
    """
    try:
        await ws_manager.broadcast_ticket_created(request.ticket_data)
        ticket_id = request.ticket_data.get("id", "unknown")
        logger.info(f"Broadcasted ticket_created to admins for ticket {ticket_id}")
        return {"status": "success", "message": "Notification broadcasted to admins"}

    except HTTPException:
        raise
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
    Receive ticket update notification from Worker API and broadcast to admins via WebSocket.
    Called when worker completes, rejects, or claims a ticket.
    """
    try:
        await ws_manager.broadcast_ticket_updated(request.ticket_data)
        ticket_id = request.ticket_data.get("id", "unknown")
        ticket_status = request.ticket_data.get("status", "unknown")
        logger.info(f"Broadcasted ticket_updated to admins for ticket {ticket_id} (status={ticket_status})")
        return {"status": "success", "message": "Notification broadcasted to admins"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error broadcasting ticket_updated: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to broadcast notification"
        )


@router.post("/notify-thread-created")
async def notify_thread_created(
    request: NotifyThreadRequest,
) -> Dict[str, str]:
    """
    Receive thread creation notification from Public API and broadcast to admins via WebSocket.
    """
    try:
        await ws_manager.broadcast_thread_created(request.thread_data)
        thread_id = request.thread_data.get("id", "unknown")
        logger.info(f"Broadcasted thread_created to admins for thread {thread_id}")
        return {"status": "success", "message": "Thread notification broadcasted to admins"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error broadcasting thread_created: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to broadcast thread notification"
        )


@router.post("/notify-thread-message")
async def notify_thread_message(
    request: NotifyThreadMessageRequest,
) -> Dict[str, str]:
    """
    Receive thread message notification from Public API and broadcast to admins via WebSocket.
    """
    try:
        await ws_manager.broadcast_thread_message_added(request.message_data)
        thread_id = request.message_data.get("thread_id", "unknown")
        logger.info(f"Broadcasted thread_message_added to admins for thread {thread_id}")
        return {"status": "success", "message": "Thread message notification broadcasted to admins"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error broadcasting thread_message_added: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to broadcast thread message notification"
        )


@router.post("/notify-invoice-created")
async def notify_invoice_created(
    request: NotifyInvoiceRequest,
) -> Dict[str, str]:
    """
    Receive worker invoice creation notification from Worker API and broadcast to admins via WebSocket.
    """
    try:
        await ws_manager.broadcast_to_admins("worker_invoice_created", request.invoice_data)
        invoice_id = request.invoice_data.get("id", "unknown")
        logger.info(f"Broadcasted worker_invoice_created to admins for invoice {invoice_id}")
        return {"status": "success", "message": "Invoice notification broadcasted to admins"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error broadcasting worker_invoice_created: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to broadcast invoice notification"
        )


@router.post("/notify-schedule-updated")
async def notify_schedule_updated(
    request: NotifyScheduleRequest,
) -> Dict[str, str]:
    """
    Receive worker schedule update notification from Worker API and broadcast to admins via WebSocket.
    Called when worker changes their schedule or pause status.
    """
    try:
        await ws_manager.broadcast_to_admins("worker_schedule_updated", request.schedule_data)
        worker_id = request.schedule_data.get("worker_id", "unknown")
        logger.info(f"Broadcasted worker_schedule_updated to admins for worker {worker_id}")
        return {"status": "success", "message": "Schedule notification broadcasted to admins"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error broadcasting worker_schedule_updated: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to broadcast schedule notification"
        )


@router.post("/notify-shift-updated")
async def notify_shift_updated(
    request: NotifyShiftRequest,
) -> Dict[str, str]:
    """
    Receive worker shift status notification from Worker API and broadcast to admins via WebSocket.
    Called when worker starts/pauses/resumes/stops a shift.
    """
    try:
        await ws_manager.broadcast_to_admins("worker_shift_updated", request.shift_data)
        worker_id = request.shift_data.get("worker_id", "unknown")
        logger.info(f"Broadcasted worker_shift_updated to admins for worker {worker_id}")
        return {"status": "success", "message": "Shift notification broadcasted to admins"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error broadcasting worker_shift_updated: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to broadcast shift notification"
        )
