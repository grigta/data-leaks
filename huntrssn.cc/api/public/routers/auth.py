"""
Authentication router for Public API.
"""
import re
from fastapi import APIRouter, Depends, HTTPException, status, Body
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, update
from decimal import Decimal
import secrets
import logging
from api.common.database import get_postgres_session
from api.common.auth import (
    UserLogin, UserResponse, Token,
    hash_password, verify_password, create_access_token, generate_access_code
)
from api.common.models_postgres import User, Coupon, UserCoupon, CouponType
from api.public.dependencies import get_current_user
from api.common.validators import (
    validate_email, validate_telegram, validate_jabber,
    validate_coupon_code, validate_string_length
)
from api.common.sanitizers import sanitize_email, sanitize_string
from api.common.security_logger import SecurityEventLogger
from pydantic import BaseModel
from typing import Optional

logger = logging.getLogger(__name__)
security_logger = SecurityEventLogger("public_api.auth")
router = APIRouter()


async def _generate_unique_invitation_code(db: AsyncSession, user: User) -> str:
    """
    Generate and assign a unique invitation code to the user.

    Args:
        db: Database session
        user: User to assign invitation code to

    Returns:
        Generated invitation code

    Raises:
        HTTPException: If unable to generate unique code after max attempts
    """
    max_attempts = 10
    for attempt in range(max_attempts):
        try:
            # Generate alphanumeric code
            chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
            invitation_code = ''.join(secrets.choice(chars) for _ in range(15))

            # Check if code already exists
            result = await db.execute(select(User).where(User.invitation_code == invitation_code))
            if not result.scalar_one_or_none():
                # Code is unique, assign it
                user.invitation_code = invitation_code
                await db.commit()
                await db.refresh(user)
                logger.info(f"Generated invitation code for user {user.username}")
                return invitation_code
        except Exception as e:
            logger.error(f"Attempt {attempt + 1} to generate invitation code failed: {e}")
            if attempt == max_attempts - 1:
                await db.rollback()
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to generate unique invitation code"
                )
            continue

    # Should never reach here
    await db.rollback()
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Failed to generate unique invitation code"
    )


# Pydantic models for coupon validation
class ValidateCouponRequest(BaseModel):
    """Request model for coupon validation."""
    coupon_code: str


class ValidateCouponResponse(BaseModel):
    """Response model for coupon validation."""
    valid: bool
    coupon_type: Optional[str] = None
    bonus_percent: Optional[int] = None
    bonus_amount: Optional[Decimal] = None
    requires_registration: bool = False
    message: Optional[str] = None


class InvitationCodeResponse(BaseModel):
    """Response model for invitation code retrieval."""
    invitation_code: str


class InvitationStatsResponse(BaseModel):
    """Response model for invitation statistics."""
    invitation_code: str
    total_invited: int
    total_bonus_earned: Decimal


@router.post("/validate-coupon", response_model=ValidateCouponResponse)
async def validate_coupon(
    request: ValidateCouponRequest,
    db: AsyncSession = Depends(get_postgres_session)
):
    """
    Validate a coupon code for registration.

    Args:
        request: Coupon validation request with coupon_code
        db: PostgreSQL database session

    Returns:
        Validation result with coupon details
    """
    try:
        # Normalize coupon code
        normalized_code = request.coupon_code.strip().upper()

        # Validate coupon code format before database query
        is_valid, error = validate_coupon_code(normalized_code)
        if not is_valid:
            logger.warning(f"Invalid coupon code format rejected: {normalized_code[:20]}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error
            )

        # Query coupon by code
        result = await db.execute(
            select(Coupon).where(Coupon.code == normalized_code)
        )
        coupon = result.scalar_one_or_none()

        # Validate coupon
        if not coupon:
            return ValidateCouponResponse(
                valid=False,
                message="Coupon not found"
            )

        if not coupon.is_active:
            return ValidateCouponResponse(
                valid=False,
                message="Coupon is not active"
            )

        if coupon.current_uses >= coupon.max_uses:
            return ValidateCouponResponse(
                valid=False,
                message="Coupon usage limit reached"
            )

        # Coupon is valid
        return ValidateCouponResponse(
            valid=True,
            coupon_type=coupon.coupon_type.value,
            bonus_percent=coupon.bonus_percent if coupon.coupon_type == CouponType.percentage else None,
            bonus_amount=coupon.bonus_amount,
            requires_registration=coupon.requires_registration,
            message="Coupon is valid"
        )

    except Exception as e:
        logger.error(f"Error validating coupon: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to validate coupon"
        )


