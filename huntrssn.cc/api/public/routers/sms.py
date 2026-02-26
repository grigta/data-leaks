"""
SMS Service router - simple SMS code receiving service.

Flow:
1. User selects a service from dropdown
2. User is charged immediately (DaisySMS price + 20%, rounded to 0.05)
3. System gets phone number from DaisySMS
4. User polls for SMS code
5. When code received - shown to user
6. User can cancel for refund (if DaisySMS allows)
"""
import logging
from decimal import Decimal
from datetime import datetime, timedelta
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from pydantic import BaseModel, Field

from api.common.database import get_postgres_session
from api.common.models_postgres import (
    User,
    SMSRental,
    PhoneRentalStatus,
)
from api.public.dependencies import get_current_user
from api.common.daisysms_client import (
    create_daisysms_client,
    DaisySMSError,
    DaisySMSNoNumbersError,
    DaisySMSBalanceError,
    DaisySMSBadServiceError,
)
from api.common.daisysms_services import SERVICE_CODE_TO_NAME, get_service_name
from api.common.pricing import SMS_MARKUP, round_price_to_5_cents
from api.public.websocket import publish_user_notification, WebSocketEventType


router = APIRouter(tags=["SMS Service"])
logger = logging.getLogger(__name__)


# ============================================
# Pydantic Models
# ============================================

class SMSServiceItem(BaseModel):
    """SMS service item with pricing."""
    code: str
    name: str
    base_price: float
    user_price: float


class SMSServicesResponse(BaseModel):
    """Response model for SMS services list."""
    services: List[SMSServiceItem] = Field(default_factory=list)


class SMSGetNumberRequest(BaseModel):
    """Request model for getting SMS number."""
    service_code: str = Field(..., min_length=1, max_length=50)


class SMSGetNumberResponse(BaseModel):
    """Response model for get number."""
    success: bool
    rental_id: Optional[str] = None
    phone_number: Optional[str] = None
    service_name: Optional[str] = None
    user_price: Optional[float] = None
    expires_at: Optional[str] = None
    error: Optional[str] = None
    message: Optional[str] = None
    new_balance: Optional[float] = None


class SMSCheckCodeRequest(BaseModel):
    """Request model for checking SMS code."""
    rental_id: str = Field(..., min_length=1)


class SMSCheckCodeResponse(BaseModel):
    """Response model for check code."""
    success: bool
    status: str  # pending, code_received, cancelled, expired, finished
    sms_code: Optional[str] = None
    message: Optional[str] = None


class SMSCancelRequest(BaseModel):
    """Request model for cancelling rental."""
    rental_id: str = Field(..., min_length=1)


class SMSCancelResponse(BaseModel):
    """Response model for cancel."""
    success: bool
    refunded: bool
    refund_amount: Optional[float] = None
    new_balance: Optional[float] = None
    message: Optional[str] = None


class SMSFinishRequest(BaseModel):
    """Request model for finishing rental."""
    rental_id: str = Field(..., min_length=1)


class SMSFinishResponse(BaseModel):
    """Response model for finish."""
    success: bool
    message: Optional[str] = None


class SMSRentalHistoryItem(BaseModel):
    """Response model for rental history item."""
    id: str
    phone_number: str
    service_code: str
    service_name: str
    status: str
    base_price: float
    user_price: float
    sms_code: Optional[str] = None
    refunded: bool
    created_at: str
    expires_at: Optional[str] = None


class SMSRentalsResponse(BaseModel):
    """Response model for rental history."""
    rentals: List[SMSRentalHistoryItem] = Field(default_factory=list)
    total: int = 0


# ============================================
# Cache for services
# ============================================

_services_cache: List[SMSServiceItem] = []
_cache_time: Optional[datetime] = None
CACHE_TTL = 3600  # 1 hour


# ============================================
# Endpoints
# ============================================

