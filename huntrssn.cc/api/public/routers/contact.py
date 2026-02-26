"""
Public Contact Router
Handles contact threads and messages (bug reports and feature requests) for regular users.
"""

import logging
from typing import List, Optional
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func, desc, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from pydantic import BaseModel, Field

from api.common.database import get_postgres_session
from api.common.models_postgres import ContactThread, ContactMessage, MessageStatus, MessageType, ContactMessageType, User
from api.public.dependencies import get_current_user
from api.public.websocket import ws_manager
from api.admin.websocket import ws_manager as admin_ws_manager

# Setup logging
logger = logging.getLogger(__name__)

# Router instance
router = APIRouter(tags=["Contact"])


# Pydantic models for thread-based API
class CreateThreadRequest(BaseModel):
    """Request model for creating a new contact thread"""
    message: str = Field(..., min_length=1, max_length=2000)
    message_type: str = Field(..., pattern="^(bug_report|feature_request)$")


class CreateMessageRequest(BaseModel):
    """Request model for adding a message to a thread"""
    message: str = Field(..., min_length=1, max_length=2000)


class MessageResponse(BaseModel):
    """Response model for individual message in thread"""
    id: str
    thread_id: str
    message: str
    message_type: str
    is_read: bool
    created_at: str
    sender_username: str

    @classmethod
    def from_message(cls, message: ContactMessage) -> "MessageResponse":
        """Convert ContactMessage model to response"""
        return cls(
            id=str(message.id),
            thread_id=str(message.thread_id),
            message=message.message,
            message_type=message.message_type.value,
            is_read=message.is_read,
            created_at=message.created_at.isoformat(),
            sender_username=message.user.username if message.user else "Unknown"
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
@router.post("/threads", response_model=ThreadResponse, status_code=status.HTTP_201_CREATED)
async def create_contact_thread(
    data: CreateThreadRequest,
    db: AsyncSession = Depends(get_postgres_session),
    current_user: User = Depends(get_current_user)
):
    """
    Create a new contact thread with an initial message.

    Args:
        data: Thread and message data
        db: Database session
        current_user: Current authenticated user

    Returns:
        Created contact thread
    """
    try:
        # Validate message type
        try:
            message_type_enum = ContactMessageType(data.message_type)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid message type: {data.message_type}"
            )

        # Create new contact thread
        new_thread = ContactThread(
            user_id=current_user.id,
            message_type=message_type_enum,
            status=MessageStatus.pending,
            last_message_at=func.now()
        )
        db.add(new_thread)
        await db.flush()

        # Create first message in thread
        first_message = ContactMessage(
            thread_id=new_thread.id,
            user_id=current_user.id,
            message=data.message,
            message_type=MessageType.user,
            is_read=False
        )
        db.add(first_message)
        await db.flush()

        # Eagerly load user relationship
        await db.refresh(new_thread, ["user"])

        await db.commit()

        logger.info(f"Created contact thread {new_thread.id} ({data.message_type}) for user {current_user.id}")

        # Broadcast to WebSocket
        thread_data = {
            "id": str(new_thread.id),
            "user_id": str(new_thread.user_id),
            "username": current_user.username,
            "message_type": new_thread.message_type.value,
            "status": new_thread.status.value,
            "created_at": new_thread.created_at.isoformat()
        }
        await ws_manager.notify_contact_thread_created(str(current_user.id), thread_data)
        await admin_ws_manager.broadcast_contact_thread_created(thread_data)

        return ThreadResponse.from_thread(new_thread, unread_count=0)

    except HTTPException:
        raise
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error creating contact thread: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create contact thread"
        )


@router.get("/threads", response_model=ThreadListResponse)
async def get_contact_threads(
    status_filter: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_postgres_session),
    current_user: User = Depends(get_current_user)
):
    """
    Get contact threads for the current user.

    Args:
        status_filter: Optional filter by status ('pending', 'answered', 'closed')
        limit: Maximum number of threads to return
        offset: Number of threads to skip
        db: Database session
        current_user: Current authenticated user

    Returns:
        List of contact threads
    """
    try:
        # Build query
        query = select(ContactThread).where(
            ContactThread.user_id == current_user.id
        ).options(selectinload(ContactThread.user))

        # Apply status filter if provided
        if status_filter:
            try:
                status_enum = MessageStatus(status_filter)
                query = query.where(ContactThread.status == status_enum)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid status filter: {status_filter}"
                )

        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total_count = await db.scalar(count_query)

        # Apply pagination and ordering
        query = query.order_by(desc(ContactThread.last_message_at)).limit(limit).offset(offset)

        # Execute query
        result = await db.execute(query)
        threads = result.scalars().all()

        # Optimize: Get unread counts for all threads in one query
        thread_ids = [thread.id for thread in threads]
        unread_counts = {}
        if thread_ids:
            unread_query = (
                select(
                    ContactMessage.thread_id,
                    func.count().label('unread_count')
                )
                .where(
                    and_(
                        ContactMessage.thread_id.in_(thread_ids),
                        ContactMessage.message_type == MessageType.admin,
                        ContactMessage.is_read == False
                    )
                )
                .group_by(ContactMessage.thread_id)
            )
            unread_result = await db.execute(unread_query)
            unread_counts = {row.thread_id: row.unread_count for row in unread_result}

        # Optimize: Get last message for each thread in one query using window function
        last_messages = {}
        if thread_ids:
            # Subquery to get the latest message per thread
            latest_msg_subq = (
                select(
                    ContactMessage.thread_id,
                    ContactMessage.message,
                    func.row_number().over(
                        partition_by=ContactMessage.thread_id,
                        order_by=desc(ContactMessage.created_at)
                    ).label('rn')
                )
                .where(ContactMessage.thread_id.in_(thread_ids))
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
            f"Retrieved {len(threads)} contact threads for user {current_user.id} "
            f"(total: {total_count}, filter: {status_filter})"
        )

        return ThreadListResponse(
            threads=thread_responses,
            total_count=total_count or 0
        )

    except HTTPException:
        raise
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving contact threads: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve contact threads"
        )


