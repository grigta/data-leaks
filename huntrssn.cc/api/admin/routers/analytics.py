"""
Admin analytics router.
Provides comprehensive statistics and analytics for admin panel.
"""

import logging
import os
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, case, cast, func, or_, select, Numeric, String
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.asyncio import AsyncSession

from api.admin.dependencies import get_current_admin_user
from api.common.database import get_postgres_session
from api.common.models_postgres import (
    Coupon,
    Order,
    OrderStatus,
    Transaction,
    TransactionStatus,
    User,
    UserCoupon,
    InstantSSNSearch,
    ManualSSNTicket,
    TicketStatus,
    RequestSource,
)

router = APIRouter()

# Initialize logger
logger = logging.getLogger(__name__)

# Read configuration from environment
ANALYTICS_CACHE_DURATION = int(os.getenv("ANALYTICS_CACHE_DURATION", "60"))
ANALYTICS_MAX_PAGE_SIZE = int(os.getenv("ANALYTICS_MAX_PAGE_SIZE", "100"))


# ============================================
# Pydantic Response Models
# ============================================


class UserStatsResponse(BaseModel):
    """User growth statistics."""

    total_users: int = Field(..., description="Total number of registered users")
    new_users_1_day: int = Field(..., description="New users in last 1 day")
    new_users_30_days: int = Field(..., description="New users in last 30 days")
    new_users_all_time: int = Field(..., description="All time new users (same as total)")


class FinancialStatsResponse(BaseModel):
    """Financial statistics overview."""

    total_deposited: Decimal = Field(..., description="Total amount deposited by all users")
    total_spent: Decimal = Field(..., description="Total amount spent on orders")
    usage_percentage: float = Field(..., description="Percentage of deposited funds spent")
    usage_amount: Decimal = Field(..., description="Total usage amount (same as total_spent)")


class TransactionStatsResponse(BaseModel):
    """Transaction statistics by status."""

    total_transactions: int = Field(..., description="Total number of transactions")
    pending: int = Field(..., description="Pending transactions")
    paid: int = Field(..., description="Paid transactions")
    expired: int = Field(..., description="Expired transactions")
    failed: int = Field(..., description="Failed transactions")


class ProductStatsResponse(BaseModel):
    """Product/order statistics."""

    total_orders: int = Field(..., description="Total completed orders")
    instant_ssn_purchases: int = Field(..., description="Single-item orders (instant purchases)")
    cart_purchases: int = Field(..., description="Multi-item orders (cart purchases)")
    reverse_ssn_purchases: int = Field(..., description="Reverse SSN lookup purchases")
    enrichment_operations: int = Field(
        0, description="Enrichment operations (currently untracked)"
    )
    note: str = Field(
        default="Enrichment operations are not tracked in orders - they deduct balance directly. Reverse SSN tracking added as of 2025-11-08.",
        description="Important limitation note",
    )


class CouponUsageStats(BaseModel):
    """Coupon usage statistics."""

    coupon_code: str = Field(..., description="Coupon code")
    bonus_percent: int = Field(..., description="Bonus percentage")
    times_used: int = Field(..., description="Number of times coupon was applied")
    total_bonus_given: Decimal = Field(..., description="Total bonus amount given")


class UserTableItem(BaseModel):
    """Single user item in the table."""

    id: str = Field(..., description="User ID")
    username: str = Field(..., description="Username")
    balance: float = Field(..., description="Current balance")
    total_spent: float = Field(..., description="Total amount spent")
    total_deposited: float = Field(..., description="Total amount deposited")
    applied_coupons: List[str] = Field(default_factory=list, description="Applied coupon codes")
    created_at: str = Field(..., description="Account creation date (ISO format)")
    is_banned: bool = Field(default=False, description="Whether user is banned")

    class Config:
        json_encoders = {
            Decimal: lambda v: float(v) if v is not None else None
        }


class UserTableResponse(BaseModel):
    """Paginated user table response."""

    users: List[UserTableItem] = Field(..., description="List of users")
    total_count: int = Field(..., description="Total number of users")
    page: int = Field(..., description="Current page number (0-indexed)")
    page_size: int = Field(..., description="Number of items per page")


class UserOrderDetail(BaseModel):
    """Order details for user analytics."""

    order_id: str
    total_price: float
    status: str
    items_count: int
    created_at: str

    class Config:
        json_encoders = {
            Decimal: lambda v: float(v) if v is not None else None
        }


