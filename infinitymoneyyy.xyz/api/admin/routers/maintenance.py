"""
Admin router for maintenance mode management.
Provides CRUD operations for service maintenance modes.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel, Field, field_validator
from typing import List, Optional
import logging

from api.common.database import get_postgres_session
from api.common.models_postgres import MaintenanceMode
from api.admin.dependencies import get_current_admin_user

logger = logging.getLogger(__name__)
router = APIRouter()

# Allowed service names
ALLOWED_SERVICES = ['instant_ssn', 'manual_ssn']


# Pydantic models
class MaintenanceModeResponse(BaseModel):
    """Response model for maintenance mode data."""
    id: str
    service_name: str
    is_active: bool
    message: Optional[str]
    created_at: str
    updated_at: str

    @classmethod
    def from_maintenance_mode(cls, mode: MaintenanceMode):
        """Create response from MaintenanceMode model."""
        return cls(
            id=str(mode.id),
            service_name=mode.service_name,
            is_active=mode.is_active,
            message=mode.message,
            created_at=mode.created_at.isoformat(),
            updated_at=mode.updated_at.isoformat()
        )


class CreateMaintenanceModeRequest(BaseModel):
    """Request model for creating a new maintenance mode entry."""
    service_name: str = Field(description="Service identifier (instant_ssn, manual_ssn)")
    is_active: bool = Field(default=False, description="Whether maintenance mode is active")
    message: Optional[str] = Field(default=None, description="Custom message to display to users")

    @field_validator('service_name')
    @classmethod
    def validate_service_name(cls, v):
        if v not in ALLOWED_SERVICES:
            raise ValueError(f"Service name must be one of: {', '.join(ALLOWED_SERVICES)}")
        return v


class UpdateMaintenanceModeRequest(BaseModel):
    """Request model for updating an existing maintenance mode."""
    is_active: Optional[bool] = Field(default=None)
    message: Optional[str] = Field(default=None)


class MaintenanceModeListResponse(BaseModel):
    """Response model for listing maintenance modes."""
    maintenance_modes: List[MaintenanceModeResponse]
    total_count: int


@router.post("/", response_model=MaintenanceModeResponse, status_code=status.HTTP_201_CREATED)
async def create_maintenance_mode(
    request: CreateMaintenanceModeRequest,
    db: AsyncSession = Depends(get_postgres_session),
    admin_user = Depends(get_current_admin_user)
):
    """
    Create a new maintenance mode entry.

    Admin only. Service name must be unique.
    """
    try:
        # Check if service already exists
        result = await db.execute(
            select(MaintenanceMode).where(MaintenanceMode.service_name == request.service_name)
        )
        existing = result.scalar_one_or_none()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Maintenance mode for service '{request.service_name}' already exists"
            )

        # Create maintenance mode
        new_mode = MaintenanceMode(
            service_name=request.service_name,
            is_active=request.is_active,
            message=request.message
        )

        db.add(new_mode)
        await db.commit()
        await db.refresh(new_mode)

        logger.info(f"Admin {admin_user.username} created maintenance mode for {request.service_name}")
        return MaintenanceModeResponse.from_maintenance_mode(new_mode)

    except HTTPException:
        raise
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error creating maintenance mode: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create maintenance mode"
        )


@router.get("/", response_model=MaintenanceModeListResponse)
async def list_maintenance_modes(
    is_active: Optional[bool] = None,
    db: AsyncSession = Depends(get_postgres_session),
    admin_user = Depends(get_current_admin_user)
):
    """
    List all maintenance modes with optional filtering.

    Admin only. Can filter by active status.
    """
    try:
        # Build query
        query = select(MaintenanceMode)

        # Apply filter
        if is_active is not None:
            query = query.where(MaintenanceMode.is_active == is_active)

        # Order by service name
        query = query.order_by(MaintenanceMode.service_name)

        # Execute query
        result = await db.execute(query)
        modes = result.scalars().all()

        # Get total count
        count_query = select(func.count(MaintenanceMode.id))
        if is_active is not None:
            count_query = count_query.where(MaintenanceMode.is_active == is_active)

        count_result = await db.execute(count_query)
        total_count = count_result.scalar_one()

        return MaintenanceModeListResponse(
            maintenance_modes=[MaintenanceModeResponse.from_maintenance_mode(m) for m in modes],
            total_count=total_count
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing maintenance modes: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list maintenance modes"
        )


@router.get("/{service_name}", response_model=MaintenanceModeResponse)
async def get_maintenance_mode(
    service_name: str,
    db: AsyncSession = Depends(get_postgres_session),
    admin_user = Depends(get_current_admin_user)
):
    """
    Get a specific maintenance mode by service name.

    Admin only.
    """
    # Validate service_name
    if service_name not in ALLOWED_SERVICES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid service name. Must be one of: {', '.join(ALLOWED_SERVICES)}"
        )

    try:
        result = await db.execute(
            select(MaintenanceMode).where(MaintenanceMode.service_name == service_name)
        )
        mode = result.scalar_one_or_none()

        if not mode:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Maintenance mode not found"
            )

        return MaintenanceModeResponse.from_maintenance_mode(mode)

    except HTTPException:
        raise
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting maintenance mode {service_name}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get maintenance mode"
        )


@router.patch("/{service_name}", response_model=MaintenanceModeResponse)
async def update_maintenance_mode(
    service_name: str,
    request: UpdateMaintenanceModeRequest,
    db: AsyncSession = Depends(get_postgres_session),
    admin_user = Depends(get_current_admin_user)
):
    """
    Update an existing maintenance mode.

    Admin only. Can update is_active and/or message.
    """
    # Validate service_name
    if service_name not in ALLOWED_SERVICES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid service name. Must be one of: {', '.join(ALLOWED_SERVICES)}"
        )

    try:
        # Get maintenance mode
        result = await db.execute(
            select(MaintenanceMode).where(MaintenanceMode.service_name == service_name)
        )
        mode = result.scalar_one_or_none()

        if not mode:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Maintenance mode not found"
            )

        # Update fields
        if request.is_active is not None:
            mode.is_active = request.is_active

        if request.message is not None:
            mode.message = request.message

        await db.commit()
        await db.refresh(mode)

        logger.info(f"Admin {admin_user.username} updated maintenance mode for {service_name}")
        return MaintenanceModeResponse.from_maintenance_mode(mode)

    except HTTPException:
        raise
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error updating maintenance mode {service_name}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update maintenance mode"
        )


@router.delete("/{service_name}")
async def delete_maintenance_mode(
    service_name: str,
    db: AsyncSession = Depends(get_postgres_session),
    admin_user = Depends(get_current_admin_user)
):
    """
    Delete a maintenance mode.

    Admin only.
    """
    # Validate service_name
    if service_name not in ALLOWED_SERVICES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid service name. Must be one of: {', '.join(ALLOWED_SERVICES)}"
        )

    try:
        # Get maintenance mode
        result = await db.execute(
            select(MaintenanceMode).where(MaintenanceMode.service_name == service_name)
        )
        mode = result.scalar_one_or_none()

        if not mode:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Maintenance mode not found"
            )

        # Delete maintenance mode
        await db.delete(mode)
        await db.commit()

        logger.info(f"Admin {admin_user.username} deleted maintenance mode for {service_name}")
        return {"message": "Maintenance mode deleted successfully"}

    except HTTPException:
        raise
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error deleting maintenance mode {service_name}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete maintenance mode"
        )


@router.post("/{service_name}/toggle", response_model=MaintenanceModeResponse)
async def toggle_maintenance_mode(
    service_name: str,
    db: AsyncSession = Depends(get_postgres_session),
    admin_user = Depends(get_current_admin_user)
):
    """
    Toggle maintenance mode on/off.

    Admin only. Quick endpoint to toggle is_active status.
    """
    # Validate service_name
    if service_name not in ALLOWED_SERVICES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid service name. Must be one of: {', '.join(ALLOWED_SERVICES)}"
        )

    try:
        # Get maintenance mode
        result = await db.execute(
            select(MaintenanceMode).where(MaintenanceMode.service_name == service_name)
        )
        mode = result.scalar_one_or_none()

        if not mode:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Maintenance mode not found"
            )

        # Toggle is_active
        mode.is_active = not mode.is_active
        await db.commit()
        await db.refresh(mode)

        logger.info(f"Admin {admin_user.username} toggled maintenance mode for {service_name} to {mode.is_active}")
        return MaintenanceModeResponse.from_maintenance_mode(mode)

    except HTTPException:
        raise
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error toggling maintenance mode {service_name}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to toggle maintenance mode"
        )
