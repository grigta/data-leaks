"""
Orders management router for Admin API.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
from typing import Optional, Any
from pydantic import BaseModel
from decimal import Decimal
from datetime import datetime

from api.common.database import get_postgres_session
from api.admin.dependencies import get_current_admin_user
from api.common.models_postgres import User, Order, OrderStatus

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


@router.get("/", response_model=OrderListResponse)
async def get_orders(
    status_filter: Optional[str] = Query(None, description="Filter by status (pending, completed, failed, cancelled)"),
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
