"""
Admin Support Router
Handles support thread and message management for admins.
"""

import logging
import os
from typing import List, Optional
from uuid import UUID
from datetime import datetime

import aiohttp
from fastapi import APIRouter, Depends, HTTPException, status, Body
from sqlalchemy import select, func, update, desc, and_, distinct
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from pydantic import BaseModel, Field

from api.common.database import get_postgres_session
from api.common.models_postgres import SupportThread, SupportMessage, MessageStatus, MessageType, User, SupportMessageType
from api.admin.dependencies import get_current_admin_user
from api.admin.websocket import ws_manager

# Public API internal URL for cross-service notifications (admin → user)
PUBLIC_API_INTERNAL_URL = os.getenv("PUBLIC_API_INTERNAL_URL", "http://public_api:8000")

# Setup logging
logger = logging.getLogger(__name__)

# Router instance
router = APIRouter(prefix="/support", tags=["Admin Support"])


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
    def from_message(cls, message: SupportMessage, responded_by_username: Optional[str] = None) -> "MessageResponse":
        """Convert SupportMessage model to response"""
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
    """Response model for support thread"""
    id: str
    user_id: str
    username: str
    message_type: str
    subject: Optional[str]
    status: str
    last_message_at: str
    unread_count: int
    created_at: str
    updated_at: str
    last_message_preview: Optional[str] = None

    @classmethod
    def from_thread(cls, thread: SupportThread, unread_count: int = 0, last_message_preview: Optional[str] = None) -> "ThreadResponse":
        """Convert SupportThread model to response"""
        return cls(
            id=str(thread.id),
            user_id=str(thread.user_id),
            username=thread.user.username if thread.user else "Unknown",
            message_type=thread.message_type.value,
            subject=thread.subject,
            status=thread.status.value,
            last_message_at=thread.last_message_at.isoformat(),
            unread_count=unread_count,
            created_at=thread.created_at.isoformat(),
            updated_at=thread.updated_at.isoformat(),
            last_message_preview=last_message_preview
        )


class ThreadListResponse(BaseModel):
    """Response model for list of support threads"""
    threads: List[ThreadResponse]
    total_count: int


# Thread-based endpoints
@router.get("/threads", response_model=ThreadListResponse)
async def get_support_threads(
    status_filter: Optional[str] = None,
    message_type_filter: Optional[str] = None,
    unread_only: bool = False,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_postgres_session),
    current_user: User = Depends(get_current_admin_user)
):
    """
    Get all support threads (admin view).

    Args:
        status_filter: Optional filter by status ('pending', 'answered', 'closed')
        message_type_filter: Optional filter by message type ('bug_report', 'feature_request', 'general_question')
        unread_only: Show only threads with unread user messages
        limit: Maximum number of threads to return
        offset: Number of threads to skip
        db: Database session
        current_user: Current authenticated admin

    Returns:
        List of support threads
    """
    try:
        # Build query with eager loading
        query = select(SupportThread).options(selectinload(SupportThread.user))

        # Apply status filter if provided
        if status_filter:
            try:
                status_enum = MessageStatus(status_filter)
                query = query.where(SupportThread.status == status_enum)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid status filter: {status_filter}"
                )

        # Apply message type filter if provided
        if message_type_filter:
            try:
                message_type_enum = SupportMessageType(message_type_filter)
                query = query.where(SupportThread.message_type == message_type_enum)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid message type filter: {message_type_filter}"
                )

        # Apply unread filter if requested
        if unread_only:
            # Subquery to find threads with unread user messages
            unread_subquery = (
                select(distinct(SupportMessage.thread_id))
                .where(
                    and_(
                        SupportMessage.message_type == MessageType.user,
                        SupportMessage.is_read == False
                    )
                )
            )
            query = query.where(SupportThread.id.in_(unread_subquery))

        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total_count = await db.scalar(count_query)

        # Apply pagination and ordering
        query = query.order_by(desc(SupportThread.last_message_at)).limit(limit).offset(offset)

        # Execute query
        result = await db.execute(query)
        threads = result.scalars().all()

        # Optimize: Get unread counts for all threads in one query
        thread_ids = [thread.id for thread in threads]
        unread_counts = {}
        if thread_ids:
            unread_query = (
                select(
                    SupportMessage.thread_id,
                    func.count().label('unread_count')
                )
                .where(
                    and_(
                        SupportMessage.thread_id.in_(thread_ids),
                        SupportMessage.message_type == MessageType.user,
                        SupportMessage.is_read == False
                    )
                )
                .group_by(SupportMessage.thread_id)
            )
            unread_result = await db.execute(unread_query)
            unread_counts = {row.thread_id: row.unread_count for row in unread_result}

        # Optimize: Get last message for each thread in one query using window function
        last_messages = {}
        if thread_ids:
            # Subquery to get the latest message per thread
            latest_msg_subq = (
                select(
                    SupportMessage.thread_id,
                    SupportMessage.message,
                    func.row_number().over(
                        partition_by=SupportMessage.thread_id,
                        order_by=desc(SupportMessage.created_at)
                    ).label('rn')
                )
                .where(SupportMessage.thread_id.in_(thread_ids))
                .subquery()
            )

            latest_msg_query = select(
                latest_msg_subq.c.thread_id,
                latest_msg_subq.c.message
            ).where(latest_msg_subq.c.rn == 1)

            latest_result = await db.execute(latest_msg_query)
            last_messages = {row.thread_id: row.message[:100] for row in latest_result}

        # Build thread responses
        thread_responses = []
        for thread in threads:
            unread_count = unread_counts.get(thread.id, 0)
            last_msg_preview = last_messages.get(thread.id)
            thread_responses.append(
                ThreadResponse.from_thread(thread, unread_count, last_msg_preview)
            )

        logger.info(
            f"Admin {current_user.username} retrieved {len(threads)} support threads "
            f"(total: {total_count}, filter: {status_filter}, unread_only: {unread_only})"
        )

        return ThreadListResponse(
            threads=thread_responses,
            total_count=total_count or 0
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving support threads: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve support threads"
        )


