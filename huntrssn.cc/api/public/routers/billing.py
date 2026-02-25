"""
Billing router for Public API (deposits and transactions).
"""
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from typing import List, Optional, Dict, Any
from decimal import Decimal
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict
import hashlib
import secrets
import json
import logging
import os
from api.common.database import get_postgres_session
from api.common.models_postgres import User, Transaction, TransactionStatus, PaymentMethod, Coupon, UserCoupon, CouponType
from api.common.cryptocurrencyapi_client import get_cryptocurrencyapi_client, CryptoCurrencyAPIError
from api.common.helket_client import get_helket_client, HelketError
from api.common.ffio_client import get_ffio_client, FFIOError, get_ffio_currency_code
from api.common.validators import validate_coupon_code
from api.public.dependencies import get_current_user, limiter
from api.public.websocket import publish_user_notification, WebSocketEventType
import asyncio
from fastapi import BackgroundTasks

logger = logging.getLogger(__name__)


router = APIRouter()


# Supported crypto currencies and networks
SUPPORTED_CURRENCIES = {"USDT", "BTC", "ETH", "BNB", "LTC"}
SUPPORTED_NETWORKS = {"TRC20", "ERC20", "BSC", "MAINNET"}
VALID_CRYPTO_COMBINATIONS = {
    ("USDT", "TRC20"), ("USDT", "ERC20"), ("USDT", "BSC"),
    ("ETH", "MAINNET"), ("BNB", "MAINNET"),
    ("BTC", "MAINNET"), ("LTC", "MAINNET")
}


def normalize_and_validate_crypto(currency: str, network: Optional[str] = None) -> tuple[str, str]:
    """
    Normalize and validate cryptocurrency and network combination.

    Args:
        currency: Cryptocurrency code (case-insensitive)
        network: Blockchain network (case-insensitive, optional)

    Returns:
        Tuple of (normalized_currency, normalized_network)

    Raises:
        ValueError: If combination is invalid
    """
    # Normalize to uppercase
    currency_norm = currency.upper() if currency else ""

    # Apply default network if not provided
    if not network:
        if currency_norm == "USDT":
            network_norm = "TRC20"
        elif currency_norm in ["BTC", "ETH", "BNB", "LTC"]:
            network_norm = "MAINNET"
        else:
            raise ValueError(f"Network must be specified for currency: {currency}")
    else:
        network_norm = network.upper()

    # Validate combination
    if (currency_norm, network_norm) not in VALID_CRYPTO_COMBINATIONS:
        raise ValueError(
            f"Invalid cryptocurrency/network combination: {currency_norm}/{network_norm}"
        )

    return currency_norm, network_norm


# Pydantic models
class CreateDepositRequest(BaseModel):
    """Request model for creating a deposit."""
    amount: Decimal = Field(..., gt=0, description="Deposit amount (must be positive)")
    payment_method: str = Field(default="crypto", description="Payment method (crypto, card, bank_transfer)")
    payment_provider: str = Field(default="cryptocurrencyapi", description="Payment provider: cryptocurrencyapi, helket, ffio")
    currency: str = Field(default="USDT", description="Cryptocurrency code")
    network: Optional[str] = Field(default=None, description="Blockchain network")
    coupon_code: Optional[str] = Field(default=None, max_length=20, description="Coupon code for bonus")


class TransactionResponse(BaseModel):
    """Response model for transaction."""
    id: str
    amount: float
    payment_method: str
    status: str
    payment_provider: Optional[str] = None
    external_transaction_id: Optional[str] = None
    payment_address: Optional[str] = None
    currency: Optional[str] = None
    network: Optional[str] = None
    metadata: Optional[Any] = None
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True
        json_encoders = {
            Decimal: lambda v: float(v) if v is not None else None
        }


class TransactionListResponse(BaseModel):
    """Response model for transaction list."""
    transactions: List[TransactionResponse]
    total_count: int


class ApplyCouponRequest(BaseModel):
    """Request model for applying a coupon."""
    code: str = Field(..., min_length=1, max_length=20, description="Coupon code")


class ApplyCouponResponse(BaseModel):
    """Response model for coupon application validation."""
    success: bool
    message: str
    bonus_percent: Optional[int]
    coupon_type: str
    bonus_amount: Optional[Decimal]
    requires_registration: bool


class ApplyCouponToBalanceRequest(BaseModel):
    """Request model for applying a coupon directly to balance."""
    code: str = Field(..., min_length=1, max_length=20, description="Coupon code")


class ApplyCouponToBalanceResponse(BaseModel):
    """Response model for coupon application to balance."""
    success: bool
    message: str
    bonus_amount: float
    new_balance: float

    class Config:
        json_encoders = {
            Decimal: lambda v: float(v) if v is not None else None
        }


class CryptoCurrencyAPIIPNPayload(BaseModel):
    """IPN payload from cryptocurrencyapi.net."""
    model_config = ConfigDict(populate_by_name=True)

    cryptocurrencyapi_net: int = Field(alias="cryptocurrencyapi.net")
    chain: str
    currency: str
    type: str  # "in" or "out"
    date: int  # Unix timestamp
    from_address: Optional[str] = Field(None, alias="from")
    to: str
    token: Optional[str] = None
    tokenContract: Optional[str] = None
    amount: str  # decimal as string
    fee: str
    txid: str
    pos: Optional[str] = None
    confirmation: int
    label: str  # contains transaction_id
    sign: str


