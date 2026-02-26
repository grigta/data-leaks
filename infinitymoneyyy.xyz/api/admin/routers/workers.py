"""
Worker registration management endpoints.
"""
import os
import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel
from typing import Optional, List
from uuid import UUID
from decimal import Decimal
from sqlalchemy.exc import IntegrityError
import httpx

from api.common.database import get_postgres_session as get_db
from api.common.models_postgres import User, WorkerRegistrationRequest, RegistrationStatus, AppSettings, ManualSSNTicket, TicketStatus, WorkerInvoice, InvoiceStatus
from api.common.auth import generate_access_code
from api.common.pricing import MANUAL_SSN_COST, INSTANT_SSN_PRICE, MANUAL_SSN_PRICE
from api.admin.dependencies import get_current_admin_user
from api.admin.websocket import ws_manager

WORKER_API_URL = os.getenv("WORKER_API_URL", "http://worker_api:8003")
INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY", "")

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/worker-requests", tags=["Worker Requests"])

# === Worker management endpoints (prefix: /workers) ===
workers_router = APIRouter(prefix="/workers", tags=["Workers"])


class WorkerItemResponse(BaseModel):
    id: str
    username: str
    email: Optional[str]
    access_code: Optional[str]
    worker_role: bool
    is_banned: bool
    is_online: bool = False
    worker_status: str = 'idle'
    current_shift_started_at: Optional[str] = None
    created_at: str


class WorkerListResponse(BaseModel):
    workers: List[WorkerItemResponse]
    total_count: int


class GenerateWorkerResponse(BaseModel):
    message: str
    access_code: str


@workers_router.get("", response_model=WorkerListResponse)
async def list_workers(
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    admin_user=Depends(get_current_admin_user),
):
    """List all users with worker_role=True."""
    query = (
        select(User)
        .where(User.worker_role == True)
        .order_by(User.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(query)
    users = result.scalars().all()

    count_result = await db.execute(
        select(func.count(User.id)).where(User.worker_role == True)
    )
    total = count_result.scalar_one()

    # Get online workers from worker API
    online_worker_ids = []
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"{WORKER_API_URL}/internal/online-workers",
                headers={"X-Internal-Api-Key": INTERNAL_API_KEY}
            )
            if resp.status_code == 200:
                online_worker_ids = resp.json().get("online_worker_ids", [])
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Failed to fetch online workers from worker_api: {e}")

    # Get current shift start times for active workers
    from api.common.models_postgres import WorkerShift
    from sqlalchemy import desc
    shift_map = {}
    active_worker_ids = [u.id for u in users if u.worker_status in ('active', 'paused')]
    if active_worker_ids:
        shift_result = await db.execute(
            select(WorkerShift.worker_id, WorkerShift.started_at).where(
                WorkerShift.worker_id.in_(active_worker_ids),
                WorkerShift.ended_at.is_(None),
            )
        )
        for row in shift_result:
            shift_map[str(row.worker_id)] = row.started_at.isoformat()

    return WorkerListResponse(
        workers=[
            WorkerItemResponse(
                id=str(u.id),
                username=u.username,
                email=u.email,
                access_code=u.access_code,
                worker_role=u.worker_role,
                is_banned=u.is_banned,
                is_online=str(u.id) in online_worker_ids,
                worker_status=u.worker_status,
                current_shift_started_at=shift_map.get(str(u.id)),
                created_at=u.created_at.isoformat(),
            )
            for u in users
        ],
        total_count=total,
    )


@workers_router.post("/generate", response_model=GenerateWorkerResponse)
async def generate_worker_access_code(
    db: AsyncSession = Depends(get_db),
    admin_user=Depends(get_current_admin_user),
):
    """Generate a new unique access code for a worker."""
    # Generate unique access code
    for _ in range(10):
        code = generate_access_code()
        existing = await db.execute(
            select(User.id).where(User.access_code == code)
        )
        if not existing.scalar_one_or_none():
            break
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate unique access code",
        )

    # Create worker user with generated access code
    new_user = User(
        username=f"worker_{code.replace('-', '')[:8]}",
        access_code=code,
        hashed_password="",  # No password - worker registers via qwertyworkforever.top
        is_admin=False,
        worker_role=True,
        balance=Decimal("0.00"),
    )
    db.add(new_user)

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Failed to create worker - username conflict, try again",
        )

    await db.refresh(new_user)
    logger.info(
        f"Admin {admin_user.username} generated worker access code {code} (user {new_user.id})"
    )

    return GenerateWorkerResponse(
        message="Access code generated successfully",
        access_code=code,
    )


