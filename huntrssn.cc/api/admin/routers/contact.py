"""
Admin Contact Router
Handles contact thread and message management for admins.
"""

import logging
from typing import List, Optional
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func, update, desc, and_, distinct
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from pydantic import BaseModel, Field

from api.common.database import get_postgres_session
from api.common.models_postgres import ContactThread, ContactMessage, MessageStatus, MessageType, ContactMessageType, User
from api.admin.dependencies import get_current_admin_user
from api.admin.websocket import ws_manager
from api.public.websocket import ws_manager as public_ws_manager

# Setup logging
logger = logging.getLogger(__name__)

# Router instance
router = APIRouter(prefix="/contact", tags=["Admin Contact"])


# Pydantic models for thread-based API
class CreateMessageRequest(BaseModel):
    """Request model for admin reply to thread"""
    message: str = Field(..., min_length=1, max_length=2000)


class UpdateThreadStatusRequest(BaseModel):
    """Request model for updating thread status"""
    status: str = Field(..., pattern="^(pending|answered|closed)$")


class MessageResponse(BaseModel):
    """Response model for individual message in thread"""
    id: str
    thread_id: str
    message: str
    message_type: str
    is_read: bool
    created_at: str
    sender_username: str
    responded_by_username: Optional[str] = None

    @classmethod
    def from_message(cls, message: ContactMessage, responded_by_username: Optional[str] = None) -> "MessageResponse":
        """Convert ContactMessage model to response"""
        return cls(
            id=str(message.id),
            thread_id=str(message.thread_id),
            message=message.message,
            message_type=message.message_type.value,
            is_read=message.is_read,
            created_at=message.created_at.isoformat(),
            sender_username=message.user.username if message.user else "Unknown",
            responded_by_username=responded_by_username
        )


class MessageListResponse(BaseModel):
    """Response model for list of messages in a thread"""
    messages: List[MessageResponse]
    total_count: int


class ThreadResponse(BaseModel):
    """Response model for contact thread"""
    id: str
    user_id: str
    username: str
    message_type: str
    status: str
    last_message_at: str
    unread_count: int
    created_at: str
    updated_at: str
    last_message_preview: Optional[str] = None

    @classmethod
    def from_thread(cls, thread: ContactThread, unread_count: int = 0, last_message_preview: Optional[str] = None) -> "ThreadResponse":
        """Convert ContactThread model to response"""
        return cls(
            id=str(thread.id),
            user_id=str(thread.user_id),
            username=thread.user.username if thread.user else "Unknown",
            message_type=thread.message_type.value,
            status=thread.status.value,
            last_message_at=thread.last_message_at.isoformat(),
            unread_count=unread_count,
            created_at=thread.created_at.isoformat(),
            updated_at=thread.updated_at.isoformat(),
            last_message_preview=last_message_preview
        )


class ThreadListResponse(BaseModel):
    """Response model for list of contact threads"""
    threads: List[ThreadResponse]
    total_count: int


# Thread-based endpoints
@router.get("/threads", response_model=ThreadListResponse)
async def get_contact_threads(
    status_filter: Optional[str] = None,
    message_type_filter: Optional[str] = None,
    unread_only: bool = False,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_postgres_session),
    current_user: User = Depends(get_current_admin_user)
):
    """Get all contact threads (admin view)."""
    try:
        query = select(ContactThread).options(selectinload(ContactThread.user))

        if status_filter:
            try:
                status_enum = MessageStatus(status_filter)
                query = query.where(ContactThread.status == status_enum)
            except ValueError:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid status filter: {status_filter}")

        if message_type_filter:
            try:
                type_enum = ContactMessageType(message_type_filter)
                query = query.where(ContactThread.message_type == type_enum)
            except ValueError:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid message type filter: {message_type_filter}")

        if unread_only:
            unread_subquery = (
                select(distinct(ContactMessage.thread_id))
                .where(and_(ContactMessage.message_type == MessageType.user, ContactMessage.is_read == False))
            )
            query = query.where(ContactThread.id.in_(unread_subquery))

        count_query = select(func.count()).select_from(query.subquery())
        total_count = await db.scalar(count_query)

        query = query.order_by(desc(ContactThread.last_message_at)).limit(limit).offset(offset)

        result = await db.execute(query)
        threads = result.scalars().all()

        thread_ids = [thread.id for thread in threads]
        unread_counts = {}
        if thread_ids:
            unread_query = (
                select(ContactMessage.thread_id, func.count().label('unread_count'))
                .where(and_(ContactMessage.thread_id.in_(thread_ids), ContactMessage.message_type == MessageType.user, ContactMessage.is_read == False))
                .group_by(ContactMessage.thread_id)
            )
            unread_result = await db.execute(unread_query)
            unread_counts = {row.thread_id: row.unread_count for row in unread_result}

        last_messages = {}
        if thread_ids:
            latest_msg_subq = (
                select(
                    ContactMessage.thread_id,
                    ContactMessage.message,
                    func.row_number().over(partition_by=ContactMessage.thread_id, order_by=desc(ContactMessage.created_at)).label('rn')
                )
                .where(ContactMessage.thread_id.in_(thread_ids))
                .subquery()
            )
            latest_msg_query = select(latest_msg_subq.c.thread_id, latest_msg_subq.c.message).where(latest_msg_subq.c.rn == 1)
            latest_result = await db.execute(latest_msg_query)
            last_messages = {row.thread_id: row.message[:100] for row in latest_result}

        thread_responses = []
        for thread in threads:
            unread_count = unread_counts.get(thread.id, 0)
            last_msg_preview = last_messages.get(thread.id)
            thread_responses.append(ThreadResponse.from_thread(thread, unread_count, last_msg_preview))

        logger.info(f"Admin {current_user.username} retrieved {len(threads)} contact threads (total: {total_count})")

        return ThreadListResponse(threads=thread_responses, total_count=total_count or 0)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving contact threads: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve contact threads")