def verify_cryptocurrencyapi_signature(payload: dict, signature: str, api_key: str) -> bool:
    """
    Verify IPN signature from cryptocurrencyapi.net using SHA-1 algorithm.

    Algorithm:
    1. Create copy of payload and remove 'sign' field
    2. Sort keys lexicographically
    3. Form string: key1=value1&key2=value2&...
    4. Append api_key to the end (without separator)
    5. Calculate SHA-1 hash
    6. Compare with signature using constant-time comparison

    Args:
        payload: IPN payload dict
        signature: Signature to verify
        api_key: CryptoCurrencyAPI API key

    Returns:
        True if signature is valid, False otherwise
    """
    # Create copy and remove sign field
    payload_copy = {k: v for k, v in payload.items() if k != "sign"}

    # Sort keys lexicographically
    sorted_keys = sorted(payload_copy.keys())

    # Form string
    parts = [f"{key}={payload_copy[key]}" for key in sorted_keys]
    message = "&".join(parts)

    # Append API key (without separator)
    message += api_key

    # Calculate SHA-1 hash
    computed_signature = hashlib.sha1(message.encode()).hexdigest()

    # Constant-time comparison
    return secrets.compare_digest(computed_signature, signature)


# Coupon endpoints
@router.post("/deposit/apply-coupon", response_model=ApplyCouponResponse)
async def apply_coupon(
    request: Request,
    response: Response,
    coupon_request: ApplyCouponRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_postgres_session)
):
    """
    Validate a coupon code before applying it to a deposit.

    This endpoint checks if:
    - Coupon exists and is active
    - Coupon has not reached usage limit
    - User has not already used this coupon

    Args:
        request: FastAPI Request object
        response: FastAPI Response object
        coupon_request: Coupon code to validate
        current_user: Current authenticated user
        db: PostgreSQL database session

    Returns:
        Validation result with bonus percentage

    Raises:
        HTTPException: If coupon is invalid or cannot be used
    """
    try:
        # Normalize coupon code: strip whitespace and convert to uppercase
        normalized_code = coupon_request.code.strip().upper()

        # Validate coupon code format before database query
        is_valid, error = validate_coupon_code(normalized_code)
        if not is_valid:
            logger.warning(f"Invalid coupon code format rejected in apply_coupon: {normalized_code[:20]}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error
            )

        # Query coupon by code (direct comparison with normalized code)
        result = await db.execute(
            select(Coupon).where(Coupon.code == normalized_code)
        )
        coupon = result.scalar_one_or_none()

        # Validation chain
        if not coupon:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Coupon not found"
            )

        if not coupon.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Coupon is not active"
            )

        if coupon.current_uses >= coupon.max_uses:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Coupon usage limit reached"
            )

        # Check if user has already used this coupon
        user_coupon_result = await db.execute(
            select(UserCoupon).where(
                UserCoupon.user_id == current_user.id,
                UserCoupon.coupon_id == coupon.id
            )
        )
        user_coupon = user_coupon_result.scalar_one_or_none()

        if user_coupon:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You have already used this coupon"
            )

        # All validations passed
        return ApplyCouponResponse(
            success=True,
            message="Coupon is valid",
            bonus_percent=coupon.bonus_percent,
            coupon_type=coupon.coupon_type.value,
            bonus_amount=coupon.bonus_amount,
            requires_registration=coupon.requires_registration
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error validating coupon: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to validate coupon"
        )