@router.get("/invitation-code", response_model=InvitationCodeResponse)
async def get_invitation_code(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_postgres_session)
):
    """
    Get or generate invitation code for current user.

    Args:
        current_user: Current authenticated user
        db: PostgreSQL database session

    Returns:
        User's invitation code

    Raises:
        HTTPException: If code generation fails
    """
    # If user already has invitation code, return it
    if current_user.invitation_code:
        return InvitationCodeResponse(invitation_code=current_user.invitation_code)

    # Generate unique invitation code using helper
    invitation_code = await _generate_unique_invitation_code(db, current_user)
    return InvitationCodeResponse(invitation_code=invitation_code)


@router.get("/invitation-stats", response_model=InvitationStatsResponse)
async def get_invitation_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_postgres_session)
):
    """
    Get invitation statistics for current user.

    Args:
        current_user: Current authenticated user
        db: PostgreSQL database session

    Returns:
        Invitation statistics (total invited users and bonus earned)

    Note:
        total_bonus_earned is calculated based on current INVITATION_BONUS_INVITER constant.
        This is a limitation - it does not reflect historical bonuses if the constant changes.
        For accurate tracking, implement an InvitationBonus table or extend Transaction model.
    """
    from api.common.pricing import INVITATION_BONUS_INVITER
    from sqlalchemy import func

    # Get or generate invitation code first
    if not current_user.invitation_code:
        await _generate_unique_invitation_code(db, current_user)

    # Count invited users
    result = await db.execute(
        select(func.count(User.id)).where(User.invited_by == current_user.id)
    )
    total_invited = result.scalar() or 0

    # Calculate total bonus earned (based on current constant - not historical)
    # TODO: Implement proper tracking via InvitationBonus table for accurate history
    total_bonus_earned = total_invited * INVITATION_BONUS_INVITER

    return InvitationStatsResponse(
        invitation_code=current_user.invitation_code,
        total_invited=total_invited,
        total_bonus_earned=total_bonus_earned
    )


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    coupon_code: Optional[str] = Body(None),
    invitation_code: Optional[str] = Body(None),
    db: AsyncSession = Depends(get_postgres_session)
):
    """
    Register a new user and generate access code.

    Args:
        coupon_code: Optional coupon code for registration bonuses
        invitation_code: Optional invitation code from another user
        db: PostgreSQL database session

    Returns:
        Created user data with access code

    Raises:
        HTTPException: If access code generation fails or coupon/invitation validation fails
    """
    # Generate unique access code
    max_attempts = 10
    for _ in range(max_attempts):
        access_code = generate_access_code()

        # Check if access code already exists
        result = await db.execute(select(User).where(User.access_code == access_code))
        if not result.scalar_one_or_none():
            break
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate unique access code"
        )

    # Generate unique username
    import uuid
    username = f"user_{uuid.uuid4().hex[:8]}"

    # Create new user with simple static hash (bcrypt doesn't support long strings)
    hashed_password = "$2b$12$dummy_hash_placeholder_for_access_code_users"

    # Set initial balance (will be updated if coupon provides bonus)
    initial_balance = Decimal('0.00')

    new_user = User(
        username=username,
        email=None,
        hashed_password=hashed_password,
        access_code=access_code,
        balance=initial_balance
    )

    db.add(new_user)
    await db.flush()  # Flush to get user ID for coupon linking

    # Process invitation code if provided (before coupon to allow stacking bonuses)
    if invitation_code:
        from api.common.pricing import INVITATION_BONUS_INVITEE, INVITATION_BONUS_INVITER
        from sqlalchemy import update

        # Normalize invitation code
        normalized_invitation = invitation_code.strip().upper()

        # Validate invitation code format (only A-Z0-9, max 20 chars)
        is_valid, error = validate_string_length(normalized_invitation, 1, 20, "invitation_code")
        if not is_valid:
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error
            )

        if not re.match(r'^[A-Z0-9]+$', normalized_invitation):
            logger.warning(f"Invalid invitation code format rejected: {normalized_invitation[:20]}")
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invitation code must contain only letters and digits"
            )

        # Query inviter by invitation_code
        inviter_result = await db.execute(
            select(User).where(User.invitation_code == normalized_invitation)
        )
        inviter = inviter_result.scalar_one_or_none()

        # Validate inviter exists
        if not inviter:
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid invitation code"
            )

        # Validate inviter is not banned
        if inviter.is_banned:
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invitation code is from a banned user"
            )

        # Set invited_by relationship
        new_user.invited_by = inviter.id
        new_user.invitation_bonus_received = True

        # Apply bonus to new user (invitee)
        new_user.balance += INVITATION_BONUS_INVITEE
        logger.info(f"Applied invitation bonus of ${INVITATION_BONUS_INVITEE} to new user {new_user.username}")

        # Apply bonus to inviter (atomic update to avoid race conditions)
        await db.execute(
            update(User)
            .where(User.id == inviter.id)
            .values(balance=User.balance + INVITATION_BONUS_INVITER)
        )
        logger.info(f"Applied inviter bonus of ${INVITATION_BONUS_INVITER} to user {inviter.username}")

    # Process coupon if provided
    if coupon_code:
        # Normalize coupon code
        normalized_code = coupon_code.strip().upper()

        # Validate coupon code format before database query
        is_valid, error = validate_coupon_code(normalized_code)
        if not is_valid:
            logger.warning(f"Invalid coupon code format rejected in register: {normalized_code[:20]}")
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error
            )

        # Query coupon by code
        coupon_result = await db.execute(
            select(Coupon).where(Coupon.code == normalized_code)
        )
        coupon = coupon_result.scalar_one_or_none()

        # Validate coupon
        if not coupon:
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid coupon code"
            )

        if not coupon.is_active:
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Coupon is not active"
            )

        if coupon.current_uses >= coupon.max_uses:
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Coupon usage limit reached"
            )

        # Check if coupon is registration type (for user experience - reject deposit coupons early)
        # Allow registration, registration_bonus, and fixed_amount coupons
        # Percentage coupons are blocked as they require a base amount to calculate
        if coupon.coupon_type not in [CouponType.registration, CouponType.registration_bonus, CouponType.fixed_amount]:
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This coupon can only be used for deposits, not registration"
            )

        # Verify that coupon has requires_registration when system enforces it
        # This prevents users from bypassing the requirement with a registration coupon
        # that doesn't have requires_registration flag set
        if coupon.requires_registration == False:
            # Check if system requires registration coupons
            check_result = await db.execute(
                select(Coupon).where(
                    and_(
                        Coupon.is_active == True,
                        Coupon.requires_registration == True,
                        Coupon.current_uses < Coupon.max_uses
                    )
                ).limit(1)
            )
            if check_result.scalar_one_or_none():
                await db.rollback()
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="This coupon cannot be used for registration"
                )

        # Increment coupon usage
        coupon.current_uses += 1

        # Create UserCoupon record
        user_coupon = UserCoupon(
            user_id=new_user.id,
            coupon_id=coupon.id
        )
        db.add(user_coupon)

        # Apply registration bonus if applicable
        # Both registration_bonus and fixed_amount coupons can provide bonus at registration
        if coupon.coupon_type in [CouponType.registration_bonus, CouponType.fixed_amount] and coupon.bonus_amount:
            new_user.balance = coupon.bonus_amount
            logger.info(f"Applied registration bonus of ${coupon.bonus_amount} to user {new_user.username}")

    await db.commit()
    await db.refresh(new_user)

    # Log successful registration
    logger.info(
        f"New user registered: {new_user.username}",
        extra={
            "user_id": str(new_user.id),
            "has_coupon": bool(coupon_code),
            "has_invitation": bool(invitation_code)
        }
    )

    return UserResponse(
        id=str(new_user.id),
        username=new_user.username,
        email=new_user.email,
        telegram=new_user.telegram,
        jabber=new_user.jabber,
        balance=float(new_user.balance),
        access_code=new_user.access_code,
        created_at=new_user.created_at
    )