@router.get("/services", response_model=SMSServicesResponse)
async def get_sms_services(
    current_user: User = Depends(get_current_user)
):
    """
    Get list of available SMS services with pricing.

    Returns services with both base_price (DaisySMS) and user_price (with 20% markup).
    """
    global _services_cache, _cache_time

    # Check cache
    if _services_cache and _cache_time:
        cache_age = (datetime.now() - _cache_time).total_seconds()
        if cache_age < CACHE_TTL:
            logger.debug("Returning cached SMS services list")
            return SMSServicesResponse(services=_services_cache)

    try:
        async with create_daisysms_client() as client:
            raw_services = await client.get_services()

            services = []
            for svc in raw_services:
                code = svc.get("code", "")
                name = svc.get("name", "") or get_service_name(code)
                base_price = float(svc.get("price", 0))

                # Skip services with 0 price
                if base_price <= 0:
                    continue

                # Calculate user price with markup and rounding
                user_price = float(round_price_to_5_cents(Decimal(str(base_price))))

                services.append(SMSServiceItem(
                    code=code,
                    name=name,
                    base_price=base_price,
                    user_price=user_price
                ))

            # Sort by name
            services.sort(key=lambda x: x.name.lower())

            # Update cache
            _services_cache = services
            _cache_time = datetime.now()

            logger.info(f"Loaded {len(services)} SMS services")
            return SMSServicesResponse(services=services)

    except DaisySMSError as e:
        logger.error(f"DaisySMS error loading services: {e}")
        # Return cached data if available
        if _services_cache:
            return SMSServicesResponse(services=_services_cache)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SMS service temporarily unavailable"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error loading SMS services: {e}")
        if _services_cache:
            return SMSServicesResponse(services=_services_cache)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to load SMS services"
        )


@router.post("/get-number", response_model=SMSGetNumberResponse)
async def get_sms_number(
    request: SMSGetNumberRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_postgres_session)
):
    """
    Get phone number for SMS.

    1. Calculate price (base * 1.2 rounded to 0.05)
    2. Check balance
    3. Charge user
    4. Get number from DaisySMS
    5. Create SMSRental record
    """
    service_code = request.service_code.strip()

    # Check if user is banned
    if current_user.is_banned:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account has been banned"
        )

    try:
        # Get service info and price
        async with create_daisysms_client() as client:
            raw_services = await client.get_services()

            # Find the service
            service_info = None
            for svc in raw_services:
                if svc.get("code") == service_code:
                    service_info = svc
                    break

            if not service_info:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid service code: {service_code}"
                )

            base_price = Decimal(str(service_info.get("price", 0)))
            if base_price <= 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Service not available"
                )

            # Calculate user price with markup
            user_price = round_price_to_5_cents(base_price)
            service_name = service_info.get("name") or get_service_name(service_code)

            # Check balance
            if current_user.balance < user_price:
                return SMSGetNumberResponse(
                    success=False,
                    error="Insufficient balance",
                    message=f"Required: ${user_price:.2f}, Available: ${current_user.balance:.2f}"
                )

            # Charge user BEFORE getting number
            current_user.balance -= user_price

            try:
                # Get phone number from DaisySMS
                phone_id, phone_number = await client.get_number(service_code)

                # Create rental record
                expires_at = datetime.utcnow() + timedelta(minutes=20)

                rental = SMSRental(
                    user_id=current_user.id,
                    daisysms_id=phone_id,
                    phone_number=phone_number,
                    service_code=service_code,
                    service_name=service_name,
                    status=PhoneRentalStatus.active,
                    base_price=base_price,
                    user_price=user_price,
                    expires_at=expires_at
                )
                db.add(rental)
                await db.commit()
                await db.refresh(rental)

                logger.info(
                    f"SMS rental created: user={current_user.username}, "
                    f"service={service_code}, phone={phone_number}, "
                    f"price=${user_price}"
                )

                # Notify about balance change via WebSocket
                await publish_user_notification(
                    str(current_user.id),
                    WebSocketEventType.BALANCE_UPDATED,
                    {"user_id": str(current_user.id), "new_balance": float(current_user.balance)}
                )

                return SMSGetNumberResponse(
                    success=True,
                    rental_id=str(rental.id),
                    phone_number=phone_number,
                    service_name=service_name,
                    user_price=float(user_price),
                    expires_at=expires_at.isoformat(),
                    new_balance=float(current_user.balance),
                    message="Phone number obtained successfully"
                )

            except DaisySMSNoNumbersError:
                # Refund if no numbers available
                current_user.balance += user_price
                await db.commit()
                return SMSGetNumberResponse(
                    success=False,
                    error="No numbers available",
                    message="No phone numbers available for this service. Please try again later.",
                    new_balance=float(current_user.balance)
                )

            except DaisySMSBalanceError:
                # Refund if DaisySMS balance issue
                current_user.balance += user_price
                await db.commit()
                logger.error("DaisySMS balance insufficient")
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Service temporarily unavailable"
                )

            except DaisySMSBadServiceError:
                # Refund if bad service
                current_user.balance += user_price
                await db.commit()
                return SMSGetNumberResponse(
                    success=False,
                    error="Invalid service",
                    message=f"Service code '{service_code}' is not valid",
                    new_balance=float(current_user.balance)
                )

            except DaisySMSError as e:
                # Refund on any DaisySMS error
                current_user.balance += user_price
                await db.commit()
                logger.error(f"DaisySMS error: {e}")
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="SMS service error. Please try again later."
                )

    except HTTPException:
        raise
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error getting SMS number: {e}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get phone number"
        )