@router.post("/billing/apply-coupon", response_model=ApplyCouponToBalanceResponse)
async def apply_coupon_to_balance(
    request: Request,
    response: Response,
    coupon_request: ApplyCouponToBalanceRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_postgres_session)
):
    """
    Apply a fixed-amount coupon directly to user balance.

    This endpoint applies fixed-amount coupons directly to the user's balance
    without requiring a deposit. Only fixed_amount coupon type is supported.

    Args:
        request: FastAPI Request object
        response: FastAPI Response object
        coupon_request: Coupon code to apply
        current_user: Current authenticated user
        db: PostgreSQL database session

    Returns:
        Application result with bonus amount and new balance

    Raises:
        HTTPException: If coupon is invalid, wrong type, or cannot be used
    """
    try:
        # Normalize coupon code: strip whitespace and convert to uppercase
        normalized_code = coupon_request.code.strip().upper()

        # Validate coupon code format before database query
        is_valid, error = validate_coupon_code(normalized_code)
        if not is_valid:
            logger.warning(f"Invalid coupon code format rejected in apply_coupon_to_balance: {normalized_code[:20]}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error
            )

        # Query coupon by code (direct comparison with normalized code)
        result = await db.execute(
            select(Coupon).where(Coupon.code == normalized_code)
        )
        coupon = result.scalar_one_or_none()

        # Validation chain
        if not coupon:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Coupon not found"
            )

        if not coupon.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Coupon is not active"
            )

        if coupon.current_uses >= coupon.max_uses:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Coupon usage limit reached"
            )

        # Check if user has already used this coupon
        user_coupon_result = await db.execute(
            select(UserCoupon).where(
                UserCoupon.user_id == current_user.id,
                UserCoupon.coupon_id == coupon.id
            )
        )
        user_coupon = user_coupon_result.scalar_one_or_none()

        if user_coupon:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You have already used this coupon"
            )

        # Validate coupon type - only fixed_amount allowed
        if coupon.coupon_type == CouponType.percentage:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Percentage coupons can only be applied to deposits"
            )

        if coupon.coupon_type in [CouponType.registration, CouponType.registration_bonus]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This coupon can only be used during registration"
            )

        if coupon.coupon_type != CouponType.fixed_amount:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported coupon type: {coupon.coupon_type.value}"
            )

        # Validate bonus_amount exists
        if not coupon.bonus_amount:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Fixed amount coupon has no bonus amount configured"
            )

        bonus_amount = coupon.bonus_amount

        # Begin atomic update
        try:
            # Atomically update user balance
            stmt = (
                update(User)
                .where(User.id == current_user.id)
                .values(balance=User.balance + bonus_amount)
                .returning(User.balance)
            )
            balance_result = await db.execute(stmt)
            new_balance_row = balance_result.fetchone()

            if new_balance_row is None:
                logger.error(f"Failed to update balance for user {current_user.id}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to update balance"
                )

            new_balance = new_balance_row[0]

            # Increment coupon usage
            coupon.current_uses += 1

            # Create user-coupon relationship
            new_user_coupon = UserCoupon(
                user_id=current_user.id,
                coupon_id=coupon.id
            )
            db.add(new_user_coupon)

            # Commit transaction with IntegrityError handling for race conditions
            await db.commit()

            logger.info(
                f"Coupon {coupon.code} applied to user {current_user.id} balance: "
                f"bonus=${bonus_amount}, new_balance=${new_balance}"
            )

            # Notify about balance change via WebSocket
            await publish_user_notification(
                str(current_user.id),
                WebSocketEventType.BALANCE_UPDATED,
                {"user_id": str(current_user.id), "new_balance": float(new_balance)}
            )

            return ApplyCouponToBalanceResponse(
                success=True,
                message="Coupon applied successfully",
                bonus_amount=bonus_amount,
                new_balance=new_balance
            )

        except Exception as commit_error:
            from sqlalchemy.exc import IntegrityError
            await db.rollback()

            if isinstance(commit_error, IntegrityError):
                error_msg = str(commit_error.orig) if hasattr(commit_error, 'orig') else str(commit_error)

                # Check which constraint was violated
                if 'check_current_uses_within_limit' in error_msg:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Coupon usage limit reached"
                    )
                elif 'uq_user_coupon' in error_msg:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="You have already used this coupon"
                    )

            # Re-raise if it's not an expected integrity error
            raise

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error applying coupon to balance: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to apply coupon"
        )


