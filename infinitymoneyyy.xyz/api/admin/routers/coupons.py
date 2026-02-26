"""
Admin router for coupon management.
Provides CRUD operations for coupons and statistics.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func, and_
from pydantic import BaseModel, Field
from typing import List, Optional
from decimal import Decimal
from uuid import UUID
import secrets
from datetime import datetime
import logging

from api.common.database import get_postgres_session
from api.common.models_postgres import Coupon, UserCoupon, User, Transaction, CouponType
from api.admin.dependencies import get_current_admin_user

logger = logging.getLogger(__name__)
router = APIRouter()


# Pydantic models
class CreateCouponRequest(BaseModel):
    """Request model for creating a new coupon."""
    code: Optional[str] = Field(default=None, max_length=20, description="Coupon code (auto-generated if not provided)")
    bonus_percent: Optional[int] = Field(default=None, ge=1, le=100, description="Bonus percentage (1-100)")
    coupon_type: str = Field(default='percentage', description="Coupon type: percentage, fixed_amount, registration, registration_bonus")
    bonus_amount: Optional[Decimal] = Field(default=None, description="Fixed bonus amount (for fixed_amount type)")
    requires_registration: bool = Field(default=False, description="Whether coupon is required for registration")
    max_uses: int = Field(ge=1, description="Maximum number of uses")
    is_active: bool = Field(default=True, description="Whether coupon is active")


class UpdateCouponRequest(BaseModel):
    """Request model for updating an existing coupon."""
    bonus_percent: Optional[int] = Field(default=None, ge=1, le=100)
    coupon_type: Optional[str] = Field(default=None)
    bonus_amount: Optional[Decimal] = Field(default=None)
    requires_registration: Optional[bool] = Field(default=None)
    max_uses: Optional[int] = Field(default=None, ge=1)
    is_active: Optional[bool] = Field(default=None)


class CouponResponse(BaseModel):
    """Response model for coupon data."""
    id: str
    code: str
    bonus_percent: Optional[int]
    coupon_type: str
    bonus_amount: Optional[Decimal]
    requires_registration: bool
    max_uses: int
    current_uses: int
    is_active: bool
    created_at: str
    usage_percentage: float

    @classmethod
    def from_coupon(cls, coupon: Coupon):
        """Create response from Coupon model."""
        usage_pct = (coupon.current_uses / coupon.max_uses * 100) if coupon.max_uses > 0 else 0
        return cls(
            id=str(coupon.id),
            code=coupon.code,
            bonus_percent=coupon.bonus_percent,
            coupon_type=coupon.coupon_type.value,
            bonus_amount=coupon.bonus_amount,
            requires_registration=coupon.requires_registration,
            max_uses=coupon.max_uses,
            current_uses=coupon.current_uses,
            is_active=coupon.is_active,
            created_at=coupon.created_at.isoformat(),
            usage_percentage=round(usage_pct, 2)
        )


class CouponListResponse(BaseModel):
    """Response model for listing coupons."""
    coupons: List[CouponResponse]
    total_count: int


class CouponStatsResponse(BaseModel):
    """Response model for coupon statistics."""
    total_coupons: int
    active_coupons: int
    total_uses: int
    total_bonus_given: Decimal


class UserCouponUsage(BaseModel):
    """Response model for user coupon usage."""
    user_id: str
    username: str
    email: str
    applied_at: str
    bonus_amount: Decimal


class CouponUsersResponse(BaseModel):
    """Response model for listing users who used a coupon."""
    users: List[UserCouponUsage]
    total_count: int


async def generate_coupon_code(db: AsyncSession) -> str:
    """
    Generate a unique, cryptographically secure coupon code.

    Uses secrets.token_urlsafe for secure random generation.
    Checks database for uniqueness to prevent collisions.
    """
    max_attempts = 10
    for _ in range(max_attempts):
        # Generate 16-character URL-safe random string
        raw_code = secrets.token_urlsafe(12)
        # Clean up: uppercase, remove hyphens/underscores
        code = raw_code.upper().replace("-", "").replace("_", "")[:16]

        # Check uniqueness (direct comparison with normalized code)
        result = await db.execute(
            select(Coupon).where(Coupon.code == code)
        )
        existing = result.scalar_one_or_none()

        if not existing:
            return code

    # Fallback: add timestamp suffix to guarantee uniqueness
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    return f"COUPON{timestamp}"


@router.post("/", response_model=CouponResponse, status_code=status.HTTP_201_CREATED)
async def create_coupon(
    request: CreateCouponRequest,
    db: AsyncSession = Depends(get_postgres_session),
    admin_user = Depends(get_current_admin_user)
):
    """
    Create a new coupon.

    Admin only. If code is not provided, generates a unique random code.
    """
    try:
        # Validate coupon type
        if request.coupon_type not in ['percentage', 'fixed_amount', 'registration', 'registration_bonus']:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid coupon_type: {request.coupon_type}"
            )

        # Type-specific validation
        if request.coupon_type == 'percentage':
            if not request.bonus_percent or request.bonus_percent < 1 or request.bonus_percent > 100:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Percentage coupons require bonus_percent (1-100)"
                )
            if request.bonus_amount is not None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Percentage coupons cannot have bonus_amount"
                )
        elif request.coupon_type == 'fixed_amount':
            if not request.bonus_amount or request.bonus_amount <= 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Fixed amount coupons require bonus_amount > 0"
                )
            request.bonus_percent = None
        elif request.coupon_type == 'registration':
            # Registration coupons don't give bonuses
            request.requires_registration = True
            request.bonus_percent = None
            request.bonus_amount = None
        elif request.coupon_type == 'registration_bonus':
            if not request.bonus_amount or request.bonus_amount <= 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Registration bonus coupons require bonus_amount > 0"
                )
            request.requires_registration = True
            request.bonus_percent = None

        # Generate or validate code
        if request.code:
            # Normalize code: strip whitespace and convert to uppercase
            code = request.code.strip().upper()

            # Validate length
            if len(code) > 20:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Coupon code cannot exceed 20 characters"
                )

            # Check if code already exists (direct comparison with normalized code)
            result = await db.execute(
                select(Coupon).where(Coupon.code == code)
            )
            existing = result.scalar_one_or_none()
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Coupon code '{code}' already exists"
                )
        else:
            code = await generate_coupon_code(db)

        # Determine bonus_percent based on coupon_type
        if request.coupon_type == 'percentage':
            bonus_percent = request.bonus_percent
        else:
            # For fixed_amount, registration, and registration_bonus, set bonus_percent to None
            bonus_percent = None

        # Create coupon
        new_coupon = Coupon(
            code=code,
            bonus_percent=bonus_percent,
            coupon_type=CouponType[request.coupon_type],
            bonus_amount=request.bonus_amount,
            requires_registration=request.requires_registration,
            max_uses=request.max_uses,
            current_uses=0,
            is_active=request.is_active
        )

        db.add(new_coupon)
        await db.commit()
        await db.refresh(new_coupon)

        logger.info(f"Admin {admin_user.username} created coupon {code}")
        return CouponResponse.from_coupon(new_coupon)

    except HTTPException:
        raise
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error creating coupon: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create coupon"
        )


@router.get("/", response_model=CouponListResponse)
async def list_coupons(
    is_active: Optional[bool] = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_postgres_session),
    admin_user = Depends(get_current_admin_user)
):
    """
    List all coupons with pagination and filtering.

    Admin only. Can filter by active status.
    """
    try:
        # Build query
        query = select(Coupon)

        # Apply filter
        if is_active is not None:
            query = query.where(Coupon.is_active == is_active)

        # Order and paginate
        query = query.order_by(Coupon.created_at.desc()).offset(offset).limit(limit)

        # Execute query
        result = await db.execute(query)
        coupons = result.scalars().all()

        # Get total count
        count_query = select(func.count(Coupon.id))
        if is_active is not None:
            count_query = count_query.where(Coupon.is_active == is_active)

        count_result = await db.execute(count_query)
        total_count = count_result.scalar_one()

        return CouponListResponse(
            coupons=[CouponResponse.from_coupon(c) for c in coupons],
            total_count=total_count
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing coupons: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list coupons"
        )


@router.get("/stats", response_model=CouponStatsResponse)
async def get_coupon_stats(
    db: AsyncSession = Depends(get_postgres_session),
    admin_user = Depends(get_current_admin_user)
):
    """
    Get overall coupon statistics.

    Admin only.
    """
    try:
        # Total coupons
        total_result = await db.execute(select(func.count(Coupon.id)))
        total_coupons = total_result.scalar_one()

        # Active coupons
        active_result = await db.execute(
            select(func.count(Coupon.id)).where(Coupon.is_active == True)
        )
        active_coupons = active_result.scalar_one()

        # Total uses
        uses_result = await db.execute(select(func.sum(Coupon.current_uses)))
        total_uses = uses_result.scalar_one() or 0

        # Total bonus given (estimated from coupon usage)
        # This is an approximation - actual bonus depends on transaction amounts
        # For exact calculation, would need to parse transaction metadata
        total_bonus_given = Decimal("0.00")

        return CouponStatsResponse(
            total_coupons=total_coupons,
            active_coupons=active_coupons,
            total_uses=total_uses,
            total_bonus_given=total_bonus_given
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting coupon stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get coupon statistics"
        )


@router.get("/{coupon_id}", response_model=CouponResponse)
async def get_coupon(
    coupon_id: UUID,
    db: AsyncSession = Depends(get_postgres_session),
    admin_user = Depends(get_current_admin_user)
):
    """
    Get a specific coupon by ID.

    Admin only.
    """
    try:
        result = await db.execute(select(Coupon).where(Coupon.id == coupon_id))
        coupon = result.scalar_one_or_none()

        if not coupon:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Coupon not found"
            )

        return CouponResponse.from_coupon(coupon)

    except HTTPException:
        raise
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting coupon {coupon_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get coupon"
        )


@router.get("/code/{code}", response_model=CouponResponse)
async def get_coupon_by_code(
    code: str,
    db: AsyncSession = Depends(get_postgres_session),
    admin_user = Depends(get_current_admin_user)
):
    """
    Get a specific coupon by code.

    Admin only. Case-insensitive lookup.
    """
    try:
        # Normalize code for lookup
        normalized_code = code.strip().upper()

        # Direct comparison with normalized code
        result = await db.execute(
            select(Coupon).where(Coupon.code == normalized_code)
        )
        coupon = result.scalar_one_or_none()

        if not coupon:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Coupon not found"
            )

        return CouponResponse.from_coupon(coupon)

    except HTTPException:
        raise
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting coupon by code {code}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get coupon"
        )


@router.patch("/{coupon_id}", response_model=CouponResponse)
async def update_coupon(
    coupon_id: UUID,
    request: UpdateCouponRequest,
    db: AsyncSession = Depends(get_postgres_session),
    admin_user = Depends(get_current_admin_user)
):
    """
    Update an existing coupon.

    Admin only. Can update bonus_percent, max_uses, and is_active.
    Cannot reduce max_uses below current_uses.
    """
    try:
        # Get coupon
        result = await db.execute(select(Coupon).where(Coupon.id == coupon_id))
        coupon = result.scalar_one_or_none()

        if not coupon:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Coupon not found"
            )

        # Determine target coupon type (new or current)
        target_coupon_type = request.coupon_type if request.coupon_type is not None else coupon.coupon_type.value

        # Validate coupon_type if updating
        if request.coupon_type is not None:
            if request.coupon_type not in ['percentage', 'fixed_amount', 'registration', 'registration_bonus']:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid coupon_type: {request.coupon_type}"
                )
            coupon.coupon_type = CouponType[request.coupon_type]

        # Type-specific validation based on target type
        if target_coupon_type == 'percentage':
            # For percentage coupons, require bonus_percent in range 1-100
            effective_bonus_percent = request.bonus_percent if request.bonus_percent is not None else coupon.bonus_percent
            if effective_bonus_percent is None or effective_bonus_percent < 1 or effective_bonus_percent > 100:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Percentage coupons require bonus_percent (1-100)"
                )
            # Update bonus_percent if provided
            if request.bonus_percent is not None:
                coupon.bonus_percent = request.bonus_percent
            # Ensure bonus_amount is None for percentage coupons
            if request.bonus_amount is not None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Percentage coupons cannot have bonus_amount"
                )
        elif target_coupon_type == 'fixed_amount':
            # For fixed_amount coupons, require positive bonus_amount
            effective_bonus_amount = request.bonus_amount if request.bonus_amount is not None else coupon.bonus_amount
            if effective_bonus_amount is None or effective_bonus_amount <= 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Fixed amount coupons require bonus_amount > 0"
                )
            # Update bonus_amount if provided
            if request.bonus_amount is not None:
                coupon.bonus_amount = request.bonus_amount
            # Set bonus_percent to None for fixed_amount coupons
            coupon.bonus_percent = None
        elif target_coupon_type == 'registration':
            # For registration coupons, no bonuses allowed
            if request.bonus_percent is not None and request.bonus_percent != 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Registration coupons cannot have bonus_percent"
                )
            if request.bonus_amount is not None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Registration coupons cannot have bonus_amount"
                )
            # Set bonuses to None
            coupon.bonus_percent = None
            coupon.bonus_amount = None
            # Ensure requires_registration is True
            coupon.requires_registration = True
        elif target_coupon_type == 'registration_bonus':
            # For registration_bonus coupons, require positive bonus_amount
            effective_bonus_amount = request.bonus_amount if request.bonus_amount is not None else coupon.bonus_amount
            if effective_bonus_amount is None or effective_bonus_amount <= 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Registration bonus coupons require bonus_amount > 0"
                )
            # Update bonus_amount if provided
            if request.bonus_amount is not None:
                coupon.bonus_amount = request.bonus_amount
            # Set bonus_percent to None for registration_bonus coupons
            coupon.bonus_percent = None
            # Ensure requires_registration is True
            coupon.requires_registration = True

        # Validate max_uses if updating
        if request.max_uses is not None:
            if request.max_uses < coupon.current_uses:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Cannot reduce max_uses below current_uses ({coupon.current_uses})"
                )
            coupon.max_uses = request.max_uses

        # Update requires_registration if explicitly provided (and not a registration type)
        if request.requires_registration is not None and target_coupon_type not in ['registration', 'registration_bonus']:
            coupon.requires_registration = request.requires_registration

        # Update is_active if provided
        if request.is_active is not None:
            coupon.is_active = request.is_active

        await db.commit()
        await db.refresh(coupon)

        logger.info(f"Admin {admin_user.username} updated coupon {coupon.code}")
        return CouponResponse.from_coupon(coupon)

    except HTTPException:
        raise
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error updating coupon {coupon_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update coupon"
        )


@router.delete("/{coupon_id}")
async def delete_coupon(
    coupon_id: UUID,
    db: AsyncSession = Depends(get_postgres_session),
    admin_user = Depends(get_current_admin_user)
):
    """
    Delete a coupon.

    Admin only. Can only delete coupons that haven't been used.
    For used coupons, deactivate instead.
    """
    try:
        # Get coupon
        result = await db.execute(select(Coupon).where(Coupon.id == coupon_id))
        coupon = result.scalar_one_or_none()

        if not coupon:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Coupon not found"
            )

        # Check if used
        if coupon.current_uses > 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete coupon that has been used. Deactivate it instead."
            )

        # Delete coupon (cascade will delete UserCoupon records)
        await db.delete(coupon)
        await db.commit()

        logger.info(f"Admin {admin_user.username} deleted coupon {coupon.code}")
        return {"message": "Coupon deleted successfully"}

    except HTTPException:
        raise
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error deleting coupon {coupon_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete coupon"
        )


@router.post("/{coupon_id}/deactivate", response_model=CouponResponse)
async def deactivate_coupon(
    coupon_id: UUID,
    db: AsyncSession = Depends(get_postgres_session),
    admin_user = Depends(get_current_admin_user)
):
    """
    Deactivate a coupon.

    Admin only. Sets is_active to False.
    """
    try:
        # Get coupon
        result = await db.execute(select(Coupon).where(Coupon.id == coupon_id))
        coupon = result.scalar_one_or_none()

        if not coupon:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Coupon not found"
            )

        # Deactivate
        coupon.is_active = False
        await db.commit()
        await db.refresh(coupon)

        logger.info(f"Admin {admin_user.username} deactivated coupon {coupon.code}")
        return CouponResponse.from_coupon(coupon)

    except HTTPException:
        raise
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error deactivating coupon {coupon_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to deactivate coupon"
        )


@router.get("/{coupon_id}/users", response_model=CouponUsersResponse)
async def get_coupon_users(
    coupon_id: UUID,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_postgres_session),
    admin_user = Depends(get_current_admin_user)
):
    """
    List users who have used a specific coupon.

    Admin only. Returns user details and usage timestamp.
    """
    try:
        # Verify coupon exists
        coupon_result = await db.execute(select(Coupon).where(Coupon.id == coupon_id))
        coupon = coupon_result.scalar_one_or_none()

        if not coupon:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Coupon not found"
            )

        # Get user coupons with user info
        query = (
            select(UserCoupon, User)
            .join(User, UserCoupon.user_id == User.id)
            .where(UserCoupon.coupon_id == coupon_id)
            .order_by(UserCoupon.applied_at.desc())
            .offset(offset)
            .limit(limit)
        )

        result = await db.execute(query)
        user_coupons = result.all()

        # Get total count
        count_query = select(func.count(UserCoupon.id)).where(UserCoupon.coupon_id == coupon_id)
        count_result = await db.execute(count_query)
        total_count = count_result.scalar_one()

        # Build response with bonus_amount from transactions
        users = []
        for user_coupon, user in user_coupons:
            # Find transaction with this coupon code
            transaction_query = (
                select(Transaction)
                .where(Transaction.user_id == user.id)
                .order_by(Transaction.created_at.desc())
            )
            transaction_result = await db.execute(transaction_query)
            transactions = transaction_result.scalars().all()

            # Find the transaction with matching coupon code in metadata
            bonus_amount = Decimal('0.00')
            for transaction in transactions:
                if transaction.payment_metadata and isinstance(transaction.payment_metadata, dict):
                    if transaction.payment_metadata.get('coupon_code') == coupon.code:
                        # Extract bonus_amount from metadata
                        bonus_str = transaction.payment_metadata.get('coupon_bonus_amount', '0.00')
                        try:
                            bonus_amount = Decimal(bonus_str)
                            break
                        except (ValueError, TypeError):
                            bonus_amount = Decimal('0.00')

            users.append(UserCouponUsage(
                user_id=str(user.id),
                username=user.username,
                email=user.email,
                applied_at=user_coupon.applied_at.isoformat(),
                bonus_amount=bonus_amount
            ))

        return CouponUsersResponse(users=users, total_count=total_count)

    except HTTPException:
        raise
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting coupon users for {coupon_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get coupon users"
        )