class UserTransactionDetail(BaseModel):
    """Transaction details for user analytics."""

    transaction_id: str
    amount: float
    status: str
    created_at: str

    class Config:
        json_encoders = {
            Decimal: lambda v: float(v) if v is not None else None
        }


class UserDetailsResponse(BaseModel):
    """Detailed user analytics."""

    user_id: str
    username: str
    email: str
    balance: float
    created_at: str
    total_orders: int
    total_spent: float
    total_deposited: float
    applied_coupons: List[dict]

    class Config:
        json_encoders = {
            Decimal: lambda v: float(v) if v is not None else None
        }
    recent_orders: List[UserOrderDetail]
    recent_transactions: List[UserTransactionDetail]


class InstantSSNStatsResponse(BaseModel):
    """Instant SSN search statistics."""

    total_attempts: int = Field(..., description="Total search attempts")
    successful_searches: int = Field(..., description="Searches where user was charged")
    failed_searches: int = Field(..., description="Searches where user was NOT charged")
    success_rate: float = Field(..., description="Success rate percentage")
    failure_rate: float = Field(..., description="Failure rate percentage")
    total_revenue: Decimal = Field(..., description="Total revenue from successful searches")
    total_api_cost: Decimal = Field(..., description="Total API cost")
    net_profit: Decimal = Field(..., description="Net profit (revenue - api_cost)")
    profit_per_search: Decimal = Field(..., description="Average profit per successful search")
    period: str = Field(..., description="Time period filter")
    telegram_total_attempts: int = Field(..., description="Total attempts via Telegram")
    telegram_successful: int = Field(..., description="Successful attempts via Telegram")
    telegram_failed: int = Field(..., description="Failed attempts via Telegram")
    telegram_success_rate: float = Field(..., description="Success rate percentage via Telegram")


class ManualSSNStatsResponse(BaseModel):
    """Manual SSN ticket statistics."""

    total_attempts: int = Field(..., description="Total ticket attempts")
    successful_searches: int = Field(..., description="Completed tickets")
    failed_searches: int = Field(..., description="Rejected tickets")
    pending_tickets: int = Field(..., description="Pending tickets")
    processing_tickets: int = Field(..., description="Processing tickets")
    success_rate: float = Field(..., description="Success rate percentage")
    failure_rate: float = Field(..., description="Failure rate percentage")
    total_revenue: Decimal = Field(..., description="Total revenue from completed tickets")
    processing_cost: Decimal = Field(..., description="Processing cost (manual work)")
    net_profit: Decimal = Field(..., description="Net profit (revenue - processing_cost)")
    profit_per_search: Decimal = Field(..., description="Average profit per successful search")
    avg_response_time: Optional[float] = Field(None, description="Average response time in minutes")
    period: str = Field(..., description="Time period filter")
    telegram_total_attempts: int = Field(..., description="Total attempts via Telegram")
    telegram_successful: int = Field(..., description="Successful attempts via Telegram")
    telegram_failed: int = Field(..., description="Failed attempts via Telegram")
    telegram_success_rate: float = Field(..., description="Success rate percentage via Telegram")


# ============================================
# Analytics Endpoints
# ============================================


@router.get("/stats/users", response_model=UserStatsResponse)
async def get_user_statistics(
    response: Response,
    db: AsyncSession = Depends(get_postgres_session),
    _admin: User = Depends(get_current_admin_user),
):
    """
    Get user growth statistics.
    Requires admin authentication.
    """
    # Set cache headers
    if ANALYTICS_CACHE_DURATION > 0:
        response.headers["Cache-Control"] = f"max-age={ANALYTICS_CACHE_DURATION}, public"
    try:
        # Total users
        total_users_query = select(func.count()).select_from(User)
        total_users_result = await db.execute(total_users_query)
        total_users = total_users_result.scalar() or 0

        # New users in last 1 day (using DB-side interval)
        new_1_day_query = select(func.count()).select_from(User).where(
            User.created_at >= func.now() - func.make_interval(0, 0, 0, 1)
        )
        new_1_day_result = await db.execute(new_1_day_query)
        new_users_1_day = new_1_day_result.scalar() or 0

        # New users in last 30 days (using DB-side interval)
        new_30_days_query = select(func.count()).select_from(User).where(
            User.created_at >= func.now() - func.make_interval(0, 0, 0, 30)
        )
        new_30_days_result = await db.execute(new_30_days_query)
        new_users_30_days = new_30_days_result.scalar() or 0

        return UserStatsResponse(
            total_users=total_users,
            new_users_1_day=new_users_1_day,
            new_users_30_days=new_users_30_days,
            new_users_all_time=total_users,
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve user statistics: {str(e)}",
        )


