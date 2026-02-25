"""
Orders management router for Admin API.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, or_
from typing import Optional, Any
from pydantic import BaseModel
from decimal import Decimal
from datetime import datetime

from api.common.database import get_postgres_session
from api.admin.dependencies import get_current_admin_user
from api.common.models_postgres import User, Order, OrderStatus, OrderType, TestSearchHistory

router = APIRouter(tags=["Admin Orders"])


# Pydantic models
class OrderResponse(BaseModel):
    """Order response model."""
    id: str
    user_id: str
    username: str
    items: Any  # JSON field
    total_price: Decimal
    status: str
    order_type: str
    is_viewed: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class OrderListResponse(BaseModel):
    """Order list response."""
    orders: list[OrderResponse]
    total_count: int
    page: int
    page_size: int


class FailedItemResponse(BaseModel):
    """Failed/not-found search entry."""
    id: str
    user_id: str
    username: str
    input_fullname: str
    input_address: str
    reason: str  # 'not_found' or 'api_error'
    error_message: Optional[str] = None
    search_time: Optional[float] = None
    created_at: datetime


class FailedListResponse(BaseModel):
    """Failed searches list."""
    items: list[FailedItemResponse]
    total_count: int
    page: int
    page_size: int


@router.get("/not-found", response_model=FailedListResponse)
async def get_failed_searches(
    reason_filter: Optional[str] = Query(None, description="Filter: 'not_found' or 'api_error'"),
    search: Optional[str] = Query(None, description="Search by username"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_postgres_session),
    current_user: User = Depends(get_current_admin_user)
):
    """
    Get failed searches: SSN not found (from test_search_history) and API errors (from instant_ssn_searches).
    """
    from api.common.models_postgres import InstantSSNSearch

    nf_items: list[FailedItemResponse] = []
    api_items: list[FailedItemResponse] = []
    nf_count = 0
    api_count = 0

    # Not Found searches (test_search_history where status='nf')
    if not reason_filter or reason_filter == 'not_found':
        nf_query = (
            select(TestSearchHistory, User.username)
            .join(User, TestSearchHistory.user_id == User.id)
            .where(TestSearchHistory.status == 'nf')
        )
        if search:
            nf_query = nf_query.where(User.username.ilike(f"%{search.strip()}%"))

        nf_count_q = select(func.count()).select_from(nf_query.subquery())
        nf_count = (await session.execute(nf_count_q)).scalar() or 0

        nf_query = nf_query.order_by(desc(TestSearchHistory.created_at)).limit(limit).offset(offset)
        result = await session.execute(nf_query)
        for entry, username in result.all():
            nf_items.append(FailedItemResponse(
                id=str(entry.id),
                user_id=str(entry.user_id),
                username=username,
                input_fullname=entry.input_fullname,
                input_address=entry.input_address,
                reason='not_found',
                search_time=entry.search_time,
                created_at=entry.created_at
            ))

    # API error searches (instant_ssn_searches where success=false and error_message is set)
    if not reason_filter or reason_filter == 'api_error':
        api_query = (
            select(InstantSSNSearch, User.username)
            .join(User, InstantSSNSearch.user_id == User.id)
            .where(InstantSSNSearch.success == False)
            .where(InstantSSNSearch.error_message.isnot(None))
            .where(InstantSSNSearch.error_message != "No SSN matches found in local database")
            .where(InstantSSNSearch.error_message != "No SSN found — sent to worker")
            .where(InstantSSNSearch.error_message != "No SSN found — no manual fallback")
        )
        if search:
            api_query = api_query.where(User.username.ilike(f"%{search.strip()}%"))

        api_count_q = select(func.count()).select_from(api_query.subquery())
        api_count = (await session.execute(api_count_q)).scalar() or 0

        api_query = api_query.order_by(desc(InstantSSNSearch.created_at)).limit(limit).offset(offset)
        result = await session.execute(api_query)
        for entry, username in result.all():
            params = entry.search_params or {}
            api_items.append(FailedItemResponse(
                id=str(entry.id),
                user_id=str(entry.user_id),
                username=username,
                input_fullname=f"{params.get('firstname', '')} {params.get('lastname', '')}".strip(),
                input_address=params.get('address', ''),
                reason='api_error',
                error_message=entry.error_message,
                created_at=entry.created_at
            ))

    # Combine and sort by date
    if reason_filter == 'not_found':
        all_items = nf_items
        total = nf_count
    elif reason_filter == 'api_error':
        all_items = api_items
        total = api_count
    else:
        all_items = sorted(nf_items + api_items, key=lambda x: x.created_at, reverse=True)[:limit]
        total = nf_count + api_count

    return FailedListResponse(
        items=all_items,
        total_count=total,
        page=offset // limit + 1 if limit > 0 else 1,
        page_size=limit
    )


@router.get("/", response_model=OrderListResponse)
async def get_orders(
    status_filter: Optional[str] = Query(None, description="Filter by status (pending, completed, failed, cancelled)"),
    type_filter: Optional[str] = Query(None, description="Filter by order type (instant_ssn, manual_ssn)"),
    search: Optional[str] = Query(None, description="Search by username"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_postgres_session),
    current_user: User = Depends(get_current_admin_user)
):
    """
    Get all orders with optional filtering.

    Admin only endpoint for viewing all orders in the system.
    """
    # Build query
    query = (
        select(Order, User.username)
        .join(User, Order.user_id == User.id)
    )

    # Apply status filter if provided
    if status_filter:
        try:
            status = OrderStatus(status_filter)
            query = query.where(Order.status == status)
        except ValueError:
            pass  # Invalid status, ignore filter
    else:
        # Exclude cancelled orders by default
        query = query.where(Order.status != OrderStatus.cancelled)

    # Apply type filter if provided
    if type_filter:
        try:
            order_type = OrderType(type_filter)
            query = query.where(Order.order_type == order_type)
        except ValueError:
            pass  # Invalid type, ignore filter

    # Apply username search if provided
    if search:
        search_term = f"%{search.strip()}%"
        query = query.where(User.username.ilike(search_term))

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await session.execute(count_query)
    total_count = total_result.scalar() or 0

    # Apply pagination and ordering
    query = query.order_by(desc(Order.created_at)).limit(limit).offset(offset)

    # Execute query
    result = await session.execute(query)
    rows = result.all()

    # Format response
    orders = []
    for order, username in rows:
        orders.append(OrderResponse(
            id=str(order.id),
            user_id=str(order.user_id),
            username=username,
            items=order.items,
            total_price=order.total_price,
            status=order.status.value,
            order_type=order.order_type.value if order.order_type else '',
            is_viewed=order.is_viewed,
            created_at=order.created_at,
            updated_at=order.updated_at
        ))

    return OrderListResponse(
        orders=orders,
        total_count=total_count,
        page=offset // limit + 1 if limit > 0 else 1,
        page_size=limit
    )


@router.get("/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: str,
    session: AsyncSession = Depends(get_postgres_session),
    current_user: User = Depends(get_current_admin_user)
):
    """
    Get order by ID.

    Admin only endpoint for viewing order details.
    """
    from uuid import UUID

    query = (
        select(Order, User.username)
        .join(User, Order.user_id == User.id)
        .where(Order.id == UUID(order_id))
    )

    result = await session.execute(query)
    row = result.first()

    if not row:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Order not found")

    order, username = row

    return OrderResponse(
        id=str(order.id),
        user_id=str(order.user_id),
        username=username,
        items=order.items,
        total_price=order.total_price,
        status=order.status.value,
        order_type=order.order_type.value if order.order_type else '',
        is_viewed=order.is_viewed,
        created_at=order.created_at,
        updated_at=order.updated_at
    )


@router.patch("/{order_id}/status")
async def update_order_status(
    order_id: str,
    status: OrderStatus,
    session: AsyncSession = Depends(get_postgres_session),
    current_user: User = Depends(get_current_admin_user)
):
    """
    Update order status.

    Admin only endpoint for changing order status.
    """
    from uuid import UUID

    query = select(Order).where(Order.id == UUID(order_id))
    result = await session.execute(query)
    order = result.scalar_one_or_none()

    if not order:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Order not found")

    order.status = status
    await session.commit()

    return {"message": "Order status updated successfully", "order_id": order_id, "new_status": status.value}
