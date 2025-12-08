"""
Subscriptions router for Public API.
"""
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.common.database import get_postgres_session
from api.common.models_postgres import User, Subscription, SubscriptionPlan
from api.public.dependencies import get_current_user


router = APIRouter()


# Pydantic models
class SubscriptionPlanResponse(BaseModel):
    id: UUID
    name: str
    duration_months: int
    price: Decimal
    discount_percent: int

    class Config:
        from_attributes = True


class SubscriptionResponse(BaseModel):
    id: UUID
    plan: SubscriptionPlanResponse
    start_date: datetime
    end_date: datetime
    is_active: bool

    class Config:
        from_attributes = True


class PurchaseSubscriptionRequest(BaseModel):
    plan_id: UUID


class CheckAccessResponse(BaseModel):
    has_access: bool
    subscription: Optional[SubscriptionResponse] = None
    message: str


@router.get("/plans", response_model=List[SubscriptionPlanResponse])
async def get_subscription_plans(
    db: AsyncSession = Depends(get_postgres_session)
):
    """Get list of active subscription plans."""
    result = await db.execute(
        select(SubscriptionPlan)
        .where(SubscriptionPlan.is_active == True)
        .order_by(SubscriptionPlan.duration_months)
    )
    plans = result.scalars().all()
    return plans


@router.post("/purchase", response_model=SubscriptionResponse)
async def purchase_subscription(
    request: PurchaseSubscriptionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_postgres_session)
):
    """
    Purchase a subscription plan.

    Deducts the plan price from user balance and creates a new subscription.
    """
    # Check if plan exists and is active
    result = await db.execute(
        select(SubscriptionPlan)
        .where(SubscriptionPlan.id == request.plan_id, SubscriptionPlan.is_active == True)
    )
    plan = result.scalar_one_or_none()

    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subscription plan not found or not active"
        )

    # Check if user already has an active subscription
    result = await db.execute(
        select(Subscription)
        .where(
            Subscription.user_id == current_user.id,
            Subscription.is_active == True,
            Subscription.end_date > datetime.utcnow()
        )
    )
    existing_subscription = result.scalar_one_or_none()

    if existing_subscription:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You already have an active subscription. Please wait for it to expire before purchasing a new one."
        )

    # Check user balance
    if current_user.balance < plan.price:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Insufficient balance. Required: ${plan.price}, Available: ${current_user.balance}"
        )

    # Create subscription in a transaction
    try:
        # Deduct balance
        current_user.balance -= plan.price

        # Calculate dates
        start_date = datetime.utcnow()
        end_date = start_date + timedelta(days=plan.duration_months * 30)

        # Create subscription
        subscription = Subscription(
            user_id=current_user.id,
            plan_id=plan.id,
            start_date=start_date,
            end_date=end_date,
            is_active=True
        )

        db.add(subscription)
        await db.commit()
        await db.refresh(subscription)

        # Load plan relationship for response
        result = await db.execute(
            select(Subscription)
            .options(selectinload(Subscription.plan))
            .where(Subscription.id == subscription.id)
        )
        subscription = result.scalar_one()

        return subscription

    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create subscription: {str(e)}"
        )


@router.get("/my-subscription", response_model=Optional[SubscriptionResponse])
async def get_my_subscription(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_postgres_session)
):
    """Get current user's active subscription."""
    result = await db.execute(
        select(Subscription)
        .options(selectinload(Subscription.plan))
        .where(
            Subscription.user_id == current_user.id,
            Subscription.is_active == True,
            Subscription.end_date > datetime.utcnow()
        )
        .order_by(Subscription.end_date.desc())
        .limit(1)
    )
    subscription = result.scalar_one_or_none()
    return subscription


@router.get("/check-access", response_model=CheckAccessResponse)
async def check_subscription_access(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_postgres_session)
):
    """Check if current user has access to lookup API via subscription."""
    result = await db.execute(
        select(Subscription)
        .options(selectinload(Subscription.plan))
        .where(
            Subscription.user_id == current_user.id,
            Subscription.is_active == True,
            Subscription.end_date > datetime.utcnow()
        )
        .order_by(Subscription.end_date.desc())
        .limit(1)
    )
    subscription = result.scalar_one_or_none()

    if subscription:
        days_remaining = (subscription.end_date - datetime.utcnow()).days
        return CheckAccessResponse(
            has_access=True,
            subscription=subscription,
            message=f"Active subscription. {days_remaining} days remaining."
        )
    else:
        return CheckAccessResponse(
            has_access=False,
            subscription=None,
            message="No active subscription. Purchase a subscription to access Lookup SSN feature."
        )