@router.get("/threads/unread-count")
async def get_unread_threads_count(
    db: AsyncSession = Depends(get_postgres_session),
    current_user: User = Depends(get_current_admin_user)
):
    """
    Get count of threads with unread user messages.

    Args:
        db: Database session
        current_user: Current authenticated admin

    Returns:
        Count of threads with unread messages
    """
    try:
        # Count distinct threads with unread user messages
        query = select(func.count(distinct(SupportMessage.thread_id))).where(
            and_(
                SupportMessage.message_type == MessageType.user,
                SupportMessage.is_read == False
            )
        )
        count = await db.scalar(query) or 0

        logger.info(f"Admin {current_user.username} retrieved unread thread count: {count}")

        return {"count": count}

    except Exception as e:
        logger.error(f"Error getting unread thread count: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get unread thread count"
        )


@router.get("/threads/{thread_id}", response_model=ThreadResponse)
async def get_support_thread_details(
    thread_id: UUID,
    db: AsyncSession = Depends(get_postgres_session),
    current_user: User = Depends(get_current_admin_user)
):
    """
    Get details of a specific support thread (admin view).

    Args:
        thread_id: Thread ID
        db: Database session
        current_user: Current authenticated admin

    Returns:
        Support thread details
    """
    try:
        # Query thread with user relationship
        query = select(SupportThread).where(
            SupportThread.id == thread_id
        ).options(selectinload(SupportThread.user))

        result = await db.execute(query)
        thread = result.scalar_one_or_none()

        if not thread:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Support thread not found"
            )

        # Count unread user messages
        unread_query = select(func.count()).where(
            and_(
                SupportMessage.thread_id == thread.id,
                SupportMessage.message_type == MessageType.user,
                SupportMessage.is_read == False
            )
        )
        unread_count = await db.scalar(unread_query) or 0

        logger.info(f"Admin {current_user.username} retrieved support thread {thread_id}")

        return ThreadResponse.from_thread(thread, unread_count)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving support thread {thread_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve support thread"
        )


