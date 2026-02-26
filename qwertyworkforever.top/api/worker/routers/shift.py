"""
Worker shift management endpoints.
Allows workers to start/pause/resume/stop shifts with time tracking.
"""
import os
import logging
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from pydantic import BaseModel
import httpx

from api.common.database import get_postgres_session as get_db
from api.common.models_postgres import User, WorkerShift
from api.worker.dependencies import get_current_worker_user

ADMIN_API_URL = os.getenv("ADMIN_API_URL", "http://admin_api:8002")
INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY", "")

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Shift"])


# --- Pydantic models ---

class ShiftResponse(BaseModel):
    id: Optional[str] = None
    worker_status: str  # idle / active / paused
    started_at: Optional[str] = None
    elapsed_seconds: int = 0
    pause_duration_seconds: int = 0
    tickets_completed: int = 0
    tickets_rejected: int = 0


class ShiftHistoryItem(BaseModel):
    id: str
    started_at: str
    ended_at: Optional[str] = None
    duration_seconds: int = 0
    pause_duration_seconds: int = 0
    tickets_completed: int = 0
    tickets_rejected: int = 0


class ShiftHistoryResponse(BaseModel):
    shifts: List[ShiftHistoryItem]
    total_count: int


# --- Helpers ---

def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _compute_elapsed(shift: WorkerShift) -> int:
    """Compute elapsed work seconds (excluding pauses)."""
    now = _utcnow()
    end = shift.ended_at or now
    total = int((end - shift.started_at).total_seconds())
    pause = shift.pause_duration_seconds
    # If currently paused, add ongoing pause duration
    if shift.paused_at:
        pause += int((now - shift.paused_at).total_seconds())
    return max(total - pause, 0)


def _shift_to_response(shift: Optional[WorkerShift], worker_status: str) -> ShiftResponse:
    if not shift:
        return ShiftResponse(worker_status=worker_status)
    return ShiftResponse(
        id=str(shift.id),
        worker_status=worker_status,
        started_at=shift.started_at.isoformat(),
        elapsed_seconds=_compute_elapsed(shift),
        pause_duration_seconds=shift.pause_duration_seconds + (
            int((_utcnow() - shift.paused_at).total_seconds()) if shift.paused_at else 0
        ),
        tickets_completed=shift.tickets_completed,
        tickets_rejected=shift.tickets_rejected,
    )


async def _get_current_shift(db: AsyncSession, worker_id) -> Optional[WorkerShift]:
    result = await db.execute(
        select(WorkerShift).where(
            WorkerShift.worker_id == worker_id,
            WorkerShift.ended_at.is_(None),
        ).order_by(desc(WorkerShift.started_at)).limit(1)
    )
    return result.scalar_one_or_none()


async def _notify_admin_shift_update(user: User):
    """Notify Admin API about worker shift status change."""
    data = {
        "worker_id": str(user.id),
        "worker_username": user.username,
        "worker_status": user.worker_status,
    }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(
                f"{ADMIN_API_URL}/internal/notify-shift-updated",
                json={"shift_data": data},
                headers={"X-Internal-Api-Key": INTERNAL_API_KEY}
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Failed to notify admin about shift update: {e}")


# --- Endpoints ---

@router.post("/start", response_model=ShiftResponse)
async def start_shift(
    current_user: User = Depends(get_current_worker_user),
    db: AsyncSession = Depends(get_db),
):
    """Start a new shift."""
    if current_user.worker_status != 'idle':
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Shift already in progress. Stop current shift first."
        )

    now = _utcnow()
    shift = WorkerShift(
        worker_id=current_user.id,
        started_at=now,
    )
    db.add(shift)
    current_user.worker_status = 'active'
    current_user.worker_paused = False
    await db.commit()
    await db.refresh(shift)
    await db.refresh(current_user)

    await _notify_admin_shift_update(current_user)
    return _shift_to_response(shift, current_user.worker_status)


