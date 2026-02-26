"""
E-commerce router for Public API (cart and orders).
"""
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, update
from typing import List, Optional, Any
from decimal import Decimal
from uuid import UUID
import json
import logging
from datetime import datetime
from pydantic import BaseModel
from api.common.database import get_postgres_session
from api.common.models_postgres import User, Order, CartItem, OrderStatus, OrderType
from api.common.models_sqlite import InstantSSNPurchaseRequest, InstantSSNPurchaseResponse
from api.public.dependencies import get_current_user, limiter
from database.search_engine_factory import get_search_engine
from api.public.websocket import publish_user_notification, WebSocketEventType

logger = logging.getLogger(__name__)


router = APIRouter()


def determine_order_type(table_name: str) -> OrderType:
    """
    Determine order type based on table name.

    Args:
        table_name: SQLite table name (e.g., 'ssn_1', 'ssn_2', 'instant_ssn', 'reverse_ssn')

    Returns:
        OrderType enum value
    """
    table_lower = table_name.lower()

    # Instant SSN tables
    if table_lower in ('ssn_1', 'instant_ssn', 'instant'):
        return OrderType.instant_ssn

    # Reverse SSN tables (deprecated but kept for compatibility)
    elif table_lower in ('ssn_2', 'reverse_ssn', 'reverse'):
        return OrderType.reverse_ssn

    # Manual SSN tables
    elif table_lower in ('manual_ssn', 'manual'):
        return OrderType.manual_ssn

    # Default to instant_ssn for unknown tables
    else:
        logger.warning(f"Unknown table name '{table_name}', defaulting to instant_ssn order type")
        return OrderType.instant_ssn


# Pydantic models
class OrderResponse(BaseModel):
    """Response model for order."""
    id: str
    total_price: Decimal
    status: str
    order_type: str
    created_at: str
    items_count: int

    class Config:
        from_attributes = True


class OrderDetailResponse(BaseModel):
    """Response model for order details."""
    id: str
    total_price: Decimal
    status: str
    created_at: str
    items: List[dict]


class InstantPurchaseRequest(BaseModel):
    """Request model for instant purchase."""
    ssn: str
    table_name: str
    price: Optional[Decimal] = None


# Order endpoints
# @limiter.limit("100/hour")
@router.get("/orders", response_model=List[OrderResponse])
async def get_orders(
    request: Request,
    response: Response,
    status_filter: Optional[str] = None,
    type_filter: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_postgres_session)
):
    """
    Get user's orders.

    Args:
        status_filter: Filter by order status
        type_filter: Filter by order type (reverse_ssn, instant_ssn, manual_ssn)
        limit: Maximum number of orders to return
        offset: Number of orders to skip
        current_user: Current authenticated user
        db: PostgreSQL database session

    Returns:
        List of orders
    """
    # Build query
    query = select(Order).where(Order.user_id == current_user.id)

    # Apply status filter
    if status_filter:
        try:
            status_enum = OrderStatus(status_filter)
            query = query.where(Order.status == status_enum)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status: {status_filter}"
            )

    # Apply order type filter
    if type_filter:
        try:
            type_enum = OrderType(type_filter)
            query = query.where(Order.order_type == type_enum)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid type: {type_filter}. Must be one of: reverse_ssn, instant_ssn, manual_ssn"
            )

    # Apply ordering and pagination
    query = query.order_by(Order.created_at.desc()).offset(offset).limit(limit)

    # Execute query
    result = await db.execute(query)
    orders = result.scalars().all()

    return [
        OrderResponse(
            id=str(order.id),
            total_price=order.total_price,
            status=order.status.value,
            order_type=order.order_type.value,
            created_at=order.created_at.isoformat(),
            items_count=len(order.items)
        )
        for order in orders
    ]