@router.get("/threads/{thread_id}/messages", response_model=MessageListResponse)
async def get_thread_messages(
    thread_id: UUID,
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_postgres_session),
    current_user: User = Depends(get_current_admin_user)
):
    """
    Get messages in a support thread (admin view).

    Args:
        thread_id: Thread ID
        limit: Maximum number of messages to return
        offset: Number of messages to skip
        db: Database session
        current_user: Current authenticated admin

    Returns:
        List of messages in the thread
    """
    try:
        # Verify thread exists
        thread_query = select(SupportThread).where(SupportThread.id == thread_id)
        thread_result = await db.execute(thread_query)
        thread = thread_result.scalar_one_or_none()

        if not thread:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Support thread not found"
            )

        # Build messages query
        query = select(SupportMessage).where(
            SupportMessage.thread_id == thread_id
        ).options(selectinload(SupportMessage.user))

        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total_count = await db.scalar(count_query)

        # Apply pagination and ordering (oldest first for chat view)
        query = query.order_by(SupportMessage.created_at.asc()).limit(limit).offset(offset)

        # Execute query
        result = await db.execute(query)
        messages = result.scalars().all()

        logger.info(
            f"Admin {current_user.username} retrieved {len(messages)} messages for thread {thread_id} "
            f"(total: {total_count})"
        )

        return MessageListResponse(
            messages=[MessageResponse.from_message(msg) for msg in messages],
            total_count=total_count or 0
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving messages for thread {thread_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve thread messages"
        )


@router.post("/threads/{thread_id}/messages", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
async def reply_to_thread(
    thread_id: UUID,
    data: CreateMessageRequest,
    db: AsyncSession = Depends(get_postgres_session),
    current_user: User = Depends(get_current_admin_user)
):
    """
    Reply to a support thread (admin only).

    Args:
        thread_id: Thread ID
        data: Message data
        db: Database session
        current_user: Current authenticated admin

    Returns:
        Created message
    """
    try:
        # Verify thread exists
        thread_query = select(SupportThread).where(SupportThread.id == thread_id)
        thread_result = await db.execute(thread_query)
        thread = thread_result.scalar_one_or_none()

        if not thread:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Support thread not found"
            )

        # Create admin reply message
        new_message = SupportMessage(
            thread_id=thread_id,
            user_id=current_user.id,
            message=data.message,
            message_type=MessageType.admin,
            is_read=False  # User hasn't read it yet
        )
        db.add(new_message)

        # Update thread
        thread.last_message_at = func.now()
        if thread.status == MessageStatus.pending:
            thread.status = MessageStatus.answered

        # Mark all user messages in thread as read
        mark_read_stmt = (
            update(SupportMessage)
            .where(
                and_(
                    SupportMessage.thread_id == thread_id,
                    SupportMessage.message_type == MessageType.user,
                    SupportMessage.is_read == False
                )
            )
            .values(is_read=True)
        )
        await db.execute(mark_read_stmt)

        await db.flush()
        await db.refresh(new_message, ["user"])
        await db.commit()

        logger.info(f"Admin {current_user.username} replied to thread {thread_id}")

        # Broadcast to WebSocket
        message_data = {
            "thread_id": str(thread_id),
            "message_id": str(new_message.id),
            "message": new_message.message,
            "message_type": new_message.message_type.value,
            "sender_username": current_user.username,
            "is_read": new_message.is_read,
            "created_at": new_message.created_at.isoformat()
        }
        await ws_manager.broadcast_thread_message_added(message_data)

        # Notify user via public_api WebSocket (cross-container HTTP call)
        try:
            async with aiohttp.ClientSession() as http_session:
                async with http_session.post(
                    f"{PUBLIC_API_INTERNAL_URL}/internal/notify-thread-message",
                    json={"user_id": str(thread.user_id), "message_data": message_data},
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    if resp.status != 200:
                        logger.error(f"Failed to notify public_api about thread message: HTTP {resp.status}")
        except Exception as notify_error:
            logger.error(f"Error notifying public_api about thread message: {notify_error}")

        return MessageResponse.from_message(new_message, responded_by_username=current_user.username)

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error replying to thread {thread_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to reply to thread"
        )


@router.patch("/threads/{thread_id}/status", response_model=ThreadResponse)
async def update_thread_status(
    thread_id: UUID,
    data: UpdateThreadStatusRequest,
    db: AsyncSession = Depends(get_postgres_session),
    current_user: User = Depends(get_current_admin_user)
):
    """
    Update support thread status (admin only).

    Args:
        thread_id: Thread ID
        data: Status update data
        db: Database session
        current_user: Current authenticated admin

    Returns:
        Updated thread
    """
    try:
        # Validate status
        try:
            status_enum = MessageStatus(data.status)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status: {data.status}"
            )

        # Query thread
        query = select(SupportThread).where(SupportThread.id == thread_id).options(selectinload(SupportThread.user))
        result = await db.execute(query)
        thread = result.scalar_one_or_none()

        if not thread:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Support thread not found"
            )

        # Update thread status
        thread.status = status_enum

        await db.commit()

        logger.info(
            f"Admin {current_user.username} updated status of thread {thread_id} to {data.status}"
        )

        # Broadcast to WebSocket
        status_data = {
            "thread_id": str(thread_id),
            "status": thread.status.value,
            "updated_by": current_user.username,
            "updated_at": datetime.utcnow().isoformat()
        }
        await ws_manager.broadcast_thread_status_updated(status_data)

        # Notify user via public_api WebSocket (cross-container HTTP call)
        try:
            async with aiohttp.ClientSession() as http_session:
                async with http_session.post(
                    f"{PUBLIC_API_INTERNAL_URL}/internal/notify-thread-status",
                    json={"user_id": str(thread.user_id), "status_data": status_data},
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    if resp.status != 200:
                        logger.error(f"Failed to notify public_api about thread status: HTTP {resp.status}")
        except Exception as notify_error:
            logger.error(f"Error notifying public_api about thread status: {notify_error}")

        # Count unread user messages
        unread_query = select(func.count()).where(
            and_(
                SupportMessage.thread_id == thread.id,
                SupportMessage.message_type == MessageType.user,
                SupportMessage.is_read == False
            )
        )
        unread_count = await db.scalar(unread_query) or 0

        return ThreadResponse.from_thread(thread, unread_count)

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error updating thread status {thread_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update thread status"
        )


@router.patch("/threads/{thread_id}/mark-read")
async def mark_thread_messages_as_read(
    thread_id: UUID,
    db: AsyncSession = Depends(get_postgres_session),
    current_user: User = Depends(get_current_admin_user)
):
    """
    Mark all user messages in a thread as read (admin).

    Args:
        thread_id: Thread ID
        db: Database session
        current_user: Current authenticated admin

    Returns:
        Success response with updated count
    """
    try:
        # Verify thread exists
        thread_query = select(SupportThread).where(SupportThread.id == thread_id)
        thread_result = await db.execute(thread_query)
        thread = thread_result.scalar_one_or_none()

        if not thread:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Support thread not found"
            )

        # Update all unread user messages to read
        update_stmt = (
            update(SupportMessage)
            .where(
                and_(
                    SupportMessage.thread_id == thread_id,
                    SupportMessage.message_type == MessageType.user,
                    SupportMessage.is_read == False
                )
            )
            .values(is_read=True)
        )
        result = await db.execute(update_stmt)
        updated_count = result.rowcount

        await db.commit()

        logger.info(f"Admin {current_user.username} marked {updated_count} messages as read in thread {thread_id}")

        # Broadcast to WebSocket
        read_data = {
            "thread_id": str(thread_id),
            "read_count": updated_count,
            "read_by": current_user.username,
            "updated_at": datetime.utcnow().isoformat()
        }
        await ws_manager.broadcast_thread_messages_read(read_data)

        return {"success": True, "updated_count": updated_count}

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error marking messages as read in thread {thread_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to mark messages as read"
        )