@router.get("/stats/financial", response_model=FinancialStatsResponse)
async def get_financial_statistics(
    response: Response,
    db: AsyncSession = Depends(get_postgres_session),
    _admin: User = Depends(get_current_admin_user),
):
    """
    Get financial statistics overview.
    Requires admin authentication.
    """
    # Set cache headers
    if ANALYTICS_CACHE_DURATION > 0:
        response.headers["Cache-Control"] = f"max-age={ANALYTICS_CACHE_DURATION}, public"
    try:
        # Total deposited (paid transactions)
        deposited_query = select(func.coalesce(func.sum(Transaction.amount), 0)).where(
            Transaction.status == TransactionStatus.paid
        )
        deposited_result = await db.execute(deposited_query)
        total_deposited = deposited_result.scalar() or Decimal("0.00")

        # Total spent (completed orders)
        spent_query = select(func.coalesce(func.sum(Order.total_price), 0)).where(
            Order.status == OrderStatus.completed
        )
        spent_result = await db.execute(spent_query)
        total_spent = spent_result.scalar() or Decimal("0.00")

        # Calculate usage percentage
        if total_deposited > 0:
            usage_percentage = float((total_spent / total_deposited) * 100)
        else:
            usage_percentage = 0.0

        return FinancialStatsResponse(
            total_deposited=total_deposited,
            total_spent=total_spent,
            usage_percentage=round(usage_percentage, 2),
            usage_amount=total_spent,
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve financial statistics: {str(e)}",
        )


@router.get("/stats/transactions", response_model=TransactionStatsResponse)
async def get_transaction_statistics(
    response: Response,
    db: AsyncSession = Depends(get_postgres_session),
    _admin: User = Depends(get_current_admin_user),
):
    """
    Get transaction statistics by status.
    Requires admin authentication.
    """
    # Set cache headers
    if ANALYTICS_CACHE_DURATION > 0:
        response.headers["Cache-Control"] = f"max-age={ANALYTICS_CACHE_DURATION}, public"
    try:
        # Count transactions by status in a single aggregating query
        status_counts_query = select(
            func.count().label("total"),
            func.sum(
                case((Transaction.status == TransactionStatus.pending, 1), else_=0)
            ).label("pending"),
            func.sum(
                case((Transaction.status == TransactionStatus.paid, 1), else_=0)
            ).label("paid"),
            func.sum(
                case((Transaction.status == TransactionStatus.expired, 1), else_=0)
            ).label("expired"),
            func.sum(
                case((Transaction.status == TransactionStatus.failed, 1), else_=0)
            ).label("failed"),
        ).select_from(Transaction)

        result = await db.execute(status_counts_query)
        row = result.one()

        return TransactionStatsResponse(
            total_transactions=row.total or 0,
            pending=row.pending or 0,
            paid=row.paid or 0,
            expired=row.expired or 0,
            failed=row.failed or 0,
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve transaction statistics: {str(e)}",
        )


@router.get("/stats/products", response_model=ProductStatsResponse)
async def get_product_statistics(
    response: Response,
    db: AsyncSession = Depends(get_postgres_session),
    _admin: User = Depends(get_current_admin_user),
):
    """
    Get product/order statistics.
    Requires admin authentication.

    Note: Enrichment operations are not tracked in the Order table.
    """
    # Set cache headers
    if ANALYTICS_CACHE_DURATION > 0:
        response.headers["Cache-Control"] = f"max-age={ANALYTICS_CACHE_DURATION}, public"
    try:
        # Total completed orders
        total_query = select(func.count()).select_from(Order).where(Order.status == OrderStatus.completed)
        total_result = await db.execute(total_query)
        total_orders = total_result.scalar() or 0

        # Single item orders (instant purchases)
        instant_query = select(func.count()).select_from(Order).where(
            and_(Order.status == OrderStatus.completed, func.json_array_length(Order.items) == 1)
        )
        instant_result = await db.execute(instant_query)
        instant_ssn = instant_result.scalar() or 0

        # Multi-item orders (cart purchases) - exclude reverse_ssn orders to avoid overlap
        cart_query = select(func.count()).select_from(Order).where(
            and_(
                Order.status == OrderStatus.completed,
                func.json_array_length(Order.items) > 1,
                ~cast(Order.items, postgresql.JSONB).op('@>')(cast('[{"source": "reverse_ssn"}]', postgresql.JSONB))
            )
        )
        cart_result = await db.execute(cart_query)
        cart_purchases = cart_result.scalar() or 0

        # Reverse SSN purchases (orders with source="reverse_ssn")
        reverse_ssn_query = select(func.count()).select_from(Order).where(
            and_(
                Order.status == OrderStatus.completed,
                cast(Order.items, postgresql.JSONB).op('@>')(cast('[{"source": "reverse_ssn"}]', postgresql.JSONB))
            )
        )
        reverse_ssn_result = await db.execute(reverse_ssn_query)
        reverse_ssn_purchases = reverse_ssn_result.scalar() or 0

        return ProductStatsResponse(
            total_orders=total_orders,
            instant_ssn_purchases=instant_ssn,
            cart_purchases=cart_purchases,
            reverse_ssn_purchases=reverse_ssn_purchases,
            enrichment_operations=0,
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve product statistics: {str(e)}",
        )