@router.post("/check-code", response_model=SMSCheckCodeResponse)
async def check_sms_code(
    request: SMSCheckCodeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_postgres_session)
):
    """
    Check if SMS code has been received.

    Uses DaisySMS get_status() to check for code.
    """
    try:
        rental_id = UUID(request.rental_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid rental ID format"
        )

    # Find rental
    result = await db.execute(
        select(SMSRental)
        .where(
            SMSRental.id == rental_id,
            SMSRental.user_id == current_user.id
        )
    )
    rental = result.scalar_one_or_none()

    if not rental:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rental not found"
        )

    # If already has code, return it
    if rental.sms_code:
        return SMSCheckCodeResponse(
            success=True,
            status="code_received",
            sms_code=rental.sms_code,
            message="SMS code received"
        )

    # If not active, return current status
    if rental.status != PhoneRentalStatus.active:
        return SMSCheckCodeResponse(
            success=True,
            status=rental.status.value,
            message=f"Rental is {rental.status.value}"
        )

    # Check if expired
    if rental.expires_at and datetime.utcnow() > rental.expires_at:
        rental.status = PhoneRentalStatus.expired
        await db.commit()
        return SMSCheckCodeResponse(
            success=True,
            status="expired",
            message="Rental has expired"
        )

    # Poll DaisySMS for code
    try:
        async with create_daisysms_client() as client:
            daisysms_status, sms_code = await client.get_status(rental.daisysms_id)

            if daisysms_status == "STATUS_OK" and sms_code:
                # Code received!
                rental.sms_code = sms_code
                rental.code_received_at = datetime.utcnow()
                await db.commit()

                logger.info(
                    f"SMS code received: user={current_user.username}, "
                    f"rental={rental_id}, code={sms_code}"
                )

                return SMSCheckCodeResponse(
                    success=True,
                    status="code_received",
                    sms_code=sms_code,
                    message="SMS code received"
                )

            elif daisysms_status == "STATUS_CANCEL":
                rental.status = PhoneRentalStatus.cancelled
                await db.commit()
                return SMSCheckCodeResponse(
                    success=True,
                    status="cancelled",
                    message="Rental was cancelled"
                )

            else:
                # Still waiting
                return SMSCheckCodeResponse(
                    success=True,
                    status="pending",
                    message="Waiting for SMS..."
                )

    except DaisySMSError as e:
        logger.error(f"DaisySMS error checking code: {e}")
        return SMSCheckCodeResponse(
            success=False,
            status="error",
            message="Failed to check SMS status"
        )