@router.post("/login", response_model=Token)
async def login(
    login_data: UserLogin,
    db: AsyncSession = Depends(get_postgres_session)
):
    """
    Login with access code and get JWT token.

    Args:
        login_data: Login data with access code
        db: PostgreSQL database session

    Returns:
        JWT access token

    Raises:
        HTTPException: If access code is invalid
    """
    # Mask access code for logging (show only first 8 chars)
    masked_code = login_data.access_code[:8] + "..." if len(login_data.access_code) > 8 else "****"
    logger.info(f"Login attempt with access_code: {masked_code}")

    # Find user by access code
    result = await db.execute(select(User).where(User.access_code == login_data.access_code))
    user = result.scalar_one_or_none()

    if not user:
        security_logger.log_failed_login(
            username=masked_code,
            ip="unknown",  # IP is logged by middleware
            reason="access_code_not_found"
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access code",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Create JWT token
    access_token = create_access_token(
        data={"sub": user.username, "user_id": str(user.id)}
    )

    # Log successful login
    logger.info(
        f"Successful login for user {user.username}",
        extra={"user_id": str(user.id)}
    )

    return Token(access_token=access_token, token_type="bearer")


@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_postgres_session)
):
    """
    Get current user profile.

    Args:
        current_user: Current authenticated user

    Returns:
        User profile data
    """
    from api.common.pricing import get_user_price_by_id, get_default_instant_ssn_price

    default_instant_price = await get_default_instant_ssn_price(db)
    search_price = await get_user_price_by_id(
        db, current_user.id, 'instant_ssn', default_instant_price
    )

    return UserResponse(
        id=str(current_user.id),
        username=current_user.username,
        email=current_user.email,
        telegram=current_user.telegram,
        jabber=current_user.jabber,
        balance=float(current_user.balance),
        access_code=current_user.access_code,
        is_admin=current_user.is_admin,
        is_banned=current_user.is_banned,
        ban_reason=current_user.ban_reason,
        banned_at=current_user.banned_at,
        instant_ssn_rules_accepted=current_user.instant_ssn_rules_accepted,
        invitation_code=current_user.invitation_code,
        invited_by=str(current_user.invited_by) if current_user.invited_by else None,
        invitation_bonus_received=current_user.invitation_bonus_received,
        search_price=float(search_price),
        created_at=current_user.created_at
    )


