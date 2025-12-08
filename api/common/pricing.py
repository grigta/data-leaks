"""Centralized pricing constants and helper functions for API."""
from decimal import Decimal
from typing import Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import logging
import os

logger = logging.getLogger(__name__)


# Search pricing constants
INSTANT_SSN_PRICE = Decimal("2.00")
MANUAL_SSN_PRICE = Decimal("3.00")
REVERSE_SSN_PRICE = Decimal("1.50")  # DEPRECATED: Used only for historical orders display
PHONE_LOOKUP_PRICE = Decimal("3.00")  # Phone lookup via DaisySMS + SearchBug

# External API costs
SEARCHBUG_API_COST = Decimal("0.77")

# Invitation/Referral bonuses (configurable via environment variables)
INVITATION_BONUS_INVITEE = Decimal(os.getenv("INVITATION_BONUS_INVITEE", "5.00"))  # Bonus for new user who registers with invitation code
INVITATION_BONUS_INVITER = Decimal(os.getenv("INVITATION_BONUS_INVITER", "3.00"))  # Bonus for user who invited someone


async def get_user_price(
    db: AsyncSession,
    access_code: str,
    service_name: str,
    default_price: Decimal
) -> Decimal:
    """
    Get custom price for a user by access_code and service_name.
    Falls back to default_price if no custom pricing is found or if custom pricing is inactive.

    Note: This function queries by access_code for backward compatibility.
    For user_id-based queries, use get_user_price_by_id() or get_price_for_user().

    Args:
        db: Database session
        access_code: User's access code
        service_name: Service identifier ('instant_ssn', 'manual_ssn')
        default_price: Default price to use if no custom pricing found

    Returns:
        Decimal: Custom price or default price
    """
    try:
        # Import here to avoid circular import
        from api.common.models_postgres import CustomPricing

        result = await db.execute(
            select(CustomPricing)
            .where(
                CustomPricing.access_code == access_code,
                CustomPricing.service_name == service_name,
                CustomPricing.is_active == True
            )
        )
        custom_pricing = result.scalar_one_or_none()

        if custom_pricing:
            return custom_pricing.price

        return default_price
    except Exception as e:
        # Log the error with details
        logger.error(
            f"Error getting custom pricing: access_code={access_code}, "
            f"service_name={service_name}, default_price={default_price}, "
            f"error={e}",
            exc_info=True
        )
        # On any error, return default price
        return default_price


async def get_user_price_by_id(
    db: AsyncSession,
    user_id: UUID,
    service_name: str,
    default_price: Decimal
) -> Decimal:
    """
    Get custom price for a user by user_id and service_name.
    Falls back to default_price if no custom pricing is found or if custom pricing is inactive.

    Args:
        db: Database session
        user_id: User's UUID
        service_name: Service identifier ('instant_ssn', 'manual_ssn')
        default_price: Default price to use if no custom pricing found

    Returns:
        Decimal: Custom price or default price
    """
    try:
        # Import here to avoid circular import
        from api.common.models_postgres import CustomPricing

        result = await db.execute(
            select(CustomPricing)
            .where(
                CustomPricing.user_id == user_id,
                CustomPricing.service_name == service_name,
                CustomPricing.is_active == True
            )
        )
        custom_pricing = result.scalar_one_or_none()

        if custom_pricing:
            return custom_pricing.price

        return default_price
    except Exception as e:
        # Log the error with details
        logger.error(
            f"Error getting custom pricing by user_id: user_id={user_id}, "
            f"service_name={service_name}, default_price={default_price}, "
            f"error={e}",
            exc_info=True
        )
        # On any error, return default price
        return default_price


async def get_price_for_user(
    db: AsyncSession,
    service_name: str,
    default_price: Decimal,
    user_id: Optional[UUID] = None,
    access_code: Optional[str] = None
) -> Decimal:
    """
    Unified function to get custom price for a user.
    Queries by user_id if provided, otherwise by access_code.
    Falls back to default_price if no custom pricing is found or if custom pricing is inactive.

    Args:
        db: Database session
        service_name: Service identifier ('instant_ssn', 'manual_ssn')
        default_price: Default price to use if no custom pricing found
        user_id: Optional user's UUID
        access_code: Optional user's access code

    Returns:
        Decimal: Custom price or default price
    """
    if user_id:
        return await get_user_price_by_id(db, user_id, service_name, default_price)
    elif access_code:
        return await get_user_price(db, access_code, service_name, default_price)
    else:
        return default_price


async def check_maintenance_mode(
    db: AsyncSession,
    service_name: str
) -> tuple[bool, Optional[str]]:
    """
    Check if a service is in maintenance mode.

    Args:
        db: Database session
        service_name: Service identifier ('instant_ssn', 'manual_ssn')

    Returns:
        tuple: (is_maintenance, message) - True if in maintenance with optional message
    """
    try:
        # Import here to avoid circular import
        from api.common.models_postgres import MaintenanceMode

        result = await db.execute(
            select(MaintenanceMode)
            .where(MaintenanceMode.service_name == service_name)
        )
        maintenance = result.scalar_one_or_none()

        if maintenance and maintenance.is_active:
            return (True, maintenance.message)

        return (False, None)
    except Exception as e:
        # Log the error with details
        logger.error(
            f"Error checking maintenance mode: service_name={service_name}, "
            f"error={e}",
            exc_info=True
        )
        # On any error, assume not in maintenance
        return (False, None)