@router.get("/stats/coupons", response_model=List[CouponUsageStats])
async def get_coupon_statistics(
    response: Response,
    db: AsyncSession = Depends(get_postgres_session),
    _admin: User = Depends(get_current_admin_user),
):
    """
    Get coupon usage statistics.
    Requires admin authentication.
    """
    # Set cache headers
    if ANALYTICS_CACHE_DURATION > 0:
        response.headers["Cache-Control"] = f"max-age={ANALYTICS_CACHE_DURATION}, public"
    try:
        # Query all coupons with usage counts and total bonus given from paid transactions
        coupon_query = (
            select(
                Coupon.code,
                Coupon.bonus_percent,
                func.count(UserCoupon.user_id).label("times_used"),
                func.coalesce(
                    func.sum(
                        cast(
                            Transaction.payment_metadata['coupon_bonus_amount'].astext,
                            Numeric(10, 2)
                        )
                    ),
                    Decimal("0.00")
                ).label("total_bonus_given")
            )
            .outerjoin(UserCoupon, Coupon.id == UserCoupon.coupon_id)
            .outerjoin(
                Transaction,
                and_(
                    Transaction.status == TransactionStatus.paid,
                    Transaction.payment_metadata['coupon_code'].astext == Coupon.code
                )
            )
            .group_by(Coupon.id, Coupon.code, Coupon.bonus_percent)
        )

        coupon_result = await db.execute(coupon_query)
        coupons_data = coupon_result.all()

        stats = []
        for code, bonus_percent, times_used, total_bonus_given in coupons_data:
            stats.append(
                CouponUsageStats(
                    coupon_code=code,
                    bonus_percent=bonus_percent,
                    times_used=times_used,
                    total_bonus_given=total_bonus_given,
                )
            )

        return stats

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve coupon statistics: {str(e)}",
        )