# Deposit endpoints
@router.post("/deposit", response_model=TransactionResponse, status_code=status.HTTP_201_CREATED)
async def create_deposit(
    request: Request,
    response: Response,
    deposit_request: CreateDepositRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_postgres_session)
):
    """
    Create a deposit transaction.

    Args:
        request: FastAPI Request object
        response: FastAPI Response object
        deposit_request: Deposit details
        current_user: Current authenticated user
        db: PostgreSQL database session

    Returns:
        Created transaction

    Raises:
        HTTPException: If amount is invalid or payment method is not supported
    """
    # Validate amount
    if deposit_request.amount < Decimal('5.00'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Minimum deposit amount is $5.00"
        )

    if deposit_request.amount > Decimal('5000.00'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum deposit amount is $5,000.00"
        )

    # Validate payment method
    try:
        payment_method_enum = PaymentMethod(deposit_request.payment_method)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid payment method: {deposit_request.payment_method}. Must be one of: crypto, card, bank_transfer"
        )

    # Validate payment provider
    valid_providers = {"cryptocurrencyapi", "helket", "ffio"}
    if deposit_request.payment_provider not in valid_providers:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid payment provider: {deposit_request.payment_provider}. Must be one of: {', '.join(valid_providers)}"
        )

    # Normalize and validate crypto for crypto payments
    if payment_method_enum == PaymentMethod.crypto:
        try:
            normalized_currency, normalized_network = normalize_and_validate_crypto(
                deposit_request.currency,
                deposit_request.network
            )
            # Update request with normalized values
            deposit_request.currency = normalized_currency
            deposit_request.network = normalized_network
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e)
            )

    # Create transaction
    try:
        new_transaction = Transaction(
            user_id=current_user.id,
            amount=deposit_request.amount,
            payment_method=payment_method_enum,
            status=TransactionStatus.pending,
            payment_provider=deposit_request.payment_provider if payment_method_enum == PaymentMethod.crypto else None,
            currency=deposit_request.currency if payment_method_enum == PaymentMethod.crypto else None,
            network=deposit_request.network if payment_method_enum == PaymentMethod.crypto else None
        )

        # Apply coupon if provided
        if deposit_request.coupon_code:
            # Normalize coupon code: strip whitespace and convert to uppercase
            normalized_coupon_code = deposit_request.coupon_code.strip().upper()

            # Validate coupon code format before database query
            is_valid, error = validate_coupon_code(normalized_coupon_code)
            if not is_valid:
                logger.warning(f"Invalid coupon code format rejected in create_deposit: {normalized_coupon_code[:20]}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=error
                )

            # Query coupon by code (direct comparison with normalized code)
            coupon_result = await db.execute(
                select(Coupon).where(Coupon.code == normalized_coupon_code)
            )
            coupon = coupon_result.scalar_one_or_none()

            # Validate coupon
            if not coupon:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Coupon not found"
                )

            if not coupon.is_active:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Coupon is not active"
                )

            if coupon.current_uses >= coupon.max_uses:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Coupon usage limit reached"
                )

            # Check if user has already used this coupon
            user_coupon_check = await db.execute(
                select(UserCoupon).where(
                    UserCoupon.user_id == current_user.id,
                    UserCoupon.coupon_id == coupon.id
                )
            )
            existing_user_coupon = user_coupon_check.scalar_one_or_none()

            if existing_user_coupon:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="You have already used this coupon"
                )

            # Check if coupon is for registration only
            if coupon.coupon_type in [CouponType.registration, CouponType.registration_bonus]:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="This coupon can only be used during registration"
                )

            # Calculate bonus based on coupon type
            original_amount = new_transaction.amount
            if coupon.coupon_type == CouponType.percentage:
                # Percentage-based bonus
                bonus_amount = original_amount * (Decimal(coupon.bonus_percent) / Decimal(100))
                bonus_amount = bonus_amount.quantize(Decimal('0.01'))
            elif coupon.coupon_type == CouponType.fixed_amount:
                # Fixed amount bonus
                bonus_amount = coupon.bonus_amount
                if not bonus_amount:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Fixed amount coupon has no bonus amount configured"
                    )
                bonus_amount = bonus_amount.quantize(Decimal('0.01'))
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Unsupported coupon type for deposits: {coupon.coupon_type.value}"
                )

            new_amount = original_amount + bonus_amount
            new_amount = new_amount.quantize(Decimal('0.01'))

            # Update transaction amount and metadata (use rounded values)
            new_transaction.amount = new_amount
            new_transaction.payment_metadata = {
                "coupon_code": coupon.code,
                "coupon_type": coupon.coupon_type.value,
                "coupon_bonus_percent": coupon.bonus_percent if coupon.coupon_type == CouponType.percentage else None,
                "coupon_bonus_amount": str(bonus_amount),
                "original_amount": str(original_amount)
            }

            # Increment coupon usage and create user-coupon relationship
            coupon.current_uses += 1
            new_user_coupon = UserCoupon(
                user_id=current_user.id,
                coupon_id=coupon.id
            )
            db.add(new_user_coupon)

            logger.info(
                f"Coupon {coupon.code} applied to transaction: "
                f"original=${original_amount}, bonus=${bonus_amount}, total=${new_amount}"
            )

        db.add(new_transaction)

        # Commit transaction with IntegrityError handling for race conditions
        try:
            await db.commit()
            await db.refresh(new_transaction)
        except Exception as commit_error:
            from sqlalchemy.exc import IntegrityError
            await db.rollback()

            if isinstance(commit_error, IntegrityError):
                error_msg = str(commit_error.orig) if hasattr(commit_error, 'orig') else str(commit_error)

                # Check which constraint was violated
                if 'check_current_uses_within_limit' in error_msg:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Coupon usage limit reached"
                    )
                elif 'uq_user_coupon' in error_msg:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="You have already used this coupon"
                    )

            # Re-raise if it's not an expected integrity error
            raise

        # For crypto payments, create payment address via selected provider
        payment_address = None
        if payment_method_enum == PaymentMethod.crypto:
            try:
                # Route to appropriate payment provider
                if deposit_request.payment_provider == "cryptocurrencyapi":
                    # CryptoCurrencyAPI provider
                    ipn_webhook_url = os.getenv("IPN_WEBHOOK_URL", "")

                    if not ipn_webhook_url:
                        logger.warning("IPN_WEBHOOK_URL not configured, payment address creation skipped")
                    else:
                        client = get_cryptocurrencyapi_client()
                        async with client:
                            result = await client.create_payment_address(
                                currency=deposit_request.currency,
                                amount=new_transaction.amount,
                                label=str(new_transaction.id),
                                status_url=ipn_webhook_url,
                                network=deposit_request.network
                            )

                        payment_address = result.get("address")
                        qr_code = result.get("qr_code")

                        # Update transaction with payment address and metadata
                        new_transaction.payment_address = payment_address
                        existing_metadata = new_transaction.payment_metadata or {}
                        qr_metadata = {"qr": qr_code, "qr_code": qr_code} if qr_code else {}
                        new_transaction.payment_metadata = {**existing_metadata, **qr_metadata}

                        await db.commit()
                        await db.refresh(new_transaction)

                        logger.info(
                            f"CryptoCurrencyAPI payment address created for transaction {new_transaction.id}: "
                            f"{payment_address[:10]}...{payment_address[-4:]}"
                        )

                elif deposit_request.payment_provider == "helket":
                    # Helket provider
                    helket_webhook_url = os.getenv("HELKET_IPN_WEBHOOK_URL", "")

                    if not helket_webhook_url:
                        logger.warning("HELKET_IPN_WEBHOOK_URL not configured, invoice creation skipped")
                    else:
                        client = get_helket_client()
                        async with client:
                            result = await client.create_invoice(
                                currency=deposit_request.currency,
                                amount=new_transaction.amount,
                                label=str(new_transaction.id),
                                callback_url=helket_webhook_url,
                                network=deposit_request.network
                            )

                        payment_address = result.get("address")
                        qr_code = result.get("qr_code")
                        invoice_id = result.get("invoice_id")

                        # Update transaction with payment address and metadata
                        new_transaction.payment_address = payment_address
                        existing_metadata = new_transaction.payment_metadata or {}
                        helket_metadata = {
                            "qr": qr_code,
                            "qr_code": qr_code,
                            "invoice_id": invoice_id,
                            "provider": "helket"
                        }
                        if qr_code:
                            helket_metadata["qr"] = qr_code
                            helket_metadata["qr_code"] = qr_code
                        new_transaction.payment_metadata = {**existing_metadata, **helket_metadata}

                        await db.commit()
                        await db.refresh(new_transaction)

                        logger.info(
                            f"Helket invoice created for transaction {new_transaction.id}: "
                            f"{payment_address[:10]}...{payment_address[-4:]}, invoice_id={invoice_id}"
                        )

                elif deposit_request.payment_provider == "ffio":
                    # ff.io provider (no webhooks, requires polling)
                    # For ff.io, we create an exchange order from crypto to crypto (same currency)
                    try:
                        # Validate FFIO_PLATFORM_ADDRESS is configured before creating order
                        platform_address = os.getenv("FFIO_PLATFORM_ADDRESS", "")

                        if not platform_address:
                            logger.error("FFIO_PLATFORM_ADDRESS not configured - ff.io deposits unavailable")
                            await db.rollback()
                            raise HTTPException(
                                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                                detail="ff.io payment provider is temporarily unavailable. Please try another payment method."
                            )

                        # Get ff.io currency code
                        ffio_currency = get_ffio_currency_code(deposit_request.currency, deposit_request.network)

                        # For deposits, we typically do same-currency "exchange" (from -> to same)
                        # The to_address is our platform's receiving address
                        client = get_ffio_client()
                        async with client:
                            result = await client.create_order(
                                from_ccy=ffio_currency,
                                to_ccy=ffio_currency,  # Same currency for deposits
                                amount=new_transaction.amount,
                                direction="from",
                                type="fixed",
                                to_address=platform_address,
                                label=str(new_transaction.id)
                            )

                        payment_address = result.get("deposit_address")
                        order_id = result.get("order_id")
                        token = result.get("token")
                        full_data = result.get("full_data", {})

                        # Update transaction with payment address and metadata
                        new_transaction.payment_address = payment_address
                        existing_metadata = new_transaction.payment_metadata or {}
                        ffio_metadata = {
                            "order_id": order_id,
                            "token": token,
                            "provider": "ffio",
                            "full_order_data": full_data
                        }
                        new_transaction.payment_metadata = {**existing_metadata, **ffio_metadata}

                        await db.commit()
                        await db.refresh(new_transaction)

                        logger.info(
                            f"ff.io order created for transaction {new_transaction.id}: "
                            f"{payment_address[:10]}...{payment_address[-4:]}, order_id={order_id}"
                        )

                        # Start polling task for ff.io (no webhooks support)
                        # Import get_postgres_session to create session factory
                        from api.common.database import async_session_maker
                        background_tasks.add_task(
                            poll_ffio_order_status,
                            new_transaction.id,
                            async_session_maker
                        )

                    except FFIOError as e:
                        logger.error(f"Failed to create ff.io order: {str(e)}")
                        raise

            except (CryptoCurrencyAPIError, HelketError, FFIOError) as e:
                logger.error(f"Failed to create payment address with {deposit_request.payment_provider}: {str(e)}")
                # Check if payment address was created despite the error
                if not new_transaction.payment_address:
                    # Rollback transaction if no payment address was created
                    await db.rollback()
                    raise HTTPException(
                        status_code=status.HTTP_502_BAD_GATEWAY,
                        detail=f"Failed to create payment address with {deposit_request.payment_provider}. Please try again later or use a different payment method."
                    )

        return TransactionResponse(
            id=str(new_transaction.id),
            amount=new_transaction.amount,
            payment_method=new_transaction.payment_method.value,
            status=new_transaction.status.value,
            payment_provider=new_transaction.payment_provider,
            external_transaction_id=new_transaction.external_transaction_id,
            payment_address=new_transaction.payment_address,
            currency=new_transaction.currency,
            network=new_transaction.network,
            metadata=new_transaction.payment_metadata,
            created_at=new_transaction.created_at.isoformat(),
            updated_at=new_transaction.updated_at.isoformat()
        )

    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create deposit: {str(e)}"
        )


