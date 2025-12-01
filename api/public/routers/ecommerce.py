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
from api.common.database import get_postgres_session, SQLITE_PATH
from api.common.models_postgres import User, Order, CartItem, OrderStatus, OrderType
from api.common.models_sqlite import InstantSSNPurchaseRequest, InstantSSNPurchaseResponse
from api.public.dependencies import get_current_user, limiter
from database.data_manager import DataManager
from api.services.enrichment_service import (
    perform_enrichment,
    ENRICHMENT_FAILURE_COST,
    ENRICHMENT_SUCCESS_COST
)

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

    # Validate SSN exists in SQLite
    data_manager = DataManager(db_path=SQLITE_PATH)

    result_dict = data_manager.get_record(purchase_request.table_name, purchase_request.ssn)
    if result_dict is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SSN record not found in {purchase_request.table_name}"
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

        return OrderResponse(
            id=str(new_order.id),
            total_price=new_order.total_price,
            status=new_order.status.value,
            order_type=new_order.order_type.value,
            created_at=new_order.created_at.isoformat(),
            items_count=len(order_items)
        )

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


# Enrichment + purchase endpoints
@router.post("/orders/instant-purchase-with-enrichment", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def instant_purchase_with_enrichment(
    purchase_request: InstantPurchaseRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_postgres_session)
):
    """
    Instantly purchase a single SSN record with mandatory enrichment attempt.

    Two-tier pricing for enrichment:
    - $1.00 if enrichment fails (no changes found)
    - $1.50 if enrichment succeeds (data updated)

    Price is determined by enrichment result (not from request).

    Args:
        purchase_request: Purchase details (SSN, table name)
        current_user: Current authenticated user
        db: PostgreSQL database session

    Returns:
        Created order with enrichment metadata

    Raises:
        HTTPException: If SSN not found or insufficient balance for enrichment
    """
    # Pre-check: ensure balance for enrichment (minimum cost)
    if current_user.balance < ENRICHMENT_FAILURE_COST:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Insufficient balance. Required: ${ENRICHMENT_FAILURE_COST}, Available: ${current_user.balance}"
        )

    # Validate SSN exists in SQLite
    data_manager = DataManager(db_path=SQLITE_PATH)
    current_record = data_manager.get_record(purchase_request.table_name, purchase_request.ssn)

    if current_record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SSN record not found in {purchase_request.table_name}"
        )

    # Perform enrichment using centralized service (charges and commits independently)
    enrichment_result = await perform_enrichment(
        user=current_user,
        table_name=purchase_request.table_name,
        ssn=purchase_request.ssn,
        db_session=db,
        data_manager=data_manager
    )

    # If enrichment failed with error, raise exception
    if enrichment_result.error and not enrichment_result.success:
        logger.error(f"Enrichment failed: {enrichment_result.error}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Enrichment failed: {enrichment_result.error}"
        )

    # NEW PRICING: Price is the enrichment cost (success/failure determines price)
    item_price = enrichment_result.cost
    total_price = item_price

    # Load updated record from SQLite after enrichment
    updated_record = data_manager.get_record(purchase_request.table_name, purchase_request.ssn)

    # Prepare order item with enrichment metadata AND full record data
    order_items = [
        {
            "ssn": purchase_request.ssn,
            "source_table": purchase_request.table_name,
            "ssn_record_id": f"{purchase_request.table_name}:{purchase_request.ssn}",
            "price": str(item_price),
            "source": "instant_purchase_enrichment",
            # Personal info from updated record
            "firstname": updated_record.get('firstname') if updated_record else None,
            "lastname": updated_record.get('lastname') if updated_record else None,
            "middlename": updated_record.get('middlename') if updated_record else None,
            "dob": updated_record.get('dob') if updated_record else None,
            # Address info
            "address": updated_record.get('address') if updated_record else None,
            "city": updated_record.get('city') if updated_record else None,
            "state": updated_record.get('state') if updated_record else None,
            "zip": updated_record.get('zip') if updated_record else None,
            # Contact info
            "phone": updated_record.get('phone') if updated_record else None,
            "email": updated_record.get('email') if updated_record else None,
            # Enrichment metadata
            "enrichment_attempted": True,
            "enrichment_success": enrichment_result.success,
            "enrichment_cost": str(item_price),
            "enrichment_timestamp": enrichment_result.timestamp,
            "updated_fields": enrichment_result.updated_fields if enrichment_result.success else [],
            "purchased_at": datetime.utcnow().isoformat()
        }
    ]

    # Create order in transaction (balance already deducted by enrichment service)
    try:
        # Create order with total price = enrichment cost
        new_order = Order(
            user_id=current_user.id,
            items=order_items,
            total_price=total_price,
            status=OrderStatus.completed,
            order_type=determine_order_type(purchase_request.table_name),
            is_viewed=False
        )
        db.add(new_order)

        # Commit transaction
        await db.commit()
        await db.refresh(new_order)

        return OrderResponse(
            id=str(new_order.id),
            total_price=new_order.total_price,
            status=new_order.status.value,
            order_type=new_order.order_type.value,
            created_at=new_order.created_at.isoformat(),
            items_count=len(order_items)
        )

    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to create order after enrichment: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create order: {str(e)}"
        )


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

    # Load SSN details for items
    items_with_details = []
    data_manager = DataManager(db_path=SQLITE_PATH)

    for item in order.items:
        ssn = item.get('ssn')
        # Try to load SSN details
        ssn_details = None
        for table_name in ['ssn_1', 'ssn_2']:
            result_dict = data_manager.get_record(table_name, ssn)
            if result_dict is not None:
                ssn_details = result_dict
                break

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