@router.get("/users/table", response_model=UserTableResponse)
async def get_users_table(
    limit: int = Query(default=50, ge=1, description="Items per page"),
    offset: int = Query(default=0, ge=0, description="Offset for pagination"),
    search: Optional[str] = Query(default=None, description="Search by username or email"),
    sort_by: Optional[str] = Query(
        default="created_at", description="Sort field (username, balance, total_spent, created_at)"
    ),
    sort_order: Optional[str] = Query(default="desc", description="Sort order (asc, desc)"),
    coupon_code: Optional[str] = Query(default=None, description="Filter by applied coupon code"),
    db: AsyncSession = Depends(get_postgres_session),
    _admin: User = Depends(get_current_admin_user),
):
    """
    Get paginated user table with aggregations.
    Requires admin authentication.
    """
    # Validate limit against max page size
    if limit > ANALYTICS_MAX_PAGE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Limit exceeds maximum page size of {ANALYTICS_MAX_PAGE_SIZE}"
        )

    try:
        # Normalize coupon code input
        normalized_coupon = coupon_code.strip().upper() if coupon_code else None
        if normalized_coupon:
            logger.info(f"Filtering users by coupon code: {normalized_coupon}")

        # Build subqueries for aggregations
        spent_subq = (
            select(Order.user_id, func.sum(Order.total_price).label("total_spent"))
            .where(Order.status == OrderStatus.completed)
            .group_by(Order.user_id)
            .subquery()
        )

        deposited_subq = (
            select(Transaction.user_id, func.sum(Transaction.amount).label("total_deposited"))
            .where(Transaction.status == TransactionStatus.paid)
            .group_by(Transaction.user_id)
            .subquery()
        )

        coupons_subq = (
            select(UserCoupon.user_id, func.array_agg(Coupon.code).label("coupon_codes"))
            .join(Coupon, UserCoupon.coupon_id == Coupon.id)
            .group_by(UserCoupon.user_id)
            .subquery()
        )

        # Main query
        main_query = (
            select(
                User,
                func.coalesce(spent_subq.c.total_spent, 0).label("total_spent"),
                func.coalesce(deposited_subq.c.total_deposited, 0).label("total_deposited"),
                coupons_subq.c.coupon_codes,
            )
            .outerjoin(spent_subq, User.id == spent_subq.c.user_id)
            .outerjoin(deposited_subq, User.id == deposited_subq.c.user_id)
        )

        # Apply coupon filtering: use inner join when filtering, outer join otherwise
        if normalized_coupon:
            main_query = main_query.join(coupons_subq, User.id == coupons_subq.c.user_id)
            # Use PostgreSQL array containment operator with explicit array type
            coupon_array = cast(postgresql.array([normalized_coupon]), ARRAY(String))
            main_query = main_query.where(
                coupons_subq.c.coupon_codes.op('@>')(coupon_array)
            )
        else:
            main_query = main_query.outerjoin(coupons_subq, User.id == coupons_subq.c.user_id)

        # Apply search filter
        if search:
            main_query = main_query.where(
                or_(User.username.ilike(f"%{search}%"), User.email.ilike(f"%{search}%"))
            )

        # Apply sorting
        if sort_by == "username":
            sort_column = User.username
        elif sort_by == "balance":
            sort_column = User.balance
        elif sort_by == "total_spent":
            sort_column = func.coalesce(spent_subq.c.total_spent, 0)
        else:  # default to created_at
            sort_column = User.created_at

        if sort_order == "asc":
            main_query = main_query.order_by(sort_column.asc())
        else:
            main_query = main_query.order_by(sort_column.desc())

        # Get total count with same filters applied
        count_query = select(func.count()).select_from(User)

        # Apply coupon filtering to count query (use same expression as main query)
        if normalized_coupon:
            count_query = count_query.join(coupons_subq, User.id == coupons_subq.c.user_id)
            # Use PostgreSQL array containment operator with explicit array type
            coupon_array = cast(postgresql.array([normalized_coupon]), ARRAY(String))
            count_query = count_query.where(
                coupons_subq.c.coupon_codes.op('@>')(coupon_array)
            )

        # Apply search filter to count query
        if search:
            count_query = count_query.where(
                or_(User.username.ilike(f"%{search}%"), User.email.ilike(f"%{search}%"))
            )

        count_result = await db.execute(count_query)
        total_count = count_result.scalar() or 0

        # Apply pagination
        main_query = main_query.offset(offset).limit(limit)

        # Execute query
        result = await db.execute(main_query)
        rows = result.all()

        # Map to response model
        users = []
        for user, total_spent, total_deposited, coupon_codes in rows:
            users.append(
                UserTableItem(
                    id=str(user.id),
                    username=user.username,
                    balance=user.balance,
                    total_spent=total_spent,
                    total_deposited=total_deposited,
                    applied_coupons=coupon_codes or [],
                    created_at=user.created_at.isoformat(),
                    is_banned=user.is_banned,
                )
            )

        return UserTableResponse(
            users=users, total_count=total_count, page=offset // limit, page_size=limit
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve user table: {str(e)}",
        )