@router.get("/transactions", response_model=TransactionListResponse)
async def get_transactions(
    request: Request,
    response: Response,
    status_filter: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_postgres_session)
):
    """
    Get user's transactions.

    Args:
        request: FastAPI Request object
        response: FastAPI Response object
        status_filter: Filter by transaction status
        limit: Maximum number of transactions to return
        offset: Number of transactions to skip
        current_user: Current authenticated user
        db: PostgreSQL database session

    Returns:
        List of transactions with total count
    """
    # Build query
    query = select(Transaction).where(Transaction.user_id == current_user.id)

    # Apply status filter
    if status_filter:
        try:
            status_enum = TransactionStatus(status_filter)
            query = query.where(Transaction.status == status_enum)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status: {status_filter}"
            )

    # Apply ordering and pagination
    query = query.order_by(Transaction.created_at.desc()).offset(offset).limit(limit)

    # Execute query
    result = await db.execute(query)
    transactions = result.scalars().all()

    # Get total count
    from sqlalchemy import func
    count_query = select(func.count()).select_from(Transaction).where(Transaction.user_id == current_user.id)
    if status_filter:
        try:
            status_enum = TransactionStatus(status_filter)
            count_query = count_query.where(Transaction.status == status_enum)
        except ValueError:
            pass

    count_result = await db.execute(count_query)
    total_count = count_result.scalar() or 0

    return TransactionListResponse(
        transactions=[
            TransactionResponse(
                id=str(t.id),
                amount=t.amount,
                payment_method=t.payment_method.value,
                status=t.status.value,
                payment_provider=t.payment_provider,
                external_transaction_id=t.external_transaction_id,
                payment_address=t.payment_address,
                currency=t.currency,
                network=t.network,
                metadata=t.payment_metadata,
                created_at=t.created_at.isoformat(),
                updated_at=t.updated_at.isoformat()
            )
            for t in transactions
        ],
        total_count=total_count
    )