@router.post("/cancel", response_model=SMSCancelResponse)
async def cancel_sms_rental(
    request: SMSCancelRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_postgres_session)
):
    """
    Cancel SMS rental.

    1. Call DaisySMS cancel_number()
    2. If successful, refund user
    3. Update rental status
    """
    try:
        rental_id = UUID(request.rental_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid rental ID format"
        )

    # Find rental
    result = await db.execute(
        select(SMSRental)
        .where(
            SMSRental.id == rental_id,
            SMSRental.user_id == current_user.id
        )
    )
    rental = result.scalar_one_or_none()

    if not rental:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rental not found"
        )

    # Check if already cancelled or finished
    if rental.status in [PhoneRentalStatus.cancelled, PhoneRentalStatus.finished]:
        return SMSCancelResponse(
            success=False,
            refunded=rental.refunded,
            message=f"Rental is already {rental.status.value}"
        )

    # Try to cancel in DaisySMS
    try:
        async with create_daisysms_client() as client:
            cancelled = await client.cancel_number(rental.daisysms_id)

            if cancelled:
                # Refund user
                refund_amount = rental.user_price
                current_user.balance += refund_amount
                rental.status = PhoneRentalStatus.cancelled
                rental.refunded = True
                await db.commit()

                logger.info(
                    f"SMS rental cancelled with refund: user={current_user.username}, "
                    f"rental={rental_id}, refund=${refund_amount}"
                )

                # Notify about balance change via WebSocket
                await publish_user_notification(
                    str(current_user.id),
                    WebSocketEventType.BALANCE_UPDATED,
                    {"user_id": str(current_user.id), "new_balance": float(current_user.balance)}
                )

                return SMSCancelResponse(
                    success=True,
                    refunded=True,
                    refund_amount=float(refund_amount),
                    new_balance=float(current_user.balance),
                    message="Rental cancelled and refunded"
                )
            else:
                # Could not cancel in DaisySMS (maybe already received SMS)
                rental.status = PhoneRentalStatus.finished
                await db.commit()

                return SMSCancelResponse(
                    success=True,
                    refunded=False,
                    message="Rental finished (could not cancel in DaisySMS)"
                )

    except DaisySMSError as e:
        logger.error(f"DaisySMS error cancelling: {e}")
        # Mark as finished without refund
        rental.status = PhoneRentalStatus.finished
        await db.commit()

        return SMSCancelResponse(
            success=True,
            refunded=False,
            message="Rental finished (DaisySMS error)"
        )


@router.post("/finish", response_model=SMSFinishResponse)
async def finish_sms_rental(
    request: SMSFinishRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_postgres_session)
):
    """
    Finish SMS rental (mark as complete, no refund).
    """
    try:
        rental_id = UUID(request.rental_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid rental ID format"
        )

    # Find rental
    result = await db.execute(
        select(SMSRental)
        .where(
            SMSRental.id == rental_id,
            SMSRental.user_id == current_user.id
        )
    )
    rental = result.scalar_one_or_none()

    if not rental:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rental not found"
        )

    # Check if already finished
    if rental.status in [PhoneRentalStatus.cancelled, PhoneRentalStatus.finished]:
        return SMSFinishResponse(
            success=True,
            message=f"Rental is already {rental.status.value}"
        )

    # Finish in DaisySMS
    try:
        async with create_daisysms_client() as client:
            await client.finish_number(rental.daisysms_id)
    except DaisySMSError as e:
        logger.warning(f"DaisySMS error finishing: {e}")
        # Continue anyway

    rental.status = PhoneRentalStatus.finished
    await db.commit()

    logger.info(f"SMS rental finished: user={current_user.username}, rental={rental_id}")

    return SMSFinishResponse(
        success=True,
        message="Rental finished"
    )


@router.get("/rentals", response_model=SMSRentalsResponse)
async def get_sms_rentals(
    limit: int = 20,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_postgres_session)
):
    """
    Get user's SMS rental history.
    """
    # Get total count
    count_result = await db.execute(
        select(SMSRental)
        .where(SMSRental.user_id == current_user.id)
    )
    total = len(count_result.scalars().all())

    # Get rentals with pagination
    result = await db.execute(
        select(SMSRental)
        .where(SMSRental.user_id == current_user.id)
        .order_by(desc(SMSRental.created_at))
        .offset(offset)
        .limit(min(limit, 50))  # Max 50 per request
    )
    rentals = result.scalars().all()

    # Convert to response format
    rental_items = []
    for rental in rentals:
        rental_items.append(SMSRentalHistoryItem(
            id=str(rental.id),
            phone_number=rental.phone_number,
            service_code=rental.service_code,
            service_name=rental.service_name,
            status=rental.status.value,
            base_price=float(rental.base_price),
            user_price=float(rental.user_price),
            sms_code=rental.sms_code,
            refunded=rental.refunded,
            created_at=rental.created_at.isoformat(),
            expires_at=rental.expires_at.isoformat() if rental.expires_at else None
        ))

    return SMSRentalsResponse(
        rentals=rental_items,
        total=total
    )