@router.get("/users/{user_id}/details", response_model=UserDetailsResponse)
async def get_user_details(
    user_id: UUID,
    db: AsyncSession = Depends(get_postgres_session),
    _admin: User = Depends(get_current_admin_user),
):
    """
    Get detailed analytics for a specific user.
    Requires admin authentication.
    """
    try:
        # Get user
        user_query = select(User).where(User.id == user_id)
        user_result = await db.execute(user_query)
        user = user_result.scalar_one_or_none()

        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        # Total orders
        total_orders_query = select(func.count()).select_from(Order).where(Order.user_id == user_id)
        total_orders_result = await db.execute(total_orders_query)
        total_orders = total_orders_result.scalar() or 0

        # Total spent
        total_spent_query = (
            select(func.coalesce(func.sum(Order.total_price), 0))
            .where(Order.user_id == user_id)
            .where(Order.status == OrderStatus.completed)
        )
        total_spent_result = await db.execute(total_spent_query)
        total_spent = total_spent_result.scalar() or Decimal("0.00")

        # Total deposited
        total_deposited_query = (
            select(func.coalesce(func.sum(Transaction.amount), 0))
            .where(Transaction.user_id == user_id)
            .where(Transaction.status == TransactionStatus.paid)
        )
        total_deposited_result = await db.execute(total_deposited_query)
        total_deposited = total_deposited_result.scalar() or Decimal("0.00")

        # Applied coupons
        coupons_query = (
            select(Coupon.code, UserCoupon.applied_at)
            .join(Coupon, UserCoupon.coupon_id == Coupon.id)
            .where(UserCoupon.user_id == user_id)
        )
        coupons_result = await db.execute(coupons_query)
        applied_coupons = [
            {"code": code, "applied_at": applied_at.isoformat()} for code, applied_at in coupons_result.all()
        ]

        # Recent orders (last 10)
        recent_orders_query = (
            select(Order).where(Order.user_id == user_id).order_by(Order.created_at.desc()).limit(10)
        )
        recent_orders_result = await db.execute(recent_orders_query)
        recent_orders_data = recent_orders_result.scalars().all()

        recent_orders = [
            UserOrderDetail(
                order_id=str(order.id),
                total_price=order.total_price,
                status=order.status.value,
                items_count=len(order.items) if order.items else 0,
                created_at=order.created_at.isoformat(),
            )
            for order in recent_orders_data
        ]

        # Recent transactions (last 10)
        recent_transactions_query = (
            select(Transaction)
            .where(Transaction.user_id == user_id)
            .order_by(Transaction.created_at.desc())
            .limit(10)
        )
        recent_transactions_result = await db.execute(recent_transactions_query)
        recent_transactions_data = recent_transactions_result.scalars().all()

        recent_transactions = [
            UserTransactionDetail(
                transaction_id=str(tx.id),
                amount=tx.amount,
                status=tx.status.value,
                created_at=tx.created_at.isoformat(),
            )
            for tx in recent_transactions_data
        ]

        return UserDetailsResponse(
            user_id=str(user.id),
            username=user.username,
            email=user.email,
            balance=user.balance,
            created_at=user.created_at.isoformat(),
            total_orders=total_orders,
            total_spent=total_spent,
            total_deposited=total_deposited,
            applied_coupons=applied_coupons,
            recent_orders=recent_orders,
            recent_transactions=recent_transactions,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve user details: {str(e)}",
        )


@router.get("/stats/instant-ssn", response_model=InstantSSNStatsResponse)
async def get_instant_ssn_stats(
    period: str = Query("all", regex="^(1d|7d|30d|all)$"),
    current_admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_postgres_session),
    response: Response = None,
):
    """
    Get Instant SSN search statistics.

    Args:
        period: Time period filter (1d, 7d, 30d, all)
        current_admin: Current authenticated admin user
        db: Database session
        response: HTTP response for cache headers

    Returns:
        InstantSSNStatsResponse with Instant SSN statistics
    """
    try:
        # Calculate time filter
        from datetime import datetime, timedelta
        time_filter = None
        if period == "1d":
            time_filter = datetime.utcnow() - timedelta(days=1)
        elif period == "7d":
            time_filter = datetime.utcnow() - timedelta(days=7)
        elif period == "30d":
            time_filter = datetime.utcnow() - timedelta(days=30)

        # Build base query with time filter
        base_conditions = []
        if time_filter:
            base_conditions.append(InstantSSNSearch.created_at >= time_filter)

        # Total attempts
        total_attempts_query = select(func.count()).select_from(InstantSSNSearch)
        if base_conditions:
            total_attempts_query = total_attempts_query.where(and_(*base_conditions))
        total_attempts_result = await db.execute(total_attempts_query)
        total_attempts = total_attempts_result.scalar() or 0

        # Successful searches (where user was charged)
        success_conditions = base_conditions + [InstantSSNSearch.success == True]
        successful_query = select(func.count()).select_from(InstantSSNSearch).where(and_(*success_conditions))
        successful_result = await db.execute(successful_query)
        successful_searches = successful_result.scalar() or 0

        # Failed searches
        failed_searches = total_attempts - successful_searches

        # Calculate rates
        success_rate = (successful_searches / total_attempts * 100) if total_attempts > 0 else 0.0
        failure_rate = (failed_searches / total_attempts * 100) if total_attempts > 0 else 0.0

        # Total revenue (sum of user_charged)
        revenue_query = select(func.sum(InstantSSNSearch.user_charged)).select_from(InstantSSNSearch)
        if base_conditions:
            revenue_query = revenue_query.where(and_(*base_conditions))
        revenue_result = await db.execute(revenue_query)
        total_revenue = revenue_result.scalar() or Decimal("0.00")

        # Total API cost (sum of api_cost)
        api_cost_query = select(func.sum(InstantSSNSearch.api_cost)).select_from(InstantSSNSearch)
        if base_conditions:
            api_cost_query = api_cost_query.where(and_(*base_conditions))
        api_cost_result = await db.execute(api_cost_query)
        total_api_cost = api_cost_result.scalar() or Decimal("0.00")

        # Net profit
        net_profit = total_revenue - total_api_cost

        # Profit per successful search
        profit_per_search = (net_profit / successful_searches) if successful_searches > 0 else Decimal("0.00")

        # Telegram statistics - total attempts via Telegram (filter by source)
        telegram_base_conditions = base_conditions + [InstantSSNSearch.source == RequestSource.telegram_bot]
        telegram_total_query = select(func.count()).select_from(InstantSSNSearch).where(and_(*telegram_base_conditions))
        telegram_total_result = await db.execute(telegram_total_query)
        telegram_total_attempts = telegram_total_result.scalar() or 0

        # Telegram successful searches
        telegram_success_conditions = telegram_base_conditions + [InstantSSNSearch.success == True]
        telegram_success_query = select(func.count()).select_from(InstantSSNSearch).where(and_(*telegram_success_conditions))
        telegram_success_result = await db.execute(telegram_success_query)
        telegram_successful = telegram_success_result.scalar() or 0

        # Telegram failed searches
        telegram_failed = telegram_total_attempts - telegram_successful

        # Telegram success rate
        telegram_success_rate = (telegram_successful / telegram_total_attempts * 100) if telegram_total_attempts > 0 else 0.0

        # Set cache headers
        if response:
            response.headers["Cache-Control"] = f"public, max-age={ANALYTICS_CACHE_DURATION}"

        return InstantSSNStatsResponse(
            total_attempts=total_attempts,
            successful_searches=successful_searches,
            failed_searches=failed_searches,
            success_rate=round(success_rate, 2),
            failure_rate=round(failure_rate, 2),
            total_revenue=total_revenue,
            total_api_cost=total_api_cost,
            net_profit=net_profit,
            profit_per_search=profit_per_search,
            period=period,
            telegram_total_attempts=telegram_total_attempts,
            telegram_successful=telegram_successful,
            telegram_failed=telegram_failed,
            telegram_success_rate=round(telegram_success_rate, 2)
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve Instant SSN statistics: {str(e)}",
        )