@router.get("/transactions/{transaction_id}", response_model=TransactionResponse)
async def get_transaction(
    request: Request,
    response: Response,
    transaction_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_postgres_session)
):
    """
    Get transaction details.

    Args:
        request: FastAPI Request object
        response: FastAPI Response object
        transaction_id: Transaction ID
        current_user: Current authenticated user
        db: PostgreSQL database session

    Returns:
        Transaction details

    Raises:
        HTTPException: If transaction not found or doesn't belong to user
    """
    # Find transaction
    result = await db.execute(
        select(Transaction).where(
            Transaction.id == transaction_id,
            Transaction.user_id == current_user.id
        )
    )
    transaction = result.scalar_one_or_none()

    if not transaction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transaction not found"
        )

    return TransactionResponse(
        id=str(transaction.id),
        amount=transaction.amount,
        payment_method=transaction.payment_method.value,
        status=transaction.status.value,
        payment_provider=transaction.payment_provider,
        external_transaction_id=transaction.external_transaction_id,
        payment_address=transaction.payment_address,
        currency=transaction.currency,
        network=transaction.network,
        metadata=transaction.payment_metadata,
        created_at=transaction.created_at.isoformat(),
        updated_at=transaction.updated_at.isoformat()
    )


# IPN endpoint (public, no authentication)
@router.post("/ipn/cryptocurrencyapi")
async def cryptocurrencyapi_ipn(
    request: Request,
    db: AsyncSession = Depends(get_postgres_session)
):
    """
    IPN webhook endpoint for cryptocurrencyapi.net.

    This endpoint is PUBLIC (no JWT authentication) and receives payment
    notifications from cryptocurrencyapi.net.

    Always returns 200 OK as required by the provider.

    Args:
        request: FastAPI Request object
        db: PostgreSQL database session

    Returns:
        JSON response with status
    """
    try:
        # Parse raw JSON body
        body = await request.body()
        payload = json.loads(body.decode())

        # Log IPN receipt (mask sensitive data)
        masked_txid = payload.get("txid", "")
        if len(masked_txid) > 4:
            masked_txid = f"...{masked_txid[-4:]}"
        logger.info(f"IPN received from cryptocurrencyapi.net: txid={masked_txid}")

        # Get API key from environment
        api_key = os.getenv("CRYPTOCURRENCYAPI_KEY", "")
        if not api_key:
            logger.error("CRYPTOCURRENCYAPI_KEY not configured")
            return {"status": "error", "message": "Server configuration error"}

        # Verify signature
        signature = payload.get("sign", "")
        if not verify_cryptocurrencyapi_signature(payload, signature, api_key):
            logger.warning(f"Invalid IPN signature for txid={masked_txid}")
            return {"status": "error", "message": "Invalid signature"}

        # Parse payload into model
        ipn_payload = CryptoCurrencyAPIIPNPayload(**payload)

        # Extract transaction_id from label
        transaction_id_str = ipn_payload.label
        try:
            transaction_id = UUID(transaction_id_str)
        except ValueError:
            logger.error(f"Invalid transaction_id in label: {transaction_id_str}")
            return {"status": "error", "message": "Invalid label format"}

        # Find transaction
        result = await db.execute(
            select(Transaction).where(Transaction.id == transaction_id)
        )
        transaction = result.scalar_one_or_none()

        if not transaction:
            logger.error(f"Transaction not found: {transaction_id}")
            return {"status": "error", "message": "Transaction not found"}

        # Check idempotency
        if (transaction.status == TransactionStatus.paid and
            transaction.external_transaction_id == ipn_payload.txid):
            logger.info(f"Duplicate IPN for transaction {transaction_id}, already processed")
            return {"status": "success", "message": "Already processed"}

        # Merge metadata instead of overwriting to preserve initial fields (QR codes, etc.)
        existing_metadata = transaction.payment_metadata or {}
        ipn_data = payload.copy()

        # Preserve existing fields (qr, qr_code) and add IPN data under 'ipn' key
        merged_metadata = {**existing_metadata, "ipn": ipn_data}
        transaction.payment_metadata = merged_metadata

        # Process payment if conditions are met
        if (ipn_payload.confirmation >= 1 and
            ipn_payload.type == "in" and
            transaction.status == TransactionStatus.pending):

            # Begin atomic update
            try:
                # Update transaction status and external_transaction_id
                transaction.status = TransactionStatus.paid
                transaction.external_transaction_id = ipn_payload.txid

                # Atomically update user balance
                stmt = (
                    update(User)
                    .where(User.id == transaction.user_id)
                    .values(balance=User.balance + transaction.amount)
                    .returning(User.balance)
                )
                balance_result = await db.execute(stmt)
                new_balance_row = balance_result.fetchone()

                if new_balance_row is None:
                    logger.error(f"Failed to update balance for user {transaction.user_id}")
                    return {"status": "error", "message": "Failed to update balance"}

                new_balance = new_balance_row[0]

                # Commit transaction
                await db.commit()

                logger.info(
                    f"Payment processed for transaction {transaction_id}: "
                    f"amount=${transaction.amount}, new_balance=${new_balance}"
                )

                # Notify about balance change via WebSocket
                await publish_user_notification(
                    str(transaction.user_id),
                    WebSocketEventType.BALANCE_UPDATED,
                    {"user_id": str(transaction.user_id), "new_balance": float(new_balance)}
                )

                return {"status": "success", "message": "Payment processed"}

            except Exception as e:
                await db.rollback()
                logger.error(f"Error processing payment: {str(e)}", exc_info=True)
                return {"status": "error", "message": str(e)}

        else:
            # Just update metadata, don't process payment yet
            await db.commit()

            if ipn_payload.confirmation < 1:
                logger.info(f"Waiting for confirmations: {ipn_payload.confirmation}")
                return {"status": "pending", "message": "Waiting for confirmations"}
            elif ipn_payload.type != "in":
                logger.info(f"Ignoring outgoing transaction: type={ipn_payload.type}")
                return {"status": "success", "message": "Outgoing transaction ignored"}
            else:
                logger.info(f"Transaction already processed or not pending")
                return {"status": "success", "message": "No action needed"}

    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in IPN: {str(e)}")
        return {"status": "error", "message": "Invalid JSON"}

    except Exception as e:
        logger.error(f"Unexpected error in IPN: {str(e)}", exc_info=True)
        return {"status": "error", "message": str(e)}