@router.post("/pause", response_model=ShiftResponse)
async def pause_shift(
    current_user: User = Depends(get_current_worker_user),
    db: AsyncSession = Depends(get_db),
):
    """Pause the current shift."""
    if current_user.worker_status != 'active':
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active shift to pause."
        )

    shift = await _get_current_shift(db, current_user.id)
    if not shift:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No open shift found.")

    shift.paused_at = _utcnow()
    current_user.worker_status = 'paused'
    current_user.worker_paused = True
    await db.commit()
    await db.refresh(shift)
    await db.refresh(current_user)

    await _notify_admin_shift_update(current_user)
    return _shift_to_response(shift, current_user.worker_status)


@router.post("/resume", response_model=ShiftResponse)
async def resume_shift(
    current_user: User = Depends(get_current_worker_user),
    db: AsyncSession = Depends(get_db),
):
    """Resume a paused shift."""
    if current_user.worker_status != 'paused':
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Shift is not paused."
        )

    shift = await _get_current_shift(db, current_user.id)
    if not shift or not shift.paused_at:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No paused shift found.")

    now = _utcnow()
    pause_seconds = int((now - shift.paused_at).total_seconds())
    shift.pause_duration_seconds += pause_seconds
    shift.paused_at = None
    current_user.worker_status = 'active'
    current_user.worker_paused = False
    await db.commit()
    await db.refresh(shift)
    await db.refresh(current_user)

    await _notify_admin_shift_update(current_user)
    return _shift_to_response(shift, current_user.worker_status)


@router.post("/stop", response_model=ShiftResponse)
async def stop_shift(
    current_user: User = Depends(get_current_worker_user),
    db: AsyncSession = Depends(get_db),
):
    """Stop the current shift."""
    if current_user.worker_status not in ('active', 'paused'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active shift to stop."
        )

    shift = await _get_current_shift(db, current_user.id)
    if not shift:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No open shift found.")

    now = _utcnow()
    # If paused, finalize current pause duration
    if shift.paused_at:
        pause_seconds = int((now - shift.paused_at).total_seconds())
        shift.pause_duration_seconds += pause_seconds
        shift.paused_at = None

    shift.ended_at = now
    current_user.worker_status = 'idle'
    current_user.worker_paused = True
    await db.commit()
    await db.refresh(shift)
    await db.refresh(current_user)

    await _notify_admin_shift_update(current_user)
    return _shift_to_response(shift, 'idle')


@router.get("/current", response_model=ShiftResponse)
async def get_current_shift(
    current_user: User = Depends(get_current_worker_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current shift status."""
    shift = None
    if current_user.worker_status in ('active', 'paused'):
        shift = await _get_current_shift(db, current_user.id)
    return _shift_to_response(shift, current_user.worker_status)


@router.get("/history", response_model=ShiftHistoryResponse)
async def get_shift_history(
    current_user: User = Depends(get_current_worker_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
):
    """Get shift history for current worker."""
    # Count
    from sqlalchemy import func
    count_result = await db.execute(
        select(func.count()).select_from(WorkerShift).where(
            WorkerShift.worker_id == current_user.id,
            WorkerShift.ended_at.isnot(None),
        )
    )
    total_count = count_result.scalar() or 0

    # Fetch
    result = await db.execute(
        select(WorkerShift).where(
            WorkerShift.worker_id == current_user.id,
            WorkerShift.ended_at.isnot(None),
        ).order_by(desc(WorkerShift.started_at)).offset(offset).limit(limit)
    )
    shifts = result.scalars().all()

    items = []
    for s in shifts:
        total_secs = int((s.ended_at - s.started_at).total_seconds())
        duration = max(total_secs - s.pause_duration_seconds, 0)
        items.append(ShiftHistoryItem(
            id=str(s.id),
            started_at=s.started_at.isoformat(),
            ended_at=s.ended_at.isoformat() if s.ended_at else None,
            duration_seconds=duration,
            pause_duration_seconds=s.pause_duration_seconds,
            tickets_completed=s.tickets_completed,
            tickets_rejected=s.tickets_rejected,
        ))

    return ShiftHistoryResponse(shifts=items, total_count=total_count)
