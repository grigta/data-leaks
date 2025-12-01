"""
Admin statistics router
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime, timedelta
from typing import Literal

from api.admin.dependencies import get_current_admin_user
from api.common.database import get_postgres_session
from api.common.models_postgres import ManualSSNTicket as Ticket, WorkerRegistrationRequest as WorkerRequest, User, Session

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/tickets")
async def get_tickets_stats(
    period: Literal["1d", "7d", "30d", "all"] = Query(default="7d"),
    db: AsyncSession = Depends(get_postgres_session),
    current_user: User = Depends(get_current_admin_user),
):
    """
    Get ticket statistics for specified period

    Args:
        period: Time period - 1d (today), 7d (this week), 30d (this month), all (all time)

    Returns:
        {
            "total": int,
            "pending": int,
            "processing": int,
            "completed": int,
            "rejected": int,
            "success_rate": float (percentage),
            "avg_time": float (minutes)
        }
    """
    from sqlalchemy import case, extract

    # Calculate date filter based on period
    now = datetime.utcnow()
    date_filter = None

    if period == "1d":
        date_filter = now - timedelta(days=1)
    elif period == "7d":
        date_filter = now - timedelta(days=7)
    elif period == "30d":
        date_filter = now - timedelta(days=30)
    # period == "all" - no filter

    # Build query with conditional aggregation
    # NOTE: Average processing time uses (updated_at - created_at) for completed tickets.
    # This is an approximation since the model does not have a dedicated completed_at field.
    # For more accurate tracking, consider adding a completed_at timestamp field or
    # implementing status transition tracking.
    query = select(
        func.count().label('total'),
        func.sum(case((Ticket.status == 'pending', 1), else_=0)).label('pending'),
        func.sum(case((Ticket.status == 'processing', 1), else_=0)).label('processing'),
        func.sum(case((Ticket.status == 'completed', 1), else_=0)).label('completed'),
        func.sum(case((Ticket.status == 'rejected', 1), else_=0)).label('rejected'),
        func.avg(
            case(
                (Ticket.status == 'completed',
                 extract('epoch', Ticket.updated_at - Ticket.created_at) / 60),
                else_=None
            )
        ).label('avg_time')
    ).select_from(Ticket)

    if date_filter:
        query = query.where(Ticket.created_at >= date_filter)

    # Execute query
    result = await db.execute(query)
    row = result.first()

    # Calculate success rate
    total = row.total or 0
    completed = row.completed or 0
    rejected = row.rejected or 0

    # Success rate: completed / (completed + rejected) * 100
    # Only count tickets that have been resolved (completed or rejected)
    resolved_tickets = completed + rejected
    success_rate = (completed / resolved_tickets * 100.0) if resolved_tickets > 0 else 0.0

    return {
        "total": total,
        "pending": row.pending or 0,
        "processing": row.processing or 0,
        "completed": completed,
        "rejected": rejected,
        "success_rate": round(success_rate, 2),
        "avg_time": float(row.avg_time) if row.avg_time else None
    }


@router.get("/workers")
async def get_workers_stats(
    period: Literal["1d", "7d", "30d", "all"] = Query(default="7d"),
    db: AsyncSession = Depends(get_postgres_session),
    current_user: User = Depends(get_current_admin_user),
):
    """
    Get worker statistics for specified period

    Args:
        period: Time period - 1d, 7d, 30d, all

    Returns:
        {
            "total": int,
            "active": int (active within selected period),
            "pending_requests": int
        }
    """

    # Calculate date filter based on period
    now = datetime.utcnow()
    date_filter = None

    if period == "1d":
        date_filter = now - timedelta(days=1)
    elif period == "7d":
        date_filter = now - timedelta(days=7)
    elif period == "30d":
        date_filter = now - timedelta(days=30)
    # period == "all" - no filter

    # Get all workers (users with worker_role=True) created within period
    workers_query = select(User).where(User.worker_role == True)
    if date_filter:
        workers_query = workers_query.where(User.created_at >= date_filter)

    result = await db.execute(workers_query)
    workers = result.scalars().all()

    total = len(workers)

    # Active workers - based on selected period (workers with sessions created in the period)
    active_date = date_filter if date_filter else (now - timedelta(days=30))
    active_workers_query = (
        select(func.count(func.distinct(Session.user_id)))
        .join(User, Session.user_id == User.id)
        .where(
            User.worker_role == True,
            Session.created_at >= active_date
        )
    )
    active_result = await db.execute(active_workers_query)
    active = active_result.scalar() or 0

    # Get pending worker requests
    pending_requests_query = select(func.count()).select_from(WorkerRequest).where(
        WorkerRequest.status == "pending"
    )
    pending_requests_result = await db.execute(pending_requests_query)
    pending_requests = pending_requests_result.scalar() or 0

    return {
        "total": total,
        "active": active,
        "pending_requests": pending_requests
    }