# @limiter.limit("10/hour")
@router.post("/orders/instant-purchase", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def instant_purchase(
    purchase_request: InstantPurchaseRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_postgres_session)
):
    """
    Instantly purchase a single SSN record without adding to cart.

    Args:
        purchase_request: Purchase details (SSN, table name, price)
        current_user: Current authenticated user
        db: PostgreSQL database session

    Returns:
        Created order

    Raises:
        HTTPException: If SSN not found or insufficient balance
    """
    # Validate price is provided for instant purchase
    if purchase_request.price is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Price is required for instant purchase. Use /orders/instant-purchase-with-enrichment for enrichment-based pricing."
        )

    # Validate SSN exists in ClickHouse
    search_engine = get_search_engine()
    results_json = search_engine.search_by_ssn(purchase_request.ssn, limit=1)
    results = json.loads(results_json)

    if not results:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SSN record not found"
        )

    # Check balance
    if current_user.balance < purchase_request.price:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Insufficient balance. Required: ${purchase_request.price}, Available: ${current_user.balance}"
        )

    # Prepare order item
    order_items = [
        {
            "ssn": purchase_request.ssn,
            "ssn_record_id": f"{purchase_request.table_name}:{purchase_request.ssn}",
            "price": str(purchase_request.price)
        }
    ]

    # Create order in atomic transaction
    try:
        # Deduct balance
        current_user.balance -= purchase_request.price

        # Create order
        new_order = Order(
            user_id=current_user.id,
            items=order_items,
            total_price=purchase_request.price,
            status=OrderStatus.completed,
            order_type=determine_order_type(purchase_request.table_name),
            is_viewed=False  # Explicitly set as unviewed
        )
        db.add(new_order)

        # Commit transaction
        await db.commit()
        await db.refresh(new_order)
        await db.refresh(current_user)

        # Notify about balance change via WebSocket
        await publish_user_notification(
            str(current_user.id),
            WebSocketEventType.BALANCE_UPDATED,
            {"user_id": str(current_user.id), "new_balance": float(current_user.balance)}
        )

        return OrderResponse(
            id=str(new_order.id),
            total_price=new_order.total_price,
            status=new_order.status.value,
            order_type=new_order.order_type.value,
            created_at=new_order.created_at.isoformat(),
            items_count=len(order_items)
        )

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create order: {str(e)}"
        )


@router.get("/orders/unviewed-count", response_model=dict)
async def get_unviewed_orders_count(
    session: AsyncSession = Depends(get_postgres_session),
    current_user: User = Depends(get_current_user)
):
    """
    Get count of unviewed orders for the current user.
    """
    from sqlalchemy import func, select

    # Count unviewed orders
    count_query = select(func.count()).select_from(Order).where(
        Order.user_id == current_user.id,
        Order.is_viewed == False
    )

    result = await session.execute(count_query)
    count = result.scalar() or 0

    return {"count": count}


@router.post("/orders/mark-viewed", response_model=dict)
async def mark_orders_as_viewed(
    session: AsyncSession = Depends(get_postgres_session),
    current_user: User = Depends(get_current_user)
):
    """
    Mark all orders as viewed for the current user.
    """
    from sqlalchemy import update

    # Update all unviewed orders for the current user
    update_query = (
        update(Order)
        .where(
            Order.user_id == current_user.id,
            Order.is_viewed == False
        )
        .values(is_viewed=True)
    )

    result = await session.execute(update_query)
    await session.commit()

    updated_count = result.rowcount

    return {"success": True, "updated_count": updated_count}


@router.get("/orders/{order_id}", response_model=OrderDetailResponse)
async def get_order(
    request: Request,
    response: Response,
    order_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_postgres_session)
):
    """
    Get order details.

    Args:
        order_id: Order ID
        current_user: Current authenticated user
        db: PostgreSQL database session

    Returns:
        Order details with SSN records

    Raises:
        HTTPException: If order not found or doesn't belong to user
    """
    # Find order
    result = await db.execute(
        select(Order).where(
            Order.id == order_id,
            Order.user_id == current_user.id
        )
    )
    order = result.scalar_one_or_none()

    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found"
        )

    # Load SSN details for items from ClickHouse
    items_with_details = []
    search_engine = get_search_engine()

    for item in order.items:
        ssn = item.get('ssn')
        # Load SSN details from ClickHouse
        ssn_details = None
        if ssn:
            results_json = search_engine.search_by_ssn(ssn, limit=1)
            results = json.loads(results_json)
            if results:
                ssn_details = results[0]

        items_with_details.append({
            **item,
            'ssn_details': ssn_details
        })

    return OrderDetailResponse(
        id=str(order.id),
        total_price=order.total_price,
        status=order.status.value,
        created_at=order.created_at.isoformat(),
        items=items_with_details
    )