@workers_router.delete("/{worker_id}")
async def remove_worker(
    worker_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin_user=Depends(get_current_admin_user),
):
    """Remove worker role from a user."""
    result = await db.execute(select(User).where(User.id == worker_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not user.worker_role:
        raise HTTPException(status_code=400, detail="User is not a worker")

    user.worker_role = False
    await db.commit()

    logger.info(f"Admin {admin_user.username} removed worker role from {user.username}")
    return {"message": f"Worker role removed from {user.username}"}


class WorkerDistributionItem(BaseModel):
    worker_id: str
    username: str
    is_online: bool
    load_percentage: Optional[int] = None


class DistributionConfigResponse(BaseModel):
    distribution_mode: str  # "even" or "percentage"
    workers: List[WorkerDistributionItem]


class UpdateDistributionRequest(BaseModel):
    distribution_mode: str  # "even" or "percentage"
    workers: Optional[List[dict]] = None  # [{worker_id, load_percentage}]


@workers_router.get("/distribution", response_model=DistributionConfigResponse)
async def get_distribution_config(
    db: AsyncSession = Depends(get_db),
    admin_user=Depends(get_current_admin_user),
):
    """Get current load distribution config."""
    # Get distribution mode
    setting = await db.execute(
        select(AppSettings).where(AppSettings.key == "worker_distribution_mode")
    )
    mode_row = setting.scalar_one_or_none()
    mode = mode_row.value if mode_row else "even"

    # Get all workers
    result = await db.execute(
        select(User).where(User.worker_role == True).order_by(User.created_at.desc())
    )
    workers = result.scalars().all()

    # Get online workers
    online_worker_ids = []
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"{WORKER_API_URL}/internal/online-workers",
                headers={"X-Internal-Api-Key": INTERNAL_API_KEY}
            )
            if resp.status_code == 200:
                online_worker_ids = resp.json().get("online_worker_ids", [])
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Failed to fetch online workers: {e}")

    return DistributionConfigResponse(
        distribution_mode=mode,
        workers=[
            WorkerDistributionItem(
                worker_id=str(w.id),
                username=w.username,
                is_online=str(w.id) in online_worker_ids,
                load_percentage=w.load_percentage,
            )
            for w in workers
        ],
    )


@workers_router.put("/distribution")
async def update_distribution_config(
    request: UpdateDistributionRequest,
    db: AsyncSession = Depends(get_db),
    admin_user=Depends(get_current_admin_user),
):
    """Update load distribution config."""
    if request.distribution_mode not in ("even", "percentage"):
        raise HTTPException(status_code=400, detail="Mode must be 'even' or 'percentage'")

    # Validate percentages sum to 100 in percentage mode
    if request.distribution_mode == "percentage" and request.workers:
        total = sum(w.get("load_percentage", 0) or 0 for w in request.workers)
        if total != 100:
            raise HTTPException(status_code=400, detail=f"Percentages must sum to 100 (current: {total})")

    # Update mode in app_settings
    setting = await db.execute(
        select(AppSettings).where(AppSettings.key == "worker_distribution_mode")
    )
    mode_row = setting.scalar_one_or_none()
    if mode_row:
        mode_row.value = request.distribution_mode
    else:
        db.add(AppSettings(key="worker_distribution_mode", value=request.distribution_mode))

    # Update per-worker percentages
    if request.workers:
        for w_data in request.workers:
            wid = w_data.get("worker_id")
            pct = w_data.get("load_percentage")
            if wid:
                result = await db.execute(select(User).where(User.id == UUID(wid)))
                user = result.scalar_one_or_none()
                if user and user.worker_role:
                    user.load_percentage = pct if request.distribution_mode == "percentage" else None

    # If switching to even mode, clear all percentages
    if request.distribution_mode == "even":
        workers = await db.execute(select(User).where(User.worker_role == True))
        for u in workers.scalars().all():
            u.load_percentage = None

    await db.commit()
    logger.info(f"Admin {admin_user.username} updated distribution mode to {request.distribution_mode}")
    return {"message": "Distribution config updated"}


# --- Worker Schedule & Pause ---

class AdminDaySchedule(BaseModel):
    day: str
    active: bool
    start: str
    end: str


class AdminUpdateScheduleRequest(BaseModel):
    schedule: List[AdminDaySchedule]
    timezone: Optional[str] = None


class AdminUpdatePauseRequest(BaseModel):
    paused: bool


class WorkerShiftItem(BaseModel):
    id: str
    started_at: str
    ended_at: Optional[str] = None
    duration_seconds: int = 0
    pause_duration_seconds: int = 0
    tickets_completed: int = 0
    tickets_rejected: int = 0


class WorkerShiftListResponse(BaseModel):
    shifts: List[WorkerShiftItem]
    total_count: int


async def _notify_worker_shift(worker_id: str, shift_data: dict):
    """Notify worker about shift change from admin via Worker API internal endpoint."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(
                f"{WORKER_API_URL}/internal/notify-shift-from-admin",
                json={"worker_id": worker_id, "shift_data": shift_data},
                headers={"X-Internal-Api-Key": INTERNAL_API_KEY}
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Failed to notify worker about shift update: {e}")


@workers_router.get("/{worker_id}/shifts", response_model=WorkerShiftListResponse)
async def get_worker_shifts(
    worker_id: UUID,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    admin_user=Depends(get_current_admin_user),
):
    """Get shift history for a specific worker."""
    from api.common.models_postgres import WorkerShift
    from sqlalchemy import desc

    result = await db.execute(select(User).where(User.id == worker_id))
    user = result.scalar_one_or_none()
    if not user or not user.worker_role:
        raise HTTPException(status_code=404, detail="Worker not found")

    count_result = await db.execute(
        select(func.count()).select_from(WorkerShift).where(WorkerShift.worker_id == worker_id)
    )
    total_count = count_result.scalar() or 0

    shifts_result = await db.execute(
        select(WorkerShift).where(WorkerShift.worker_id == worker_id)
        .order_by(desc(WorkerShift.started_at)).offset(offset).limit(limit)
    )
    shifts = shifts_result.scalars().all()

    items = []
    for s in shifts:
        end = s.ended_at or datetime.utcnow()
        total_secs = int((end - s.started_at).total_seconds())
        pause = s.pause_duration_seconds
        if s.paused_at:
            pause += int((datetime.utcnow() - s.paused_at).total_seconds())
        duration = max(total_secs - pause, 0)
        items.append(WorkerShiftItem(
            id=str(s.id),
            started_at=s.started_at.isoformat(),
            ended_at=s.ended_at.isoformat() if s.ended_at else None,
            duration_seconds=duration,
            pause_duration_seconds=pause,
            tickets_completed=s.tickets_completed,
            tickets_rejected=s.tickets_rejected,
        ))

    return WorkerShiftListResponse(shifts=items, total_count=total_count)


@workers_router.post("/{worker_id}/force-stop")
async def force_stop_worker_shift(
    worker_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin_user=Depends(get_current_admin_user),
):
    """Force-stop a worker's current shift (admin only)."""
    from api.common.models_postgres import WorkerShift
    from sqlalchemy import desc

    result = await db.execute(select(User).where(User.id == worker_id))
    user = result.scalar_one_or_none()
    if not user or not user.worker_role:
        raise HTTPException(status_code=404, detail="Worker not found")

    if user.worker_status not in ('active', 'paused'):
        raise HTTPException(status_code=400, detail="Worker has no active shift")

    # Find open shift
    shift_result = await db.execute(
        select(WorkerShift).where(
            WorkerShift.worker_id == worker_id,
            WorkerShift.ended_at.is_(None),
        ).order_by(desc(WorkerShift.started_at)).limit(1)
    )
    shift = shift_result.scalar_one_or_none()

    now = datetime.utcnow()
    if shift:
        if shift.paused_at:
            shift.pause_duration_seconds += int((now - shift.paused_at).total_seconds())
            shift.paused_at = None
        shift.ended_at = now

    user.worker_status = 'idle'
    user.worker_paused = True
    await db.commit()

    shift_data = {
        "worker_id": str(user.id),
        "worker_username": user.username,
        "worker_status": "idle",
    }

    # Broadcast to admins
    await ws_manager.broadcast_to_admins("worker_shift_updated", shift_data)

    # Notify worker
    await _notify_worker_shift(str(worker_id), shift_data)

    logger.info(f"Admin {admin_user.username} force-stopped shift for worker {user.username}")
    return {"status": "ok", "message": f"Worker {user.username} shift force-stopped"}


# --- Worker Stats & Invoices ---

class WorkerStatsItem(BaseModel):
    worker_id: str
    username: str
    total_assigned: int
    total_completed: int
    total_rejected: int
    avg_completion_time_minutes: Optional[float] = None
    dynamic_cost_instant: str
    dynamic_cost_manual: str
    total_earned: str
    total_paid: str
    debt: str
    wallet_address: Optional[str] = None
    wallet_network: Optional[str] = None


class WorkerInvoiceItem(BaseModel):
    id: str
    worker_id: str
    worker_username: str
    amount: str
    wallet_address: str
    wallet_network: str
    status: str
    paid_at: Optional[str] = None
    created_at: str


class WorkerInvoiceListResponse(BaseModel):
    invoices: List[WorkerInvoiceItem]
    total_count: int
    pending_count: int


class PendingInvoiceCountResponse(BaseModel):
    count: int


@workers_router.get("/stats", response_model=List[WorkerStatsItem])
async def get_worker_stats(
    db: AsyncSession = Depends(get_db),
    admin_user=Depends(get_current_admin_user),
):
    """Get statistics for all workers."""
    from sqlalchemy import extract, case

    # Get all workers
    workers_result = await db.execute(
        select(User).where(User.worker_role == True).order_by(User.created_at.desc())
    )
    workers = workers_result.scalars().all()

    if not workers:
        return []

    worker_ids = [w.id for w in workers]

    # Ticket stats per worker (single query)
    ticket_stats_query = (
        select(
            ManualSSNTicket.worker_id,
            func.count().label("total_assigned"),
            func.count().filter(ManualSSNTicket.status == TicketStatus.completed).label("total_completed"),
            func.count().filter(ManualSSNTicket.status == TicketStatus.rejected).label("total_rejected"),
            func.avg(
                extract("epoch", ManualSSNTicket.updated_at - ManualSSNTicket.created_at) / 60
            ).filter(ManualSSNTicket.status == TicketStatus.completed).label("avg_minutes"),
        )
        .where(ManualSSNTicket.worker_id.in_(worker_ids))
        .group_by(ManualSSNTicket.worker_id)
    )
    ticket_result = await db.execute(ticket_stats_query)
    ticket_stats = {str(row.worker_id): row for row in ticket_result}

    # Invoice paid totals per worker
    invoice_stats_query = (
        select(
            WorkerInvoice.worker_id,
            func.coalesce(func.sum(WorkerInvoice.amount), Decimal("0")).label("total_paid"),
        )
        .where(
            WorkerInvoice.worker_id.in_(worker_ids),
            WorkerInvoice.status == InvoiceStatus.paid,
        )
        .group_by(WorkerInvoice.worker_id)
    )
    invoice_result = await db.execute(invoice_stats_query)
    invoice_stats = {str(row.worker_id): row.total_paid for row in invoice_result}

    result = []
    for w in workers:
        wid = str(w.id)
        ts = ticket_stats.get(wid)
        total_assigned = ts.total_assigned if ts else 0
        total_completed = ts.total_completed if ts else 0
        total_rejected = ts.total_rejected if ts else 0
        avg_min = float(ts.avg_minutes) if ts and ts.avg_minutes else None

        total_earned = Decimal(total_completed) * MANUAL_SSN_COST
        total_paid = invoice_stats.get(wid, Decimal("0"))
        debt = total_earned - total_paid

        result.append(WorkerStatsItem(
            worker_id=wid,
            username=w.username,
            total_assigned=total_assigned,
            total_completed=total_completed,
            total_rejected=total_rejected,
            avg_completion_time_minutes=round(avg_min, 1) if avg_min else None,
            dynamic_cost_instant=f"{INSTANT_SSN_PRICE:.2f}",
            dynamic_cost_manual=f"{MANUAL_SSN_PRICE:.2f}",
            total_earned=f"{total_earned:.2f}",
            total_paid=f"{total_paid:.2f}",
            debt=f"{debt:.2f}",
            wallet_address=w.wallet_address,
            wallet_network=w.wallet_network,
        ))

    return result


@workers_router.get("/invoices", response_model=WorkerInvoiceListResponse)
async def list_worker_invoices(
    status_filter: Optional[str] = None,
    worker_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    admin_user=Depends(get_current_admin_user),
):
    """List all worker invoices with optional filters."""
    query = select(WorkerInvoice).join(User, WorkerInvoice.worker_id == User.id)
    count_query = select(func.count()).select_from(WorkerInvoice)

    if status_filter:
        try:
            status_enum = InvoiceStatus(status_filter)
            query = query.where(WorkerInvoice.status == status_enum)
            count_query = count_query.where(WorkerInvoice.status == status_enum)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid status filter")

    if worker_id:
        query = query.where(WorkerInvoice.worker_id == UUID(worker_id))
        count_query = count_query.where(WorkerInvoice.worker_id == UUID(worker_id))

    query = query.order_by(WorkerInvoice.created_at.desc()).offset(offset).limit(limit)

    result = await db.execute(query)
    invoices = result.scalars().all()

    total_result = await db.execute(count_query)
    total_count = total_result.scalar_one()

    # Pending count (always unfiltered by status)
    pending_query = select(func.count()).select_from(WorkerInvoice).where(
        WorkerInvoice.status == InvoiceStatus.pending
    )
    pending_result = await db.execute(pending_query)
    pending_count = pending_result.scalar_one()

    # Load worker usernames
    worker_ids_set = {inv.worker_id for inv in invoices}
    workers_result = await db.execute(
        select(User.id, User.username).where(User.id.in_(worker_ids_set))
    )
    username_map = {str(row.id): row.username for row in workers_result}

    return WorkerInvoiceListResponse(
        invoices=[
            WorkerInvoiceItem(
                id=str(inv.id),
                worker_id=str(inv.worker_id),
                worker_username=username_map.get(str(inv.worker_id), "unknown"),
                amount=f"{inv.amount:.2f}",
                wallet_address=inv.wallet_address,
                wallet_network=inv.wallet_network,
                status=inv.status.value,
                paid_at=inv.paid_at.isoformat() if inv.paid_at else None,
                created_at=inv.created_at.isoformat(),
            )
            for inv in invoices
        ],
        total_count=total_count,
        pending_count=pending_count,
    )


@workers_router.get("/invoices/pending-count", response_model=PendingInvoiceCountResponse)
async def get_pending_invoice_count(
    db: AsyncSession = Depends(get_db),
    admin_user=Depends(get_current_admin_user),
):
    """Get count of pending worker invoices."""
    result = await db.execute(
        select(func.count()).select_from(WorkerInvoice).where(
            WorkerInvoice.status == InvoiceStatus.pending
        )
    )
    return PendingInvoiceCountResponse(count=result.scalar_one())


@workers_router.post("/invoices/{invoice_id}/pay")
async def mark_invoice_paid(
    invoice_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin_user=Depends(get_current_admin_user),
):
    """Mark a worker invoice as paid."""
    result = await db.execute(
        select(WorkerInvoice).where(WorkerInvoice.id == invoice_id)
    )
    invoice = result.scalar_one_or_none()

    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if invoice.status != InvoiceStatus.pending:
        raise HTTPException(status_code=400, detail="Invoice is not pending")

    invoice.status = InvoiceStatus.paid
    invoice.paid_at = datetime.utcnow()
    await db.commit()
    await db.refresh(invoice)

    # Get worker username
    worker_result = await db.execute(select(User.username).where(User.id == invoice.worker_id))
    worker_username = worker_result.scalar_one_or_none() or "unknown"

    logger.info(f"Admin {admin_user.username} marked invoice {invoice_id} as paid (${invoice.amount})")

    return WorkerInvoiceItem(
        id=str(invoice.id),
        worker_id=str(invoice.worker_id),
        worker_username=worker_username,
        amount=f"{invoice.amount:.2f}",
        wallet_address=invoice.wallet_address,
        wallet_network=invoice.wallet_network,
        status=invoice.status.value,
        paid_at=invoice.paid_at.isoformat() if invoice.paid_at else None,
        created_at=invoice.created_at.isoformat(),
    )


@workers_router.get("/{worker_id}/invoices", response_model=WorkerInvoiceListResponse)
async def get_worker_invoices(
    worker_id: UUID,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    admin_user=Depends(get_current_admin_user),
):
    """Get invoices for a specific worker."""
    query = (
        select(WorkerInvoice)
        .where(WorkerInvoice.worker_id == worker_id)
        .order_by(WorkerInvoice.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(query)
    invoices = result.scalars().all()

    total_result = await db.execute(
        select(func.count()).select_from(WorkerInvoice).where(
            WorkerInvoice.worker_id == worker_id
        )
    )
    total_count = total_result.scalar_one()

    pending_result = await db.execute(
        select(func.count()).select_from(WorkerInvoice).where(
            WorkerInvoice.status == InvoiceStatus.pending
        )
    )
    pending_count = pending_result.scalar_one()

    # Get worker username
    worker_result = await db.execute(select(User.username).where(User.id == worker_id))
    worker_username = worker_result.scalar_one_or_none() or "unknown"

    return WorkerInvoiceListResponse(
        invoices=[
            WorkerInvoiceItem(
                id=str(inv.id),
                worker_id=str(inv.worker_id),
                worker_username=worker_username,
                amount=f"{inv.amount:.2f}",
                wallet_address=inv.wallet_address,
                wallet_network=inv.wallet_network,
                status=inv.status.value,
                paid_at=inv.paid_at.isoformat() if inv.paid_at else None,
                created_at=inv.created_at.isoformat(),
            )
            for inv in invoices
        ],
        total_count=total_count,
        pending_count=pending_count,
    )


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
        except HTTPException:
            raise
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
        except HTTPException:
            raise
        except Exception as e:
            logger.warning(f"Failed to broadcast worker rejection: {e}")

        logger.info(f"Admin {admin_user.username} rejected worker registration for {registration_request.username}")

        return RejectWorkerResponse(
            message="Worker registration request rejected",
            username=registration_request.username
        )

    except HTTPException:
        raise
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error rejecting worker request {request_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to reject worker request"
        )
