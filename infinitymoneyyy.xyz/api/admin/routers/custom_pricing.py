"""
Admin router for custom pricing management.
Provides CRUD operations for user-specific service pricing.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import joinedload
from pydantic import BaseModel, Field, field_validator, model_validator
from typing import List, Optional
from decimal import Decimal
from uuid import UUID
import logging

from api.common.database import get_postgres_session
from api.common.models_postgres import CustomPricing, User
from api.admin.dependencies import get_current_admin_user

logger = logging.getLogger(__name__)
router = APIRouter()

# Allowed service names
ALLOWED_SERVICES = ['instant_ssn', 'manual_ssn']


# Pydantic models
class CustomPricingResponse(BaseModel):
    """Response model for custom pricing data."""
    id: str
    access_code: Optional[str] = None
    user_id: Optional[str] = None
    username: Optional[str] = None
    service_name: str
    price: str  # Decimal as string
    is_active: bool
    created_at: str
    updated_at: str

    @classmethod
    def from_custom_pricing(cls, pricing: CustomPricing):
        """Create response from CustomPricing model."""
        return cls(
            id=str(pricing.id),
            access_code=pricing.access_code,
            user_id=str(pricing.user_id) if pricing.user_id else None,
            username=pricing.user.username if pricing.user else None,
            service_name=pricing.service_name,
            price=str(pricing.price),
            is_active=pricing.is_active,
            created_at=pricing.created_at.isoformat(),
            updated_at=pricing.updated_at.isoformat()
        )


class CreateCustomPricingRequest(BaseModel):
    """Request model for creating a new custom pricing."""
    access_code: Optional[str] = Field(default=None, max_length=15, description="User's access code")
    user_id: Optional[str] = Field(default=None, description="User's UUID")
    service_name: str = Field(description="Service identifier (instant_ssn, manual_ssn)")
    price: str = Field(description="Custom price (must be >= 0)")
    is_active: bool = Field(default=True, description="Whether custom pricing is active")

    @model_validator(mode='after')
    def validate_identifier(self):
        """Validate that at least one identifier is provided."""
        if not self.access_code and not self.user_id:
            raise ValueError('Either access_code or user_id must be provided')
        return self

    @field_validator('service_name')
    @classmethod
    def validate_service_name(cls, v):
        if v not in ALLOWED_SERVICES:
            raise ValueError(f"Service name must be one of: {', '.join(ALLOWED_SERVICES)}")
        return v

    @field_validator('price')
    @classmethod
    def validate_price(cls, v):
        try:
            price = Decimal(v)
            if price < 0:
                raise ValueError("Price must be >= 0")
            return v
        except Exception:
            raise ValueError("Invalid price format")


class UpdateCustomPricingRequest(BaseModel):
    """Request model for updating an existing custom pricing."""
    price: Optional[str] = Field(default=None, description="Custom price (must be >= 0)")
    is_active: Optional[bool] = Field(default=None)

    @field_validator('price')
    @classmethod
    def validate_price(cls, v):
        if v is not None:
            try:
                price = Decimal(v)
                if price < 0:
                    raise ValueError("Price must be >= 0")
            except Exception:
                raise ValueError("Invalid price format")
        return v


class CustomPricingListResponse(BaseModel):
    """Response model for listing custom pricing."""
    custom_pricing: List[CustomPricingResponse]
    total_count: int


@router.post("/", response_model=CustomPricingResponse, status_code=status.HTTP_201_CREATED)
async def create_custom_pricing(
    request: CreateCustomPricingRequest,
    db: AsyncSession = Depends(get_postgres_session),
    admin_user = Depends(get_current_admin_user)
):
    """
    Create a new custom pricing entry.

    Admin only. Either access_code or user_id must be provided.
    Combination of (access_code or user_id) and service_name must be unique.
    """
    try:
        user = None
        final_access_code = request.access_code
        final_user_id = None

        # Validate and resolve user based on provided identifier
        if request.user_id:
            # Validate user_id format
            try:
                user_uuid = UUID(request.user_id)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid user_id format. Must be a valid UUID"
                )

            # Fetch user
            user_result = await db.execute(
                select(User).where(User.id == user_uuid)
            )
            user = user_result.scalar_one_or_none()
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"User with ID '{request.user_id}' not found"
                )
            final_user_id = user.id
            final_access_code = user.access_code  # Auto-resolve access_code from user
        elif request.access_code:
            # Validate access_code exists
            user_result = await db.execute(
                select(User).where(User.access_code == request.access_code)
            )
            user = user_result.scalar_one_or_none()
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"User with access_code '{request.access_code}' not found"
                )
            final_user_id = user.id

        # Check for existing custom pricing by user_id
        if final_user_id:
            result = await db.execute(
                select(CustomPricing).where(
                    CustomPricing.user_id == final_user_id,
                    CustomPricing.service_name == request.service_name
                )
            )
            existing = result.scalar_one_or_none()
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Custom pricing for user and service '{request.service_name}' already exists"
                )

        # Create custom pricing with both identifiers
        new_pricing = CustomPricing(
            access_code=final_access_code,
            user_id=final_user_id,
            service_name=request.service_name,
            price=Decimal(request.price),
            is_active=request.is_active
        )

        db.add(new_pricing)
        await db.commit()
        await db.refresh(new_pricing, ['user'])

        identifier = f"user_id={final_user_id}" if request.user_id else f"access_code={final_access_code}"
        logger.info(f"Admin {admin_user.username} created custom pricing for {identifier}/{request.service_name}")
        return CustomPricingResponse.from_custom_pricing(new_pricing)

    except HTTPException:
        raise
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error creating custom pricing: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create custom pricing"
        )


@router.get("/", response_model=CustomPricingListResponse)
async def list_custom_pricing(
    access_code: Optional[str] = None,
    user_id: Optional[str] = None,
    service_name: Optional[str] = None,
    is_active: Optional[bool] = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_postgres_session),
    admin_user = Depends(get_current_admin_user)
):
    """
    List all custom pricing with pagination and filtering.

    Admin only. Can filter by access_code, user_id, service_name, and active status.
    """
    # Validate service_name if provided
    if service_name is not None and service_name not in ALLOWED_SERVICES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid service name. Must be one of: {', '.join(ALLOWED_SERVICES)}"
        )

    try:
        # Validate user_id format if provided
        user_uuid = None
        if user_id is not None:
            try:
                user_uuid = UUID(user_id)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid user_id format. Must be a valid UUID"
                )

        # Build query with joinedload for user relationship
        query = select(CustomPricing).options(joinedload(CustomPricing.user))

        # Apply filters
        if access_code is not None:
            query = query.where(CustomPricing.access_code == access_code)
        if user_uuid is not None:
            query = query.where(CustomPricing.user_id == user_uuid)
        if service_name is not None:
            query = query.where(CustomPricing.service_name == service_name)
        if is_active is not None:
            query = query.where(CustomPricing.is_active == is_active)

        # Order and paginate
        query = query.order_by(CustomPricing.created_at.desc()).offset(offset).limit(limit)

        # Execute query
        result = await db.execute(query)
        pricing_list = result.scalars().all()

        # Get total count
        count_query = select(func.count(CustomPricing.id))
        if access_code is not None:
            count_query = count_query.where(CustomPricing.access_code == access_code)
        if user_uuid is not None:
            count_query = count_query.where(CustomPricing.user_id == user_uuid)
        if service_name is not None:
            count_query = count_query.where(CustomPricing.service_name == service_name)
        if is_active is not None:
            count_query = count_query.where(CustomPricing.is_active == is_active)

        count_result = await db.execute(count_query)
        total_count = count_result.scalar_one()

        return CustomPricingListResponse(
            custom_pricing=[CustomPricingResponse.from_custom_pricing(p) for p in pricing_list],
            total_count=total_count
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing custom pricing: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list custom pricing"
        )


@router.get("/{custom_pricing_id}", response_model=CustomPricingResponse)
async def get_custom_pricing(
    custom_pricing_id: UUID,
    db: AsyncSession = Depends(get_postgres_session),
    admin_user = Depends(get_current_admin_user)
):
    """
    Get a specific custom pricing by ID.

    Admin only.
    """
    try:
        result = await db.execute(
            select(CustomPricing)
            .options(joinedload(CustomPricing.user))
            .where(CustomPricing.id == custom_pricing_id)
        )
        pricing = result.scalar_one_or_none()

        if not pricing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Custom pricing not found"
            )

        return CustomPricingResponse.from_custom_pricing(pricing)

    except HTTPException:
        raise
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting custom pricing {custom_pricing_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get custom pricing"
        )


@router.get("/by-code/{access_code}", response_model=List[CustomPricingResponse])
async def get_custom_pricing_by_code(
    access_code: str,
    db: AsyncSession = Depends(get_postgres_session),
    admin_user = Depends(get_current_admin_user)
):
    """
    Get all custom pricing for an access code.

    Admin only. Returns list of custom pricing for this user.
    """
    try:
        result = await db.execute(
            select(CustomPricing)
            .options(joinedload(CustomPricing.user))
            .where(CustomPricing.access_code == access_code)
            .order_by(CustomPricing.service_name)
        )
        pricing_list = result.scalars().all()

        return [CustomPricingResponse.from_custom_pricing(p) for p in pricing_list]

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting custom pricing by code {access_code}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get custom pricing by code"
        )


@router.get("/by-user/{user_id}", response_model=List[CustomPricingResponse])
async def get_custom_pricing_by_user(
    user_id: UUID,
    db: AsyncSession = Depends(get_postgres_session),
    admin_user = Depends(get_current_admin_user)
):
    """
    Get all custom pricing for a user by user_id.

    Admin only. Returns list of custom pricing for this user.
    """
    try:
        result = await db.execute(
            select(CustomPricing)
            .options(joinedload(CustomPricing.user))
            .where(CustomPricing.user_id == user_id)
            .order_by(CustomPricing.service_name)
        )
        pricing_list = result.scalars().all()

        return [CustomPricingResponse.from_custom_pricing(p) for p in pricing_list]

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting custom pricing by user_id {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get custom pricing by user"
        )


@router.patch("/{custom_pricing_id}", response_model=CustomPricingResponse)
async def update_custom_pricing(
    custom_pricing_id: UUID,
    request: UpdateCustomPricingRequest,
    db: AsyncSession = Depends(get_postgres_session),
    admin_user = Depends(get_current_admin_user)
):
    """
    Update an existing custom pricing.

    Admin only. Can update price and/or is_active.
    """
    try:
        # Get custom pricing
        result = await db.execute(
            select(CustomPricing)
            .options(joinedload(CustomPricing.user))
            .where(CustomPricing.id == custom_pricing_id)
        )
        pricing = result.scalar_one_or_none()

        if not pricing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Custom pricing not found"
            )

        # Update fields
        if request.price is not None:
            pricing.price = Decimal(request.price)

        if request.is_active is not None:
            pricing.is_active = request.is_active

        await db.commit()
        await db.refresh(pricing, ['user'])

        logger.info(f"Admin {admin_user.username} updated custom pricing {custom_pricing_id}")
        return CustomPricingResponse.from_custom_pricing(pricing)

    except HTTPException:
        raise
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error updating custom pricing {custom_pricing_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update custom pricing"
        )


@router.delete("/{custom_pricing_id}")
async def delete_custom_pricing(
    custom_pricing_id: UUID,
    db: AsyncSession = Depends(get_postgres_session),
    admin_user = Depends(get_current_admin_user)
):
    """
    Delete a custom pricing.

    Admin only.
    """
    try:
        # Get custom pricing
        result = await db.execute(
            select(CustomPricing).where(CustomPricing.id == custom_pricing_id)
        )
        pricing = result.scalar_one_or_none()

        if not pricing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Custom pricing not found"
            )

        # Delete custom pricing
        await db.delete(pricing)
        await db.commit()

        logger.info(f"Admin {admin_user.username} deleted custom pricing {custom_pricing_id}")
        return {"message": "Custom pricing deleted successfully"}

    except HTTPException:
        raise
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error deleting custom pricing {custom_pricing_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete custom pricing"
        )


@router.post("/{custom_pricing_id}/toggle", response_model=CustomPricingResponse)
async def toggle_custom_pricing(
    custom_pricing_id: UUID,
    db: AsyncSession = Depends(get_postgres_session),
    admin_user = Depends(get_current_admin_user)
):
    """
    Toggle custom pricing active status.

    Admin only. Quick endpoint to toggle is_active status.
    """
    try:
        # Get custom pricing
        result = await db.execute(
            select(CustomPricing)
            .options(joinedload(CustomPricing.user))
            .where(CustomPricing.id == custom_pricing_id)
        )
        pricing = result.scalar_one_or_none()

        if not pricing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Custom pricing not found"
            )

        # Toggle is_active
        pricing.is_active = not pricing.is_active
        await db.commit()
        await db.refresh(pricing, ['user'])

        logger.info(f"Admin {admin_user.username} toggled custom pricing {custom_pricing_id} to {pricing.is_active}")
        return CustomPricingResponse.from_custom_pricing(pricing)

    except HTTPException:
        raise
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error toggling custom pricing {custom_pricing_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to toggle custom pricing"
        )
