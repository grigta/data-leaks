"""Admin router for managing coupons, users, and other admin tasks."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from typing import Optional, List
from uuid import UUID
from datetime import datetime
from decimal import Decimal

from api.common.database import get_postgres_session
from api.common.models_postgres import User, Coupon, UserCoupon, CouponType
from api.public.dependencies import get_current_admin_user
from pydantic import BaseModel, Field, validator


# Pydantic models for request/response
class CouponCreate(BaseModel):
    """Schema for creating a new coupon."""
    code: str = Field(..., max_length=20, description="Coupon code")
    coupon_type: CouponType = Field(default=CouponType.percentage, description="Type of coupon")
    bonus_percent: Optional[int] = Field(None, ge=1, le=100, description="Bonus percentage (for percentage type)")
    bonus_amount: Optional[Decimal] = Field(None, gt=0, description="Bonus amount (for fixed_amount type)")
    requires_registration: bool = Field(default=False, description="Whether coupon requires new registration")
    max_uses: int = Field(..., gt=0, description="Maximum number of uses")
    is_active: bool = Field(default=True, description="Whether coupon is active")

    @validator('bonus_percent')
    def validate_bonus_percent(cls, v, values):
        if values.get('coupon_type') == CouponType.percentage and v is None:
            raise ValueError('bonus_percent is required for percentage coupons')
        if values.get('coupon_type') == CouponType.fixed_amount and v is not None:
            raise ValueError('bonus_percent should not be set for fixed_amount coupons')
        return v

    @validator('bonus_amount')
    def validate_bonus_amount(cls, v, values):
        if values.get('coupon_type') == CouponType.fixed_amount and v is None:
            raise ValueError('bonus_amount is required for fixed_amount coupons')
        if values.get('coupon_type') == CouponType.percentage and v is not None:
            raise ValueError('bonus_amount should not be set for percentage coupons')
        return v


class CouponUpdate(BaseModel):
    """Schema for updating a coupon."""
    bonus_percent: Optional[int] = Field(None, ge=1, le=100)
    bonus_amount: Optional[Decimal] = Field(None, gt=0)
    requires_registration: Optional[bool] = None
    max_uses: Optional[int] = Field(None, gt=0)
    is_active: Optional[bool] = None


class CouponResponse(BaseModel):
    """Schema for coupon response."""
    id: UUID
    code: str
    coupon_type: CouponType
    bonus_percent: Optional[int]
    bonus_amount: Optional[float]
    requires_registration: bool
    max_uses: int
    current_uses: int
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True
        json_encoders = {
            Decimal: lambda v: float(v) if v is not None else None
        }


class CouponListResponse(BaseModel):
    """Schema for list of coupons with pagination."""
    items: List[CouponResponse]
    total: int
    page: int
    page_size: int


class UserResponse(BaseModel):
    """Schema for user response."""
    id: UUID
    username: str
    email: str
    is_admin: bool
    is_worker: bool
    balance: float
    created_at: datetime
    last_login: Optional[datetime]

    class Config:
        from_attributes = True
        json_encoders = {
            Decimal: lambda v: float(v) if v is not None else None
        }


class UserListResponse(BaseModel):
    """Schema for list of users with pagination."""
    items: List[UserResponse]
    total: int
    page: int
    page_size: int


# Create router
router = APIRouter()


@router.get("/coupons/", response_model=CouponListResponse)
async def get_coupons(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    search: Optional[str] = Query(None, description="Search by coupon code"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    coupon_type: Optional[CouponType] = Query(None, description="Filter by coupon type"),
    db: AsyncSession = Depends(get_postgres_session),
    current_admin: User = Depends(get_current_admin_user)
):
    """Get all coupons with pagination and filters."""

    # Build query
    query = select(Coupon)

    # Apply filters
    filters = []
    if search:
        filters.append(Coupon.code.ilike(f"%{search}%"))
    if is_active is not None:
        filters.append(Coupon.is_active == is_active)
    if coupon_type is not None:
        filters.append(Coupon.coupon_type == coupon_type)

    if filters:
        query = query.where(and_(*filters))

    # Get total count
    count_query = select(func.count()).select_from(Coupon)
    if filters:
        count_query = count_query.where(and_(*filters))

    result = await db.execute(count_query)
    total = result.scalar_one()

    # Apply pagination
    query = query.order_by(Coupon.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    # Execute query
    result = await db.execute(query)
    coupons = result.scalars().all()

    return CouponListResponse(
        items=[CouponResponse.model_validate(c) for c in coupons],
        total=total,
        page=page,
        page_size=page_size
    )


@router.post("/coupons/", response_model=CouponResponse, status_code=201)
async def create_coupon(
    coupon_data: CouponCreate,
    db: AsyncSession = Depends(get_postgres_session),
    current_admin: User = Depends(get_current_admin_user)
):
    """Create a new coupon."""

    # Check if code already exists
    result = await db.execute(
        select(Coupon).where(Coupon.code == coupon_data.code)
    )
    existing = result.scalar_one_or_none()

    if existing:
        raise HTTPException(status_code=400, detail="Coupon code already exists")

    # Create coupon
    coupon = Coupon(
        code=coupon_data.code,
        coupon_type=coupon_data.coupon_type,
        bonus_percent=coupon_data.bonus_percent,
        bonus_amount=coupon_data.bonus_amount,
        requires_registration=coupon_data.requires_registration,
        max_uses=coupon_data.max_uses,
        is_active=coupon_data.is_active
    )

    db.add(coupon)
    await db.commit()
    await db.refresh(coupon)

    return CouponResponse.model_validate(coupon)


@router.get("/coupons/{coupon_id}", response_model=CouponResponse)
async def get_coupon(
    coupon_id: UUID,
    db: AsyncSession = Depends(get_postgres_session),
    current_admin: User = Depends(get_current_admin_user)
):
    """Get a specific coupon by ID."""

    result = await db.execute(
        select(Coupon).where(Coupon.id == coupon_id)
    )
    coupon = result.scalar_one_or_none()

    if not coupon:
        raise HTTPException(status_code=404, detail="Coupon not found")

    return CouponResponse.model_validate(coupon)


@router.patch("/coupons/{coupon_id}", response_model=CouponResponse)
async def update_coupon(
    coupon_id: UUID,
    coupon_data: CouponUpdate,
    db: AsyncSession = Depends(get_postgres_session),
    current_admin: User = Depends(get_current_admin_user)
):
    """Update a coupon."""

    result = await db.execute(
        select(Coupon).where(Coupon.id == coupon_id)
    )
    coupon = result.scalar_one_or_none()

    if not coupon:
        raise HTTPException(status_code=404, detail="Coupon not found")

    # Update fields
    update_data = coupon_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(coupon, field, value)

    await db.commit()
    await db.refresh(coupon)

    return CouponResponse.model_validate(coupon)


@router.delete("/coupons/{coupon_id}", status_code=204)
async def delete_coupon(
    coupon_id: UUID,
    db: AsyncSession = Depends(get_postgres_session),
    current_admin: User = Depends(get_current_admin_user)
):
    """Delete a coupon."""

    result = await db.execute(
        select(Coupon).where(Coupon.id == coupon_id)
    )
    coupon = result.scalar_one_or_none()

    if not coupon:
        raise HTTPException(status_code=404, detail="Coupon not found")

    await db.delete(coupon)
    await db.commit()

    return None


@router.get("/users/", response_model=UserListResponse)
async def get_users(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    search: Optional[str] = Query(None, description="Search by username or email"),
    is_admin: Optional[bool] = Query(None, description="Filter by admin status"),
    is_worker: Optional[bool] = Query(None, description="Filter by worker status"),
    db: AsyncSession = Depends(get_postgres_session),
    current_admin: User = Depends(get_current_admin_user)
):
    """Get all users with pagination and filters."""

    # Build query
    query = select(User)

    # Apply filters
    filters = []
    if search:
        filters.append(
            or_(
                User.username.ilike(f"%{search}%"),
                User.email.ilike(f"%{search}%")
            )
        )
    if is_admin is not None:
        filters.append(User.is_admin == is_admin)
    if is_worker is not None:
        filters.append(User.is_worker == is_worker)

    if filters:
        query = query.where(and_(*filters))

    # Get total count
    count_query = select(func.count()).select_from(User)
    if filters:
        count_query = count_query.where(and_(*filters))

    result = await db.execute(count_query)
    total = result.scalar_one()

    # Apply pagination
    query = query.order_by(User.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    # Execute query
    result = await db.execute(query)
    users = result.scalars().all()

    return UserListResponse(
        items=[UserResponse.model_validate(u) for u in users],
        total=total,
        page=page,
        page_size=page_size
    )


@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: UUID,
    db: AsyncSession = Depends(get_postgres_session),
    current_admin: User = Depends(get_current_admin_user)
):
    """Get a specific user by ID."""

    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return UserResponse.model_validate(user)
