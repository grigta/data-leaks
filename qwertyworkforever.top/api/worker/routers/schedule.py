"""
Worker schedule management endpoints.
Allows workers to set their working hours and pause status.
"""
import os
import logging
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, field_validator
import httpx

from api.common.database import get_postgres_session as get_db
from api.common.models_postgres import User
from api.worker.dependencies import get_current_worker_user

ADMIN_API_URL = os.getenv("ADMIN_API_URL", "http://admin_api:8002")

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Schedule"])


# --- Pydantic models ---

class DaySchedule(BaseModel):
    day: str
    active: bool
    start: str
    end: str

    @field_validator('day')
    @classmethod
    def validate_day(cls, v):
        if v not in ('mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'):
            raise ValueError('Invalid day. Must be mon/tue/wed/thu/fri/sat/sun')
        return v

    @field_validator('start', 'end')
    @classmethod
    def validate_time(cls, v):
        parts = v.split(':')
        if len(parts) != 2:
            raise ValueError('Time must be HH:MM')
        try:
            h, m = int(parts[0]), int(parts[1])
        except ValueError:
            raise ValueError('Time must be HH:MM with numeric values')
        if not (0 <= h <= 23 and 0 <= m <= 59):
            raise ValueError('Invalid time range')
        return v


class ScheduleResponse(BaseModel):
    worker_paused: bool
    worker_schedule: Optional[List[DaySchedule]] = None
    worker_timezone: Optional[str] = None


class UpdateScheduleRequest(BaseModel):
    schedule: List[DaySchedule]
    timezone: Optional[str] = None

    @field_validator('schedule')
    @classmethod
    def validate_schedule(cls, v):
        if len(v) != 7:
            raise ValueError('Schedule must contain exactly 7 days')
        days = {d.day for d in v}
        expected = {'mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'}
        if days != expected:
            raise ValueError('Schedule must contain all 7 days of the week')
        return v


class UpdatePauseRequest(BaseModel):
    paused: bool


# --- Helper ---

def _build_schedule_data(user: User) -> dict:
    return {
        "worker_id": str(user.id),
        "worker_username": user.username,
        "worker_paused": user.worker_paused,
        "worker_schedule": user.worker_schedule,
        "worker_timezone": user.worker_timezone,
    }


async def _notify_admin_schedule_update(user: User):
    """Notify Admin API about worker schedule/pause change via internal endpoint."""
    schedule_data = _build_schedule_data(user)
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(
                f"{ADMIN_API_URL}/internal/notify-schedule-updated",
                json={"schedule_data": schedule_data}
            )
    except Exception as e:
        logger.warning(f"Failed to notify admin about schedule update: {e}")


# --- Endpoints ---

@router.get("/me", response_model=ScheduleResponse)
async def get_schedule(
    current_user: User = Depends(get_current_worker_user),
):
    """Get current worker's schedule and pause status."""
    schedule = None
    if current_user.worker_schedule:
        schedule = [DaySchedule(**d) for d in current_user.worker_schedule]
    return ScheduleResponse(
        worker_paused=current_user.worker_paused,
        worker_schedule=schedule,
        worker_timezone=current_user.worker_timezone,
    )


@router.put("/me", response_model=ScheduleResponse)
async def update_schedule(
    body: UpdateScheduleRequest,
    current_user: User = Depends(get_current_worker_user),
    db: AsyncSession = Depends(get_db),
):
    """Update current worker's schedule."""
    current_user.worker_schedule = [d.model_dump() for d in body.schedule]
    if body.timezone is not None:
        current_user.worker_timezone = body.timezone
    await db.commit()
    await db.refresh(current_user)

    await _notify_admin_schedule_update(current_user)

    schedule = [DaySchedule(**d) for d in current_user.worker_schedule]
    return ScheduleResponse(
        worker_paused=current_user.worker_paused,
        worker_schedule=schedule,
        worker_timezone=current_user.worker_timezone,
    )


@router.post("/me/pause", response_model=ScheduleResponse)
async def toggle_pause(
    body: UpdatePauseRequest,
    current_user: User = Depends(get_current_worker_user),
    db: AsyncSession = Depends(get_db),
):
    """Toggle current worker's pause status."""
    current_user.worker_paused = body.paused
    await db.commit()
    await db.refresh(current_user)

    await _notify_admin_schedule_update(current_user)

    schedule = None
    if current_user.worker_schedule:
        schedule = [DaySchedule(**d) for d in current_user.worker_schedule]
    return ScheduleResponse(
        worker_paused=current_user.worker_paused,
        worker_schedule=schedule,
        worker_timezone=current_user.worker_timezone,
    )