# ============================================================================
# DEPRECATED ENDPOINTS (kept for backward compatibility)
# ============================================================================

class RespondToSupportMessageRequest(BaseModel):
    """DEPRECATED: Request model for responding to a support message"""
    admin_response: str = Field(..., min_length=1, max_length=2000)
    status: Optional[str] = Field(default="answered", pattern="^(answered|closed)$")


class SupportMessageResponse(BaseModel):
    """DEPRECATED: Response model for support message data"""
    id: str
    user_id: str
    username: str
    message: str
    admin_response: Optional[str] = None
    status: str
    responded_by: Optional[str] = None
    responded_by_username: Optional[str] = None
    responded_at: Optional[str] = None
    created_at: str
    updated_at: str


class SupportMessageListResponse(BaseModel):
    """DEPRECATED: Response model for list of support messages"""
    messages: List[SupportMessageResponse]
    total_count: int


@router.get("/messages", response_model=SupportMessageListResponse, deprecated=True)
async def get_support_messages(
    status_filter: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_postgres_session),
    current_user: User = Depends(get_current_admin_user)
):
    """
    DEPRECATED: Use GET /threads instead.
    Get all support messages (admin only).
    """
    return SupportMessageListResponse(messages=[], total_count=0)


@router.get("/messages/{message_id}", response_model=SupportMessageResponse, deprecated=True)
async def get_support_message_details(
    message_id: UUID,
    db: AsyncSession = Depends(get_postgres_session),
    current_user: User = Depends(get_current_admin_user)
):
    """
    DEPRECATED: Use GET /threads/{thread_id} instead.
    Get details of a specific support message (admin only).
    """
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="This endpoint is deprecated. Use GET /threads/{thread_id} instead."
    )


@router.post("/messages/{message_id}/respond", response_model=SupportMessageResponse, deprecated=True)
async def respond_to_support_message(
    message_id: UUID,
    data: RespondToSupportMessageRequest,
    db: AsyncSession = Depends(get_postgres_session),
    current_user: User = Depends(get_current_admin_user)
):
    """
    DEPRECATED: Use POST /threads/{thread_id}/messages instead.
    Respond to a support message (admin only).
    """
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="This endpoint is deprecated. Use POST /threads/{thread_id}/messages instead."
    )


@router.patch("/messages/{message_id}/status", response_model=SupportMessageResponse, deprecated=True)
async def update_support_message_status(
    message_id: UUID,
    status_value: str = Body(..., pattern="^(pending|answered|closed)$", embed=True),
    db: AsyncSession = Depends(get_postgres_session),
    current_user: User = Depends(get_current_admin_user)
):
    """
    DEPRECATED: Use PATCH /threads/{thread_id}/status instead.
    Update support message status (admin only).
    """
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="This endpoint is deprecated. Use PATCH /threads/{thread_id}/status instead."
    )