@router.get("/stats/manual-ssn", response_model=ManualSSNStatsResponse)
async def get_manual_ssn_stats(
    period: str = Query("all", regex="^(1d|yesterday|7d|30d|all)$"),
    current_admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_postgres_session),
    response: Response = None,
):
    """
    Get Manual SSN ticket statistics.

    Args:
        period: Time period filter (1d, yesterday, 7d, 30d, all)
        current_admin: Current authenticated admin user
        db: Database session
        response: HTTP response for cache headers

    Returns:
        ManualSSNStatsResponse with Manual SSN ticket statistics
    """
    try:
        from datetime import datetime, timedelta
        from api.common.pricing import MANUAL_SSN_PRICE

        # Calculate time filter
        time_filter = None
        time_filter_end = None
        if period == "1d":
            # Today (from start of today to now)
            now = datetime.utcnow()
            time_filter = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif period == "yesterday":
            # Yesterday (from start of yesterday to end of yesterday)
            now = datetime.utcnow()
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            time_filter = today_start - timedelta(days=1)
            time_filter_end = today_start
        elif period == "7d":
            time_filter = datetime.utcnow() - timedelta(days=7)
        elif period == "30d":
            time_filter = datetime.utcnow() - timedelta(days=30)

        # Build base query with time filter
        base_conditions = []
        if time_filter:
            base_conditions.append(ManualSSNTicket.created_at >= time_filter)
        if time_filter_end:
            base_conditions.append(ManualSSNTicket.created_at < time_filter_end)

        # Total attempts
        total_attempts_query = select(func.count()).select_from(ManualSSNTicket)
        if base_conditions:
            total_attempts_query = total_attempts_query.where(and_(*base_conditions))
        total_attempts_result = await db.execute(total_attempts_query)
        total_attempts = total_attempts_result.scalar() or 0

        # Successful searches (completed status)
        success_conditions = base_conditions + [ManualSSNTicket.status == TicketStatus.completed]
        successful_query = select(func.count()).select_from(ManualSSNTicket).where(and_(*success_conditions))
        successful_result = await db.execute(successful_query)
        successful_searches = successful_result.scalar() or 0

        # Failed searches (rejected status)
        failed_conditions = base_conditions + [ManualSSNTicket.status == TicketStatus.rejected]
        failed_query = select(func.count()).select_from(ManualSSNTicket).where(and_(*failed_conditions))
        failed_result = await db.execute(failed_query)
        failed_searches = failed_result.scalar() or 0

        # Pending tickets
        pending_conditions = base_conditions + [ManualSSNTicket.status == TicketStatus.pending]
        pending_query = select(func.count()).select_from(ManualSSNTicket).where(and_(*pending_conditions))
        pending_result = await db.execute(pending_query)
        pending_tickets = pending_result.scalar() or 0

        # Processing tickets
        processing_conditions = base_conditions + [ManualSSNTicket.status == TicketStatus.processing]
        processing_query = select(func.count()).select_from(ManualSSNTicket).where(and_(*processing_conditions))
        processing_result = await db.execute(processing_query)
        processing_tickets = processing_result.scalar() or 0

        # Calculate rates
        success_rate = (successful_searches / total_attempts * 100) if total_attempts > 0 else 0.0
        failure_rate = (failed_searches / total_attempts * 100) if total_attempts > 0 else 0.0

        # Total revenue (completed tickets × price)
        total_revenue = Decimal(str(successful_searches)) * MANUAL_SSN_PRICE

        # Processing cost (manual work = $0.00)
        processing_cost = Decimal("0.00")

        # Net profit
        net_profit = total_revenue - processing_cost

        # Profit per successful search
        profit_per_search = (net_profit / successful_searches) if successful_searches > 0 else Decimal("0.00")

        # Average response time (in minutes, for completed tickets)
        avg_time_conditions = base_conditions + [
            ManualSSNTicket.status == TicketStatus.completed,
            ManualSSNTicket.updated_at.isnot(None)
        ]
        avg_time_query = select(
            func.avg(
                func.extract('epoch', ManualSSNTicket.updated_at - ManualSSNTicket.created_at) / 60
            )
        ).select_from(ManualSSNTicket).where(and_(*avg_time_conditions))
        avg_time_result = await db.execute(avg_time_query)
        avg_response_time = avg_time_result.scalar()

        # Telegram statistics - total attempts via Telegram (filter by source)
        telegram_base_conditions = base_conditions + [ManualSSNTicket.source == RequestSource.telegram_bot]
        telegram_total_query = select(func.count()).select_from(ManualSSNTicket).where(and_(*telegram_base_conditions))
        telegram_total_result = await db.execute(telegram_total_query)
        telegram_total_attempts = telegram_total_result.scalar() or 0

        # Telegram successful searches (completed status)
        telegram_success_conditions = telegram_base_conditions + [ManualSSNTicket.status == TicketStatus.completed]
        telegram_success_query = select(func.count()).select_from(ManualSSNTicket).where(and_(*telegram_success_conditions))
        telegram_success_result = await db.execute(telegram_success_query)
        telegram_successful = telegram_success_result.scalar() or 0

        # Telegram failed searches (rejected status)
        telegram_failed_conditions = telegram_base_conditions + [ManualSSNTicket.status == TicketStatus.rejected]
        telegram_failed_query = select(func.count()).select_from(ManualSSNTicket).where(and_(*telegram_failed_conditions))
        telegram_failed_result = await db.execute(telegram_failed_query)
        telegram_failed = telegram_failed_result.scalar() or 0

        # Telegram success rate
        telegram_success_rate = (telegram_successful / telegram_total_attempts * 100) if telegram_total_attempts > 0 else 0.0

        # Set cache headers
        if response and ANALYTICS_CACHE_DURATION > 0:
            response.headers["Cache-Control"] = f"public, max-age={ANALYTICS_CACHE_DURATION}"

        return ManualSSNStatsResponse(
            total_attempts=total_attempts,
            successful_searches=successful_searches,
            failed_searches=failed_searches,
            pending_tickets=pending_tickets,
            processing_tickets=processing_tickets,
            success_rate=round(success_rate, 2),
            failure_rate=round(failure_rate, 2),
            total_revenue=total_revenue,
            processing_cost=processing_cost,
            net_profit=net_profit,
            profit_per_search=profit_per_search,
            avg_response_time=float(avg_response_time) if avg_response_time is not None else None,
            period=period,
            telegram_total_attempts=telegram_total_attempts,
            telegram_successful=telegram_successful,
            telegram_failed=telegram_failed,
            telegram_success_rate=round(telegram_success_rate, 2)
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve Manual SSN statistics: {str(e)}",
        )