@router.get("/threads/unread-count")
async def get_unread_threads_count(
    db: AsyncSession = Depends(get_postgres_session),
    current_user: User = Depends(get_current_admin_user)
):
    """Get count of threads with unread user messages."""
    try:
        query = select(func.count(distinct(ContactMessage.thread_id))).where(
            and_(ContactMessage.message_type == MessageType.user, ContactMessage.is_read == False)
        )
        count = await db.scalar(query) or 0
        logger.info(f"Admin {current_user.username} retrieved unread contact thread count: {count}")
        return {"count": count}
    except Exception as e:
        logger.error(f"Error getting unread thread count: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to get unread thread count")


@router.get("/threads/{thread_id}", response_model=ThreadResponse)
async def get_contact_thread_details(
    thread_id: UUID,
    db: AsyncSession = Depends(get_postgres_session),
    current_user: User = Depends(get_current_admin_user)
):
    """Get details of a specific contact thread (admin view)."""
    try:
        query = select(ContactThread).where(ContactThread.id == thread_id).options(selectinload(ContactThread.user))
        result = await db.execute(query)
        thread = result.scalar_one_or_none()

        if not thread:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact thread not found")

        unread_query = select(func.count()).where(
            and_(ContactMessage.thread_id == thread.id, ContactMessage.message_type == MessageType.user, ContactMessage.is_read == False)
        )
        unread_count = await db.scalar(unread_query) or 0

        logger.info(f"Admin {current_user.username} retrieved contact thread {thread_id}")
        return ThreadResponse.from_thread(thread, unread_count)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving contact thread {thread_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve contact thread")


@router.get("/threads/{thread_id}/messages", response_model=MessageListResponse)
async def get_thread_messages(
    thread_id: UUID,
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_postgres_session),
    current_user: User = Depends(get_current_admin_user)
):
    """Get messages in a contact thread (admin view)."""
    try:
        thread_query = select(ContactThread).where(ContactThread.id == thread_id)
        thread_result = await db.execute(thread_query)
        thread = thread_result.scalar_one_or_none()

        if not thread:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact thread not found")

        query = select(ContactMessage).where(ContactMessage.thread_id == thread_id).options(selectinload(ContactMessage.user))

        count_query = select(func.count()).select_from(query.subquery())
        total_count = await db.scalar(count_query)

        query = query.order_by(ContactMessage.created_at.asc()).limit(limit).offset(offset)

        result = await db.execute(query)
        messages = result.scalars().all()

        logger.info(f"Admin {current_user.username} retrieved {len(messages)} messages for contact thread {thread_id}")

        return MessageListResponse(messages=[MessageResponse.from_message(msg) for msg in messages], total_count=total_count or 0)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving messages for contact thread {thread_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve thread messages")


@router.post("/threads/{thread_id}/messages", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
async def reply_to_thread(
    thread_id: UUID,
    data: CreateMessageRequest,
    db: AsyncSession = Depends(get_postgres_session),
    current_user: User = Depends(get_current_admin_user)
):
    """Reply to a contact thread."""
    try:
        thread_query = select(ContactThread).where(ContactThread.id == thread_id)
        thread_result = await db.execute(thread_query)
        thread = thread_result.scalar_one_or_none()

        if not thread:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact thread not found")

        new_message = ContactMessage(
            thread_id=thread_id,
            user_id=current_user.id,
            message=data.message,
            message_type=MessageType.admin,
            is_read=False
        )
        db.add(new_message)

        thread.last_message_at = func.now()
        if thread.status == MessageStatus.pending:
            thread.status = MessageStatus.answered

        # Mark all user messages as read
        update_stmt = (
            update(ContactMessage)
            .where(and_(ContactMessage.thread_id == thread_id, ContactMessage.message_type == MessageType.user, ContactMessage.is_read == False))
            .values(is_read=True)
        )
        await db.execute(update_stmt)

        await db.flush()
        await db.refresh(new_message, ["user"])
        await db.commit()

        logger.info(f"Admin {current_user.username} replied to contact thread {thread_id}")

        message_data = {
            "thread_id": str(thread_id),
            "message_id": str(new_message.id),
            "message": new_message.message,
            "message_type": new_message.message_type.value,
            "sender_username": current_user.username,
            "created_at": new_message.created_at.isoformat()
        }
        await ws_manager.broadcast_contact_thread_message_added(message_data)
        await public_ws_manager.send_to_user(str(thread.user_id), "contact_thread_message_added", message_data)

        return MessageResponse.from_message(new_message, responded_by_username=current_user.username)

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error replying to contact thread {thread_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to reply to thread")


@router.patch("/threads/{thread_id}/status", response_model=ThreadResponse)
async def update_thread_status(
    thread_id: UUID,
    data: UpdateThreadStatusRequest,
    db: AsyncSession = Depends(get_postgres_session),
    current_user: User = Depends(get_current_admin_user)
):
    """Update contact thread status."""
    try:
        thread_query = select(ContactThread).where(ContactThread.id == thread_id).options(selectinload(ContactThread.user))
        thread_result = await db.execute(thread_query)
        thread = thread_result.scalar_one_or_none()

        if not thread:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact thread not found")

        try:
            status_enum = MessageStatus(data.status)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid status: {data.status}")

        thread.status = status_enum
        await db.commit()

        logger.info(f"Admin {current_user.username} updated contact thread {thread_id} status to {data.status}")

        status_data = {
            "thread_id": str(thread_id),
            "status": data.status,
            "updated_at": datetime.utcnow().isoformat()
        }
        await ws_manager.broadcast_contact_thread_status_updated(status_data)
        await public_ws_manager.send_to_user(str(thread.user_id), "contact_thread_status_updated", status_data)

        return ThreadResponse.from_thread(thread, unread_count=0)

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error updating contact thread {thread_id} status: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update thread status")


@router.patch("/threads/{thread_id}/mark-read")
async def mark_thread_messages_as_read(
    thread_id: UUID,
    db: AsyncSession = Depends(get_postgres_session),
    current_user: User = Depends(get_current_admin_user)
):
    """Mark all user messages in a thread as read (admin action)."""
    try:
        thread_query = select(ContactThread).where(ContactThread.id == thread_id)
        thread_result = await db.execute(thread_query)
        thread = thread_result.scalar_one_or_none()

        if not thread:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact thread not found")

        update_stmt = (
            update(ContactMessage)
            .where(and_(ContactMessage.thread_id == thread_id, ContactMessage.message_type == MessageType.user, ContactMessage.is_read == False))
            .values(is_read=True)
        )
        result = await db.execute(update_stmt)
        updated_count = result.rowcount

        await db.commit()

        logger.info(f"Admin {current_user.username} marked {updated_count} user messages as read in contact thread {thread_id}")

        read_data = {
            "thread_id": str(thread_id),
            "read_count": updated_count,
            "updated_at": datetime.utcnow().isoformat()
        }
        await ws_manager.broadcast_contact_thread_messages_read(read_data)

        return {"success": True, "updated_count": updated_count}

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error marking messages as read in contact thread {thread_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to mark messages as read")


# ============================================================================
# DEPRECATED ENDPOINTS (kept for backward compatibility)
# ============================================================================

class RespondToContactMessageRequest(BaseModel):
    """DEPRECATED: Request model for responding to contact message"""
    response: str = Field(..., min_length=1, max_length=2000)


class ContactMessageResponse(BaseModel):
    """DEPRECATED: Response model for contact message data"""
    id: str
    user_id: str
    username: str
    message_type: str
    message: str
    admin_response: Optional[str] = None
    status: str
    responded_by: Optional[str] = None
    responded_at: Optional[str] = None
    created_at: str
    updated_at: str


class ContactMessageListResponse(BaseModel):
    """DEPRECATED: Response model for list of contact messages"""
    messages: List[ContactMessageResponse]
    total_count: int


@router.get("/messages", response_model=ContactMessageListResponse, deprecated=True)
async def get_contact_messages(
    db: AsyncSession = Depends(get_postgres_session),
    current_user: User = Depends(get_current_admin_user)
):
    """DEPRECATED: Use GET /threads instead."""
    return ContactMessageListResponse(messages=[], total_count=0)


@router.get("/messages/{message_id}", deprecated=True)
async def get_contact_message_details(message_id: UUID):
    """DEPRECATED: Use GET /threads/{thread_id} instead."""
    raise HTTPException(status_code=status.HTTP_410_GONE, detail="This endpoint is deprecated. Use GET /threads/{thread_id} instead.")


@router.post("/messages/{message_id}/respond", deprecated=True)
async def respond_to_contact_message(message_id: UUID):
    """DEPRECATED: Use POST /threads/{thread_id}/messages instead."""
    raise HTTPException(status_code=status.HTTP_410_GONE, detail="This endpoint is deprecated. Use POST /threads/{thread_id}/messages instead.")


@router.patch("/messages/{message_id}/status", deprecated=True)
async def update_contact_message_status(message_id: UUID):
    """DEPRECATED: Use PATCH /threads/{thread_id}/status instead."""
    raise HTTPException(status_code=status.HTTP_410_GONE, detail="This endpoint is deprecated. Use PATCH /threads/{thread_id}/status instead.")
