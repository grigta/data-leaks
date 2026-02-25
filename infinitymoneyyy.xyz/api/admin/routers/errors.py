"""
Admin API error logs router.
View and manage API error logs (SearchBug, WhitePages).
"""
import logging
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, func, delete, desc
from sqlalchemy.ext.asyncio import AsyncSession

from api.admin.dependencies import get_current_admin_user
from api.common.database import get_postgres_session
from api.common.models_postgres import ApiErrorLog

router = APIRouter()
logger = logging.getLogger(__name__)

CLEANUP_DAYS = 30


# ============================================
# Pydantic Response Models
# ============================================

class ErrorLogItem(BaseModel):
    id: str
    api_name: str
    method: str
    error_type: str
    error_message: str
    status_code: Optional[int] = None
    request_params: Optional[dict] = None
    created_at: str


class ErrorLogsResponse(BaseModel):
    items: list[ErrorLogItem]
    total: int
    page: int
    page_size: int


class ErrorStatsResponse(BaseModel):
    total_errors: int
    errors_today: int
    errors_by_api: dict[str, int]


# ============================================
# Endpoints
# ============================================

@router.get("/errors", response_model=ErrorLogsResponse)
async def get_error_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    api_name: Optional[str] = Query(None),
    error_type: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_postgres_session),
    _admin=Depends(get_current_admin_user),
):
    """Get paginated list of API error logs."""
    query = select(ApiErrorLog)
    count_query = select(func.count(ApiErrorLog.id))

    if api_name:
        query = query.where(ApiErrorLog.api_name == api_name)
        count_query = count_query.where(ApiErrorLog.api_name == api_name)

    if error_type:
        query = query.where(ApiErrorLog.error_type == error_type)
        count_query = count_query.where(ApiErrorLog.error_type == error_type)

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    offset = (page - 1) * page_size
    query = query.order_by(desc(ApiErrorLog.created_at)).offset(offset).limit(page_size)

    result = await db.execute(query)
    logs = result.scalars().all()

    items = [
        ErrorLogItem(
            id=str(log.id),
            api_name=log.api_name,
            method=log.method,
            error_type=log.error_type,
            error_message=log.error_message,
            status_code=log.status_code,
            request_params=log.request_params,
            created_at=log.created_at.isoformat(),
        )
        for log in logs
    ]

    return ErrorLogsResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/errors/stats", response_model=ErrorStatsResponse)
async def get_error_stats(
    db: AsyncSession = Depends(get_postgres_session),
    _admin=Depends(get_current_admin_user),
):
    """Get error statistics summary."""
    total_result = await db.execute(select(func.count(ApiErrorLog.id)))
    total_errors = total_result.scalar() or 0

    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_result = await db.execute(
        select(func.count(ApiErrorLog.id)).where(ApiErrorLog.created_at >= today_start)
    )
    errors_today = today_result.scalar() or 0

    by_api_result = await db.execute(
        select(ApiErrorLog.api_name, func.count(ApiErrorLog.id))
        .group_by(ApiErrorLog.api_name)
    )
    errors_by_api = {row[0]: row[1] for row in by_api_result.all()}

    return ErrorStatsResponse(
        total_errors=total_errors,
        errors_today=errors_today,
        errors_by_api=errors_by_api,
    )


@router.delete("/errors/cleanup")
async def cleanup_old_errors(
    db: AsyncSession = Depends(get_postgres_session),
    _admin=Depends(get_current_admin_user),
):
    """Delete error logs older than 30 days."""
    cutoff = datetime.utcnow() - timedelta(days=CLEANUP_DAYS)
    result = await db.execute(
        delete(ApiErrorLog).where(ApiErrorLog.created_at < cutoff)
    )
    await db.commit()
    return {"deleted": result.rowcount}
