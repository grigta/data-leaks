"""
User Ban Management Router for Admin API
Handles listing banned users and unbanning functionality
"""

from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel, Field
from typing import List, Literal, Optional
from uuid import UUID
from datetime import datetime
import logging

from api.admin.dependencies import get_current_admin_user
from api.common.database import get_postgres_session
from api.common.models_postgres import User
from api.admin.websocket import ws_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["User Management"])


# Pydantic Models
class BannedUserResponse(BaseModel):
    id: str
    username: str
    ban_reason: str
    banned_at: str
    created_at: str


class BannedUsersListResponse(BaseModel):
    users: List[BannedUserResponse]
    total_count: int


class UnbanUserResponse(BaseModel):
    message: str
    user_id: str
    username: str


class BanUserRequest(BaseModel):
    reason: str = Field(..., min_length=3, max_length=500, description="Причина бана пользователя")


class BanUserResponse(BaseModel):
    message: str
    user_id: str
    username: str
    ban_reason: str
    banned_at: str


@router.get("/banned", response_model=BannedUsersListResponse)
async def get_banned_users(
    limit: int = 50,
    offset: int = 0,
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_postgres_session),
    current_admin: User = Depends(get_current_admin_user)
):
    """
    Get list of banned users with pagination and optional search
    Requires admin authentication
    """
    try:
        # Build query for banned users
        query = select(User).where(User.is_banned == True)

        # Apply search filter if provided
        if search:
            query = query.where(User.username.ilike(f"%{search}%"))

        # Order by most recent bans first
        query = query.order_by(User.banned_at.desc())

        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total_count_result = await db.execute(count_query)
        total_count = total_count_result.scalar() or 0

        # Apply pagination
        query = query.limit(limit).offset(offset)

        # Execute query
        result = await db.execute(query)
        users = result.scalars().all()

        # Convert to response models
        banned_users = [
            BannedUserResponse(
                id=str(user.id),
                username=user.username,
                ban_reason=user.ban_reason or "",
                banned_at=user.banned_at.isoformat() if user.banned_at else "",
                created_at=user.created_at.isoformat() if user.created_at else ""
            )
            for user in users
        ]

        logger.info(f"Admin {current_admin.username} listed banned users (total: {total_count}, returned: {len(banned_users)})")

        return BannedUsersListResponse(
            users=banned_users,
            total_count=total_count
        )

    except Exception as e:
        logger.error(f"Error listing banned users: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve banned users: {str(e)}"
        )


@router.patch("/{user_id}/unban", response_model=UnbanUserResponse)
async def unban_user(
    user_id: UUID,
    db: AsyncSession = Depends(get_postgres_session),
    current_admin: User = Depends(get_current_admin_user)
):
    """
    Unban a user by setting is_banned to False and clearing ban fields
    Requires admin authentication
    """
    try:
        # Query user by ID
        query = select(User).where(User.id == user_id)
        result = await db.execute(query)
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with ID {user_id} not found"
            )

        # Check if user is actually banned
        if not user.is_banned:
            logger.warning(f"Admin {current_admin.username} attempted to unban user {user.username} who is not banned")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"User {user.username} is not currently banned"
            )

        # Unban the user
        user.is_banned = False
        user.ban_reason = None
        user.banned_at = None

        await db.commit()

        # Broadcast WebSocket event
        unbanned_at = datetime.utcnow().isoformat()
        await ws_manager.broadcast_to_admins("user_unbanned", {
            "user_id": str(user.id),
            "username": user.username,
            "unbanned_by": current_admin.username,
            "unbanned_at": unbanned_at
        })

        logger.info(f"Admin {current_admin.username} unbanned user {user.username} (ID: {user.id})")

        return UnbanUserResponse(
            message=f"User {user.username} has been unbanned successfully",
            user_id=str(user.id),
            username=user.username
        )

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error unbanning user {user_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to unban user: {str(e)}"
        )


