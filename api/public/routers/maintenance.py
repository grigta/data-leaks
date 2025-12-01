"""
Public maintenance mode check endpoint.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional

from api.common.database import get_postgres_session
from api.common.pricing import check_maintenance_mode


router = APIRouter()


class MaintenanceStatusResponse(BaseModel):
    """Response model for maintenance status."""
    is_active: bool
    message: Optional[str] = None
    service_name: str


@router.get("/{service_name}", response_model=MaintenanceStatusResponse)
async def get_maintenance_status(
    service_name: str,
    db: AsyncSession = Depends(get_postgres_session)
):
    """
    Get maintenance mode status for a specific service.
    Public endpoint - no authentication required.

    Args:
        service_name: Service identifier ('instant_ssn', 'manual_ssn', etc.)

    Returns:
        MaintenanceStatusResponse with is_active status and optional message
    """
    is_active, message = await check_maintenance_mode(db, service_name)

    return MaintenanceStatusResponse(
        is_active=is_active,
        message=message,
        service_name=service_name
    )
