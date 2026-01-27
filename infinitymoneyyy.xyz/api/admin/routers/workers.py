"""
Worker registration management endpoints.
"""
import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional, List
from uuid import UUID
from decimal import Decimal
from sqlalchemy.exc import IntegrityError

from api.common.database import get_postgres_session as get_db
from api.common.models_postgres import User, WorkerRegistrationRequest, RegistrationStatus
from api.admin.dependencies import get_current_admin_user
from api.admin.websocket import ws_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/worker-requests", tags=["Worker Requests"])


class WorkerRequestResponse(BaseModel):
    """Response model for displaying registration requests."""
    id: str
    username: str
    email: str
    access_code: str
    status: str
    created_at: str

    @classmethod
    def from_request(cls, request: WorkerRegistrationRequest):
        """Convert WorkerRegistrationRequest model to response."""
        return cls(
            id=str(request.id),
            username=request.username,
            email=request.email,
            access_code=request.access_code,
            status=request.status.value,
            created_at=request.created_at.isoformat()
        )


class WorkerRequestListResponse(BaseModel):
    """Response model for listing worker registration requests."""
    requests: List[WorkerRequestResponse]
    total_count: int


class ApproveWorkerResponse(BaseModel):
    """Response model for worker approval."""
    message: str
    user_id: str
    username: str
    access_code: str


class RejectWorkerResponse(BaseModel):
    """Response model for worker rejection."""
    message: str
    username: str


@router.get("", response_model=WorkerRequestListResponse)
async def list_worker_requests(
    status_filter: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    admin_user = Depends(get_current_admin_user)
):
    """
    List worker registration requests (admin only).

    Supports filtering by status and pagination.

    Args:
        status_filter: Optional status filter (pending, approved, rejected)
        limit: Maximum number of results (default 50)
        offset: Offset for pagination (default 0)

    Returns:
        List of worker registration requests and total count
    """
    try:
        # Build query
        query = select(WorkerRegistrationRequest)

        # Apply status filter if provided
        if status_filter:
            # Validate status value
            try:
                status_enum = RegistrationStatus(status_filter)
                query = query.where(WorkerRegistrationRequest.status == status_enum)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid status: {status_filter}. Must be one of: pending, approved, rejected"
                )

        # Order by created_at desc (most recent first) and paginate
        query = query.order_by(WorkerRegistrationRequest.created_at.desc()).offset(offset).limit(limit)

        # Execute query
        result = await db.execute(query)
        requests = result.scalars().all()

        # Get total count with same filters
        from sqlalchemy import func
        count_query = select(func.count(WorkerRegistrationRequest.id))
        if status_filter:
            try:
                status_enum = RegistrationStatus(status_filter)
                count_query = count_query.where(WorkerRegistrationRequest.status == status_enum)
            except ValueError:
                pass

        count_result = await db.execute(count_query)
        total_count = count_result.scalar_one()

        logger.info(f"Admin {admin_user.username} listed worker requests")

        return WorkerRequestListResponse(
            requests=[WorkerRequestResponse.from_request(r) for r in requests],
            total_count=total_count
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing worker requests: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list worker requests"
        )


@router.post("/{request_id}/approve", response_model=ApproveWorkerResponse)
async def approve_worker_request(
    request_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin_user = Depends(get_current_admin_user)
):
    """
    Approve a worker registration request (admin only).

    Creates a new User with worker_role=True and is_admin=True.
    The worker can authenticate but is restricted to worker-only endpoints.

    Args:
        request_id: UUID of the registration request

    Returns:
        Success message with user details
    """
    try:
        # Get registration request
        result = await db.execute(
            select(WorkerRegistrationRequest).where(WorkerRegistrationRequest.id == request_id)
        )
        registration_request = result.scalar_one_or_none()

        if not registration_request:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Worker registration request not found"
            )

        # Check if already approved/rejected
        if registration_request.status != RegistrationStatus.pending:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Request already {registration_request.status.value}"
            )

        # Race condition protection: check if username or email already exists
        from sqlalchemy import func
        username_check = await db.execute(
            select(User).where(func.lower(User.username) == registration_request.username.lower())
        )
        if username_check.scalar_one_or_none():
            # Update request status to rejected
            registration_request.status = RegistrationStatus.rejected
            await db.commit()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already exists"
            )

        email_check = await db.execute(
            select(User).where(func.lower(User.email) == registration_request.email.lower())
        )
        if email_check.scalar_one_or_none():
            # Update request status to rejected
            registration_request.status = RegistrationStatus.rejected
            await db.commit()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already exists"
            )

        # Create new User with worker role
        new_user = User(
            username=registration_request.username,
            email=registration_request.email,
            hashed_password=registration_request.hashed_password,
            access_code=registration_request.access_code,
            is_admin=False,  # Worker, not admin
            worker_role=True,  # Worker role enabled
            balance=Decimal('0.00')
        )

        # Update registration request status
        registration_request.status = RegistrationStatus.approved

        # Add user to database and commit both changes
        db.add(new_user)

        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            registration_request.status = RegistrationStatus.rejected
            await db.commit()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username or email already exists"
            )

        await db.refresh(new_user)
        await db.refresh(registration_request)

        # Broadcast worker request approval via WebSocket
        try:
            request_data = {
                "request_id": str(request_id),
                "username": new_user.username,
                "email": new_user.email,
                "access_code": new_user.access_code,
                "user_id": str(new_user.id),
                "approved_by": admin_user.username,
                "approved_at": datetime.utcnow().isoformat(),
                "status": "approved"
            }
            await ws_manager.broadcast_worker_request_approved(request_data, str(new_user.id))
        except Exception as e:
            logger.warning(f"Failed to broadcast worker approval: {e}")

        logger.info(f"Admin {admin_user.username} approved worker registration for {new_user.username} (ID: {new_user.id})")

        return ApproveWorkerResponse(
            message="Worker registration approved successfully",
            user_id=str(new_user.id),
            username=new_user.username,
            access_code=new_user.access_code
        )

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error approving worker request {request_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to approve worker request"
        )


@router.post("/{request_id}/reject", response_model=RejectWorkerResponse)
async def reject_worker_request(
    request_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin_user = Depends(get_current_admin_user)
):
    """
    Reject a worker registration request (admin only).

    Updates the request status to rejected.

    Args:
        request_id: UUID of the registration request

    Returns:
        Success message
    """
    try:
        # Get registration request
        result = await db.execute(
            select(WorkerRegistrationRequest).where(WorkerRegistrationRequest.id == request_id)
        )
        registration_request = result.scalar_one_or_none()

        if not registration_request:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Worker registration request not found"
            )

        # Check if already approved/rejected
        if registration_request.status != RegistrationStatus.pending:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Request already {registration_request.status.value}"
            )

        # Update status to rejected
        registration_request.status = RegistrationStatus.rejected
        await db.commit()
        await db.refresh(registration_request)

        # Broadcast worker request rejection via WebSocket
        try:
            request_data = {
                "request_id": str(request_id),
                "username": registration_request.username,
                "email": registration_request.email,
                "rejected_by": admin_user.username,
                "rejected_at": datetime.utcnow().isoformat(),
                "status": "rejected"
            }
            await ws_manager.broadcast_to_admins("worker_request_rejected", request_data)
        except Exception as e:
            logger.warning(f"Failed to broadcast worker rejection: {e}")

        logger.info(f"Admin {admin_user.username} rejected worker registration for {registration_request.username}")

        return RejectWorkerResponse(
            message="Worker registration request rejected",
            username=registration_request.username
        )

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error rejecting worker request {request_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to reject worker request"
        )