@router.patch("/me", response_model=UserResponse)
async def update_profile(
    telegram: str | None = Body(None),
    jabber: str | None = Body(None),
    email: str | None = Body(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_postgres_session)
):
    """
    Update user profile fields.

    Args:
        telegram: Optional Telegram username
        jabber: Optional Jabber ID
        email: Optional email address
        current_user: Current authenticated user
        db: PostgreSQL database session

    Returns:
        Updated user profile data

    Raises:
        HTTPException: If email is already taken or validation fails
    """
    # Update fields if provided with validation and sanitization
    if telegram is not None:
        if telegram.strip():  # Non-empty telegram
            is_valid, error = validate_telegram(telegram)
            if not is_valid:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=error
                )
            # Sanitize and store
            current_user.telegram = sanitize_string(telegram.strip(), max_length=32)
        else:
            # Allow clearing the field
            current_user.telegram = None

    if jabber is not None:
        if jabber.strip():  # Non-empty jabber
            is_valid, error = validate_jabber(jabber)
            if not is_valid:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=error
                )
            # Sanitize and store
            current_user.jabber = sanitize_string(jabber.strip().lower(), max_length=254)
        else:
            # Allow clearing the field
            current_user.jabber = None

    if email is not None:
        if email.strip():  # Non-empty email
            # Validate email format
            is_valid, error = validate_email(email)
            if not is_valid:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=error
                )
            # Sanitize email
            sanitized_email = sanitize_email(email)
            # Check if email is already taken by another user
            result = await db.execute(
                select(User).where(User.email == sanitized_email, User.id != current_user.id)
            )
            if result.scalar_one_or_none():
                security_logger.log_suspicious_activity(
                    ip="unknown",  # IP is logged by middleware
                    activity_type="duplicate_email_attempt",
                    details={"email_domain": sanitized_email.split("@")[1] if "@" in sanitized_email else "unknown"}
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Email already registered"
                )
            current_user.email = sanitized_email
        else:
            # Allow clearing the field
            current_user.email = None

    await db.commit()
    await db.refresh(current_user)

    return UserResponse(
        id=str(current_user.id),
        username=current_user.username,
        email=current_user.email,
        telegram=current_user.telegram,
        jabber=current_user.jabber,
        balance=float(current_user.balance),
        access_code=current_user.access_code,
        is_admin=current_user.is_admin,
        is_banned=current_user.is_banned,
        ban_reason=current_user.ban_reason,
        banned_at=current_user.banned_at,
        instant_ssn_rules_accepted=current_user.instant_ssn_rules_accepted,
        invitation_code=current_user.invitation_code,
        invited_by=str(current_user.invited_by) if current_user.invited_by else None,
        invitation_bonus_received=current_user.invitation_bonus_received,
        created_at=current_user.created_at
    )