@router.post("/{user_id}/ban", response_model=BanUserResponse)
async def ban_user(
    user_id: UUID,
    ban_request: BanUserRequest,
    db: AsyncSession = Depends(get_postgres_session),
    current_admin: User = Depends(get_current_admin_user)
):
    """
    Ban a user by setting is_banned to True and recording ban details
    Requires admin authentication
    """
    try:
        # Query user by ID
        query = select(User).where(User.id == user_id)
        result = await db.execute(query)
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with ID {user_id} not found"
            )

        # Check if user is already banned
        if user.is_banned:
            logger.warning(f"Admin {current_admin.username} attempted to ban user {user.username} who is already banned")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"User {user.username} is already banned"
            )

        # Ban the user
        ban_time = datetime.utcnow()
        user.is_banned = True
        user.ban_reason = ban_request.reason
        user.banned_at = ban_time

        await db.commit()

        # Broadcast WebSocket event
        await ws_manager.broadcast_to_admins("user_banned", {
            "user_id": str(user.id),
            "username": user.username,
            "ban_reason": ban_request.reason,
            "banned_by": current_admin.username,
            "banned_at": ban_time.isoformat()
        })

        logger.info(f"Admin {current_admin.username} banned user {user.username} (ID: {user.id}), reason: {ban_request.reason}")

        return BanUserResponse(
            message=f"User {user.username} has been banned successfully",
            user_id=str(user.id),
            username=user.username,
            ban_reason=ban_request.reason,
            banned_at=ban_time.isoformat()
        )

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error banning user {user_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to ban user: {str(e)}"
        )


# ============================================
# User Actions
# ============================================


class AddBalanceRequest(BaseModel):
    amount: Decimal = Field(..., gt=0, le=100000, description="Amount to add to user balance")


class AddBalanceResponse(BaseModel):
    message: str
    user_id: str
    username: str
    new_balance: float


class SetSearchModeRequest(BaseModel):
    search_mode: Literal["auto", "instant", "manual"] = Field(..., description="Search mode to set")


class SetSearchModeResponse(BaseModel):
    message: str
    user_id: str
    username: str
    search_mode: str


@router.post("/{user_id}/add-balance", response_model=AddBalanceResponse)
async def add_user_balance(
    user_id: UUID,
    request: AddBalanceRequest,
    db: AsyncSession = Depends(get_postgres_session),
    current_admin: User = Depends(get_current_admin_user),
):
    """
    Add balance to a user's account.
    Does NOT create a transaction record.
    """
    try:
        query = select(User).where(User.id == user_id)
        result = await db.execute(query)
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with ID {user_id} not found",
            )

        user.balance = user.balance + request.amount
        await db.commit()
        await db.refresh(user)

        logger.info(
            f"Admin {current_admin.username} added ${request.amount} to user {user.username} "
            f"(ID: {user.id}), new balance: ${user.balance}"
        )

        return AddBalanceResponse(
            message=f"Added ${request.amount} to {user.username}'s balance",
            user_id=str(user.id),
            username=user.username,
            new_balance=float(user.balance),
        )

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error adding balance to user {user_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to add balance: {str(e)}",
        )


@router.patch("/{user_id}/search-mode", response_model=SetSearchModeResponse)
async def set_user_search_mode(
    user_id: UUID,
    request: SetSearchModeRequest,
    db: AsyncSession = Depends(get_postgres_session),
    current_admin: User = Depends(get_current_admin_user),
):
    """
    Set search mode for a user (auto/instant/manual).
    """
    try:
        query = select(User).where(User.id == user_id)
        result = await db.execute(query)
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with ID {user_id} not found",
            )

        user.search_mode = request.search_mode
        await db.commit()

        logger.info(
            f"Admin {current_admin.username} set search_mode={request.search_mode} "
            f"for user {user.username} (ID: {user.id})"
        )

        return SetSearchModeResponse(
            message=f"Search mode for {user.username} set to {request.search_mode}",
            user_id=str(user.id),
            username=user.username,
            search_mode=request.search_mode,
        )

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error setting search mode for user {user_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to set search mode: {str(e)}",
        )