@router.get("/threads/{thread_id}", response_model=ThreadResponse)
async def get_contact_thread_details(
    thread_id: UUID,
    db: AsyncSession = Depends(get_postgres_session),
    current_user: User = Depends(get_current_user)
):
    """
    Get details of a specific contact thread.

    Args:
        thread_id: Thread ID
        db: Database session
        current_user: Current authenticated user

    Returns:
        Contact thread details
    """
    try:
        # Query thread with user relationship
        query = select(ContactThread).where(
            ContactThread.id == thread_id
        ).options(selectinload(ContactThread.user))

        result = await db.execute(query)
        thread = result.scalar_one_or_none()

        if not thread:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Contact thread not found"
            )

        # Check ownership
        if thread.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to view this thread"
            )

        # Count unread admin messages
        unread_query = select(func.count()).where(
            and_(
                ContactMessage.thread_id == thread.id,
                ContactMessage.message_type == MessageType.admin,
                ContactMessage.is_read == False
            )
        )
        unread_count = await db.scalar(unread_query) or 0

        logger.info(f"Retrieved contact thread {thread_id} for user {current_user.id}")

        return ThreadResponse.from_thread(thread, unread_count)

    except HTTPException:
        raise
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving contact thread {thread_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve contact thread"
        )


@router.get("/threads/{thread_id}/messages", response_model=MessageListResponse)
async def get_thread_messages(
    thread_id: UUID,
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_postgres_session),
    current_user: User = Depends(get_current_user)
):
    """
    Get messages in a contact thread.

    Args:
        thread_id: Thread ID
        limit: Maximum number of messages to return
        offset: Number of messages to skip
        db: Database session
        current_user: Current authenticated user

    Returns:
        List of messages in the thread
    """
    try:
        # Verify thread ownership
        thread_query = select(ContactThread).where(ContactThread.id == thread_id)
        thread_result = await db.execute(thread_query)
        thread = thread_result.scalar_one_or_none()

        if not thread:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Contact thread not found"
            )

        if thread.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to view this thread"
            )

        # Build messages query
        query = select(ContactMessage).where(
            ContactMessage.thread_id == thread_id
        ).options(selectinload(ContactMessage.user))

        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total_count = await db.scalar(count_query)

        # Apply pagination and ordering (oldest first for chat view)
        query = query.order_by(ContactMessage.created_at.asc()).limit(limit).offset(offset)

        # Execute query
        result = await db.execute(query)
        messages = result.scalars().all()

        logger.info(
            f"Retrieved {len(messages)} messages for contact thread {thread_id} "
            f"(total: {total_count})"
        )

        return MessageListResponse(
            messages=[MessageResponse.from_message(msg) for msg in messages],
            total_count=total_count or 0
        )

    except HTTPException:
        raise
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving messages for contact thread {thread_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve thread messages"
        )