@router.post("/accept-instant-ssn-rules")
async def accept_instant_ssn_rules(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_postgres_session)
):
    """
    Accept Instant SSN search rules.

    Args:
        current_user: Current authenticated user
        db: PostgreSQL database session

    Returns:
        Success message
    """
    from datetime import datetime

    current_user.instant_ssn_rules_accepted = True
    current_user.instant_ssn_rules_accepted_at = datetime.utcnow()

    await db.commit()
    await db.refresh(current_user)

    return {"success": True, "message": "Rules accepted"}


@router.post("/change-password", status_code=status.HTTP_200_OK)
async def change_password(
    current_password: str = Body(..., min_length=8),
    new_password: str = Body(..., min_length=8),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_postgres_session)
):
    """
    Change user password (for users who have a password set).

    Args:
        current_password: Current password
        new_password: New password (minimum 8 characters)
        current_user: Current authenticated user
        db: PostgreSQL database session

    Returns:
        Success message

    Raises:
        HTTPException: If current password is incorrect or user doesn't have password
    """
    # Check if user has a real password (not dummy hash)
    if current_user.hashed_password.startswith("$2b$12$dummy_hash"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User has no password set. Use set-password endpoint first."
        )

    # Verify current password
    if not verify_password(current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is incorrect"
        )

    # Hash and set new password
    current_user.hashed_password = hash_password(new_password)
    await db.commit()

    return {"message": "Password changed successfully"}


@router.post("/set-password", status_code=status.HTTP_200_OK)
async def set_password(
    new_password: str = Body(..., min_length=8),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_postgres_session)
):
    """
    Set password for users who only have access code (first time password setup).

    Args:
        new_password: New password (minimum 8 characters)
        current_user: Current authenticated user
        db: PostgreSQL database session

    Returns:
        Success message

    Raises:
        HTTPException: If user already has a password set
    """
    # Check if user already has a real password
    if not current_user.hashed_password.startswith("$2b$12$dummy_hash"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User already has a password. Use change-password endpoint instead."
        )

    # Hash and set new password
    current_user.hashed_password = hash_password(new_password)
    await db.commit()

    return {"message": "Password set successfully"}