# Helket IPN endpoint (public, no authentication)
@router.post("/ipn/helket")
async def helket_ipn(
    request: Request,
    db: AsyncSession = Depends(get_postgres_session)
):
    """
    IPN webhook endpoint for Helket.

    This endpoint is PUBLIC (no JWT authentication) and receives payment
    notifications from Helket API.

    Always returns 200 OK as required by the provider.

    Args:
        request: FastAPI Request object
        db: PostgreSQL database session

    Returns:
        JSON response with status
    """
    try:
        # Parse raw JSON body
        body = await request.body()
        payload_str = body.decode()
        payload = json.loads(payload_str)

        # Get signature from header (Helket typically uses X-Signature or similar)
        signature = request.headers.get("X-Signature", "") or request.headers.get("X-Helket-Signature", "")

        logger.info(f"IPN received from Helket: invoice_id={payload.get('invoice_id')}")

        # Get webhook secret from environment
        webhook_secret = os.getenv("HELKET_WEBHOOK_SECRET", "")
        if not webhook_secret:
            logger.error("HELKET_WEBHOOK_SECRET not configured")
            return {"status": "error", "message": "Server configuration error"}

        # Verify signature
        from api.common.helket_client import HelketClient
        if not HelketClient.verify_webhook_signature(payload_str, signature, webhook_secret):
            logger.warning(f"Invalid Helket webhook signature for invoice_id={payload.get('invoice_id')}")
            return {"status": "error", "message": "Invalid signature"}

        # Extract transaction_id from label or custom field
        transaction_id_str = payload.get("label") or payload.get("merchant_reference")
        if not transaction_id_str:
            logger.error("No transaction identifier in Helket webhook")
            return {"status": "error", "message": "Missing transaction identifier"}

        try:
            transaction_id = UUID(transaction_id_str)
        except ValueError:
            logger.error(f"Invalid transaction_id in Helket webhook: {transaction_id_str}")
            return {"status": "error", "message": "Invalid label format"}

        # Find transaction
        result = await db.execute(
            select(Transaction).where(Transaction.id == transaction_id)
        )
        transaction = result.scalar_one_or_none()

        if not transaction:
            logger.error(f"Transaction not found: {transaction_id}")
            return {"status": "error", "message": "Transaction not found"}

        # Check idempotency
        external_tx_id = payload.get("txid") or payload.get("transaction_hash") or payload.get("invoice_id")
        if (transaction.status == TransactionStatus.paid and
            transaction.external_transaction_id == external_tx_id):
            logger.info(f"Duplicate Helket IPN for transaction {transaction_id}, already processed")
            return {"status": "success", "message": "Already processed"}

        # Merge metadata
        existing_metadata = transaction.payment_metadata or {}
        helket_ipn_data = payload.copy()
        merged_metadata = {**existing_metadata, "helket_ipn": helket_ipn_data}
        transaction.payment_metadata = merged_metadata

        # Process payment if confirmed
        payment_status = payload.get("status", "").lower()
        if payment_status in ["completed", "paid", "confirmed"] and transaction.status == TransactionStatus.pending:
            # Begin atomic update
            try:
                # Update transaction status
                transaction.status = TransactionStatus.paid
                transaction.external_transaction_id = external_tx_id

                # Atomically update user balance
                stmt = (
                    update(User)
                    .where(User.id == transaction.user_id)
                    .values(balance=User.balance + transaction.amount)
                    .returning(User.balance)
                )
                balance_result = await db.execute(stmt)
                new_balance_row = balance_result.fetchone()

                if new_balance_row is None:
                    logger.error(f"Failed to update balance for user {transaction.user_id}")
                    return {"status": "error", "message": "Failed to update balance"}

                new_balance = new_balance_row[0]

                # Commit transaction
                await db.commit()

                logger.info(
                    f"Helket payment processed for transaction {transaction_id}: "
                    f"amount=${transaction.amount}, new_balance=${new_balance}"
                )

                # Notify about balance change via WebSocket
                await publish_user_notification(
                    str(transaction.user_id),
                    WebSocketEventType.BALANCE_UPDATED,
                    {"user_id": str(transaction.user_id), "new_balance": float(new_balance)}
                )

                return {"status": "success", "message": "Payment processed"}

            except Exception as e:
                await db.rollback()
                logger.error(f"Error processing Helket payment: {str(e)}", exc_info=True)
                return {"status": "error", "message": str(e)}

        else:
            # Just update metadata
            await db.commit()

            logger.info(f"Helket webhook received but payment not confirmed yet: status={payment_status}")
            return {"status": "pending", "message": f"Payment status: {payment_status}"}

    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in Helket IPN: {str(e)}")
        return {"status": "error", "message": "Invalid JSON"}

    except Exception as e:
        logger.error(f"Unexpected error in Helket IPN: {str(e)}", exc_info=True)
        return {"status": "error", "message": str(e)}