@router.post("/threads/{thread_id}/messages", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
async def add_thread_message(
    thread_id: UUID,
    data: CreateMessageRequest,
    db: AsyncSession = Depends(get_postgres_session),
    current_user: User = Depends(get_current_user)
):
    """
    Add a message to a contact thread.

    Args:
        thread_id: Thread ID
        data: Message data
        db: Database session
        current_user: Current authenticated user

    Returns:
        Created message
    """
    try:
        # Verify thread ownership and status
        thread_query = select(ContactThread).where(ContactThread.id == thread_id)
        thread_result = await db.execute(thread_query)
        thread = thread_result.scalar_one_or_none()

        if not thread:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Contact thread not found"
            )

        if thread.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to add messages to this thread"
            )

        if thread.status == MessageStatus.closed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot add messages to a closed thread"
            )

        # Create new message
        new_message = ContactMessage(
            thread_id=thread_id,
            user_id=current_user.id,
            message=data.message,
            message_type=MessageType.user,
            is_read=False
        )
        db.add(new_message)

        # Update thread last_message_at
        thread.last_message_at = func.now()

        await db.flush()
        await db.refresh(new_message, ["user"])
        await db.commit()

        logger.info(f"Added message to contact thread {thread_id} by user {current_user.id}")

        # Broadcast to WebSocket
        message_data = {
            "thread_id": str(thread_id),
            "message_id": str(new_message.id),
            "message": new_message.message,
            "message_type": new_message.message_type.value,
            "sender_username": current_user.username,
            "created_at": new_message.created_at.isoformat()
        }
        await ws_manager.notify_contact_thread_message_added(str(current_user.id), message_data)
        await admin_ws_manager.broadcast_contact_thread_message_added(message_data)

        return MessageResponse.from_message(new_message)

    except HTTPException:
        raise
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error adding message to contact thread {thread_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to add message to thread"
        )


@router.patch("/threads/{thread_id}/mark-read")
async def mark_thread_messages_as_read(
    thread_id: UUID,
    db: AsyncSession = Depends(get_postgres_session),
    current_user: User = Depends(get_current_user)
):
    """
    Mark all admin messages in a thread as read.

    Args:
        thread_id: Thread ID
        db: Database session
        current_user: Current authenticated user

    Returns:
        Success response with updated count
    """
    try:
        # Verify thread ownership
        thread_query = select(ContactThread).where(ContactThread.id == thread_id)
        thread_result = await db.execute(thread_query)
        thread = thread_result.scalar_one_or_none()

        if not thread:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Contact thread not found"
            )

        if thread.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to modify this thread"
            )

        # Update all unread admin messages to read
        from sqlalchemy import update
        update_stmt = (
            update(ContactMessage)
            .where(
                and_(
                    ContactMessage.thread_id == thread_id,
                    ContactMessage.message_type == MessageType.admin,
                    ContactMessage.is_read == False
                )
            )
            .values(is_read=True)
        )
        result = await db.execute(update_stmt)
        updated_count = result.rowcount

        await db.commit()

        logger.info(f"Marked {updated_count} messages as read in contact thread {thread_id}")

        # Broadcast to WebSocket
        read_data = {
            "thread_id": str(thread_id),
            "read_count": updated_count,
            "updated_at": datetime.utcnow().isoformat()
        }
        await ws_manager.notify_contact_thread_messages_read(str(current_user.id), read_data)

        return {"success": True, "updated_count": updated_count}

    except HTTPException:
        raise
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error marking messages as read in contact thread {thread_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to mark messages as read"
        )


# ============================================================================
# DEPRECATED ENDPOINTS (kept for backward compatibility)
# ============================================================================

class CreateContactMessageRequest(BaseModel):
    """DEPRECATED: Request model for creating a contact message"""
    message_type: str = Field(..., pattern="^(bug_report|feature_request)$")
    message: str = Field(..., min_length=1, max_length=2000)


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


@router.post("/messages", response_model=ContactMessageResponse, status_code=status.HTTP_201_CREATED, deprecated=True)
async def create_contact_message(
    data: CreateContactMessageRequest,
    db: AsyncSession = Depends(get_postgres_session),
    current_user: User = Depends(get_current_user)
):
    """
    DEPRECATED: Use POST /threads instead.
    Create a new contact message (creates a thread automatically).
    """
    # Redirect to new thread-based API
    thread_data = CreateThreadRequest(message=data.message, message_type=data.message_type)
    thread = await create_contact_thread(thread_data, db, current_user)

    # Return in old format for compatibility
    return ContactMessageResponse(
        id=thread.id,
        user_id=thread.user_id,
        username=thread.username,
        message_type=thread.message_type,
        message=data.message,
        admin_response=None,
        status=thread.status,
        responded_by=None,
        responded_at=None,
        created_at=thread.created_at,
        updated_at=thread.updated_at
    )


@router.get("/messages", response_model=ContactMessageListResponse, deprecated=True)
async def get_contact_messages(
    message_type_filter: Optional[str] = None,
    status_filter: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_postgres_session),
    current_user: User = Depends(get_current_user)
):
    """
    DEPRECATED: Use GET /threads instead.
    Get contact messages for the current user.
    """
    # Return empty list with deprecation notice
    return ContactMessageListResponse(messages=[], total_count=0)


@router.get("/messages/{message_id}", response_model=ContactMessageResponse, deprecated=True)
async def get_contact_message_details(
    message_id: UUID,
    db: AsyncSession = Depends(get_postgres_session),
    current_user: User = Depends(get_current_user)
):
    """
    DEPRECATED: Use GET /threads/{thread_id} instead.
    Get details of a specific contact message.
    """
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="This endpoint is deprecated. Use GET /threads/{thread_id} instead."
    )