# Background task for ff.io order status polling
async def poll_ffio_order_status(transaction_id: UUID, db_session_factory):
    """
    Background task to poll ff.io order status.

    ff.io does not support webhooks, so we need to poll the API periodically
    to check if the payment has been completed.

    Args:
        transaction_id: Transaction ID to poll
        db_session_factory: Factory function to create new DB session
    """
    max_attempts = 60  # Poll for up to 1 hour (60 attempts * 60 seconds)
    attempt = 0

    logger.info(f"Starting ff.io order polling for transaction {transaction_id}")

    while attempt < max_attempts:
        attempt += 1
        await asyncio.sleep(60)  # Wait 60 seconds between polls

        try:
            # Create new DB session for this iteration
            async with db_session_factory() as db:
                # Get transaction
                result = await db.execute(
                    select(Transaction).where(Transaction.id == transaction_id)
                )
                transaction = result.scalar_one_or_none()

                if not transaction:
                    logger.error(f"Transaction {transaction_id} not found in polling task")
                    return

                # If already paid, stop polling
                if transaction.status == TransactionStatus.paid:
                    logger.info(f"Transaction {transaction_id} already paid, stopping poll")
                    return

                # Get order_id and token from metadata
                metadata = transaction.payment_metadata or {}
                order_id = metadata.get("order_id")
                token = metadata.get("token")

                if not order_id or not token:
                    logger.error(f"Missing order_id or token in transaction {transaction_id} metadata")
                    return

                # Check order status
                client = get_ffio_client()
                async with client:
                    status_result = await client.get_order_status(order_id, token)

                order_data = status_result.get("data", {})
                status = order_data.get("status", "").lower()

                logger.info(f"ff.io order {order_id} status: {status} (attempt {attempt}/{max_attempts})")

                # Update metadata with latest status
                metadata["latest_status"] = status
                metadata["last_poll_attempt"] = attempt
                transaction.payment_metadata = metadata

                if status in ["completed", "success"]:
                    # Payment completed
                    try:
                        transaction.status = TransactionStatus.paid
                        transaction.external_transaction_id = order_id

                        # Atomically update user balance
                        stmt = (
                            update(User)
                            .where(User.id == transaction.user_id)
                            .values(balance=User.balance + transaction.amount)
                            .returning(User.balance)
                        )
                        balance_result = await db.execute(stmt)
                        new_balance_row = balance_result.fetchone()

                        if new_balance_row is None:
                            logger.error(f"Failed to update balance for user {transaction.user_id}")
                            await db.commit()  # Still commit metadata update
                            return

                        new_balance = new_balance_row[0]
                        await db.commit()

                        logger.info(
                            f"ff.io payment completed for transaction {transaction_id}: "
                            f"amount=${transaction.amount}, new_balance=${new_balance}"
                        )

                        # Notify about balance change via WebSocket
                        await publish_user_notification(
                            str(transaction.user_id),
                            WebSocketEventType.BALANCE_UPDATED,
                            {"user_id": str(transaction.user_id), "new_balance": float(new_balance)}
                        )
                        return  # Stop polling

                    except Exception as e:
                        await db.rollback()
                        logger.error(f"Error processing ff.io payment: {str(e)}", exc_info=True)
                        return

                elif status in ["failed", "expired", "refunded"]:
                    # Payment failed
                    transaction.status = TransactionStatus.failed
                    metadata["failure_reason"] = status
                    transaction.payment_metadata = metadata
                    await db.commit()

                    logger.warning(f"ff.io order {order_id} failed with status: {status}")
                    return  # Stop polling

                else:
                    # Still pending, continue polling
                    await db.commit()

        except FFIOError as e:
            logger.error(f"ff.io API error while polling transaction {transaction_id}: {str(e)}")
            # Continue polling despite errors
            continue

        except Exception as e:
            logger.error(f"Unexpected error in ff.io polling for transaction {transaction_id}: {str(e)}", exc_info=True)
            # Continue polling despite errors
            continue

    # Max attempts reached
    logger.warning(f"ff.io polling timeout for transaction {transaction_id} after {max_attempts} attempts")
