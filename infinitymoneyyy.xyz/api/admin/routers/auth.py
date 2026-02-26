"""
Admin authentication router with 2FA support.
"""
import pyotp
import qrcode
import io
import base64
from datetime import timedelta, datetime
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List
from uuid import UUID
from decimal import Decimal
import secrets
import logging

from api.common.database import get_postgres_session as get_db
from api.common.models_postgres import User, WorkerRegistrationRequest, RegistrationStatus
from api.common.auth import (
    verify_password,
    create_access_token,
    AdminLoginRequest,
    AdminUserResponse,
    Token,
    hash_password
)
from api.admin.dependencies import (
    oauth2_scheme_admin,
    get_current_admin_user,
    get_current_admin_user_optional,
)
from api.admin.websocket import ws_manager

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Admin Authentication"])


class AdminUserResponse(BaseModel):
    """Admin user info response."""
    username: str
    email: str
    has_totp: bool
    is_admin: bool
    worker_role: bool


@router.get("/me", response_model=AdminUserResponse)
async def get_admin_me(
    current_user: User = Depends(get_current_admin_user)
):
    """
    Get current authenticated admin or worker user information.

    Returns:
        User information including 2FA status
    """
    return AdminUserResponse(
        username=current_user.username,
        email=current_user.email or "",
        has_totp=bool(current_user.totp_secret),
        is_admin=current_user.is_admin,
        worker_role=current_user.worker_role
    )


# Pydantic models for 2FA
class TwoFactorVerifyRequest(BaseModel):
    """2FA verification request."""
    token: str = Field(description="Temporary token from login")
    code: str = Field(min_length=6, max_length=6, description="TOTP code from authenticator app")


class TwoFactorSetupResponse(BaseModel):
    """2FA setup response with provisioning URI and QR code."""
    secret: str
    provisioning_uri: str
    qr_code: str
    message: str


class TwoFactorConfirmRequest(BaseModel):
    """2FA confirmation request."""
    code: str = Field(min_length=6, max_length=6, description="TOTP code from authenticator app")


class PasswordVerifyRequest(BaseModel):
    """Password verification request for disabling 2FA."""
    password: str = Field(min_length=8)


# Worker Registration Models
class WorkerRegisterRequest(BaseModel):
    """Worker registration request."""
    username: str = Field(min_length=3, max_length=50, description="Username for worker account")
    email: EmailStr = Field(description="Email address")
    password: str = Field(min_length=8, description="Password for worker account")


class WorkerRegisterResponse(BaseModel):
    """Worker registration response with access code."""
    message: str
    access_code: str
    status: str = "pending"




async def generate_worker_access_code(db: AsyncSession) -> str:
    """
    Generate a unique 15-character alphanumeric access code for workers.

    Uses secrets.choice for deterministic generation of exactly 15 characters.
    Checks database for uniqueness against both User.access_code and
    WorkerRegistrationRequest.access_code tables.
    """
    import string
    alphabet = string.ascii_uppercase + string.digits
    max_attempts = 10

    for _ in range(max_attempts):
        # Generate exactly 15 random characters
        code = ''.join(secrets.choice(alphabet) for _ in range(15))

        # Check uniqueness in User table
        user_result = await db.execute(
            select(User).where(User.access_code == code)
        )
        existing_user = user_result.scalar_one_or_none()

        # Check uniqueness in WorkerRegistrationRequest table
        request_result = await db.execute(
            select(WorkerRegistrationRequest).where(WorkerRegistrationRequest.access_code == code)
        )
        existing_request = request_result.scalar_one_or_none()

        if not existing_user and not existing_request:
            return code

    # Fallback: timestamp-based code
    from datetime import datetime
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    return f"WRK{timestamp}"[:15]


@router.post("/login", response_model=Token)
async def admin_login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db)
):
    """
    Admin login endpoint. Returns temporary token if 2FA is enabled.

    Returns:
        - If 2FA not enabled: Full access token
        - If 2FA enabled: Temporary token (5 min) with temp_2fa flag
    """
    # Find user by username
    result = await db.execute(
        select(User).where(User.username == form_data.username)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Verify password
    if not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check if user has admin privileges
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access forbidden: Admin privileges required"
        )

    # If 2FA is enabled, return temporary token
    if user.totp_secret:
        temp_token_data = {
            "sub": user.username,
            "user_id": str(user.id),
            "temp_2fa": True,
            "is_admin": user.is_admin,
            "worker_role": user.worker_role
        }
        temp_token = create_access_token(
            temp_token_data,
            expires_delta=timedelta(minutes=5)
        )
        return Token(access_token=temp_token, token_type="bearer")

    # If 2FA not enabled, return full access token
    token_data = {
        "sub": user.username,
        "user_id": str(user.id),
        "is_admin": user.is_admin,
        "worker_role": user.worker_role
    }
    access_token = create_access_token(token_data)
    return Token(access_token=access_token, token_type="bearer")


@router.post("/verify-2fa", response_model=Token)
async def verify_two_factor(
    request: TwoFactorVerifyRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Verify TOTP code and issue full admin access token.

    Args:
        request: Contains temporary token and TOTP code

    Returns:
        Full admin access token with is_admin=true claim
    """
    from api.common.auth import decode_access_token

    # Decode temporary token
    try:
        payload = decode_access_token(request.token)
    except HTTPException:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )

    # Check if token is temporary 2FA token
    if not payload.get("temp_2fa"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token is not a temporary 2FA token"
        )

    # Get user
    user_id = payload.get("user_id")
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()

    if not user or not user.is_admin or not user.totp_secret:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid user or 2FA not configured"
        )

    # Verify TOTP code
    totp = pyotp.TOTP(user.totp_secret)
    if not totp.verify(request.code, valid_window=1):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid TOTP code"
        )

    # Issue full admin token
    token_data = {
        "sub": user.username,
        "user_id": str(user.id),
        "is_admin": user.is_admin,
        "worker_role": user.worker_role
    }
    access_token = create_access_token(token_data)
    return Token(access_token=access_token, token_type="bearer")


@router.post("/setup-2fa", response_model=TwoFactorSetupResponse)
async def setup_two_factor(
    current_user: User = Depends(get_current_admin_user_optional),
    db: AsyncSession = Depends(get_db)
):
    """
    Initialize 2FA setup by generating TOTP secret and provisioning URI.

    Note: This endpoint requires authentication but not 2FA verification.
    Use get_current_admin_user_optional dependency.

    Returns:
        Secret and provisioning URI for QR code generation
    """

    # Защита от перезаписи существующего 2FA
    # Предупреждение: если пользователь уже имеет активный 2FA, требуется подтверждение
    if current_user.totp_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="2FA is already enabled. Please disable it first before setting up again."
        )

    # Generate new TOTP secret
    secret = pyotp.random_base32()

    # Generate provisioning URI for QR code
    totp = pyotp.TOTP(secret)
    provisioning_uri = totp.provisioning_uri(
        name=current_user.email,
        issuer_name="SSN Admin Portal"
    )

    # Generate QR code as base64 PNG
    qr = qrcode.make(provisioning_uri)
    buf = io.BytesIO()
    qr.save(buf, format="PNG")
    qr_base64 = base64.b64encode(buf.getvalue()).decode("utf-8")

    # Store secret in database so it persists across requests
    current_user.totp_secret = secret
    await db.commit()
    await db.refresh(current_user)

    return TwoFactorSetupResponse(
        secret=secret,
        provisioning_uri=provisioning_uri,
        qr_code=f"data:image/png;base64,{qr_base64}",
        message="Scan the QR code with your authenticator app and confirm with a code"
    )


@router.post("/confirm-2fa", response_model=dict)
async def confirm_two_factor(
    request: TwoFactorConfirmRequest,
    current_user: User = Depends(get_current_admin_user_optional),
    db: AsyncSession = Depends(get_db)
):
    """
    Confirm 2FA setup by verifying TOTP code and saving secret to database.

    Args:
        request: Contains TOTP code from authenticator app

    Returns:
        Success message
    """

    # Check if user has a pending TOTP secret
    if not current_user.totp_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No 2FA setup in progress. Please call /setup-2fa first"
        )

    # Verify TOTP code
    totp = pyotp.TOTP(current_user.totp_secret)
    if not totp.verify(request.code, valid_window=1):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid TOTP code. Please try again"
        )

    # Secret already committed in setup-2fa, just return success
    return {
        "message": "2FA successfully enabled",
        "totp_enabled": True
    }


@router.post("/disable-2fa", response_model=dict)
async def disable_two_factor(
    request: PasswordVerifyRequest,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Disable 2FA by verifying password and clearing TOTP secret.

    Args:
        request: Contains user password for verification

    Returns:
        Success message
    """

    # Verify password
    if not verify_password(request.password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect password"
        )

    # Clear TOTP secret
    current_user.totp_secret = None
    await db.commit()
    await db.refresh(current_user)

    return {
        "message": "2FA successfully disabled",
        "totp_enabled": False
    }


# Worker Registration Endpoints
@router.post("/register-worker", response_model=WorkerRegisterResponse, status_code=status.HTTP_201_CREATED)
async def register_worker(
    request: WorkerRegisterRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Register a new worker (public endpoint - no authentication required).

    Creates a pending worker registration request with a unique 15-character access code.
    Admin approval is required before the worker can log in.

    Returns:
        Access code and pending status
    """
    try:
        # Validate username uniqueness (case-insensitive)
        user_result = await db.execute(
            select(User).where(func.lower(User.username) == request.username.lower())
        )
        if user_result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Username '{request.username}' already exists"
            )

        # Validate email uniqueness (case-insensitive)
        email_result = await db.execute(
            select(User).where(func.lower(User.email) == request.email.lower())
        )
        if email_result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Email '{request.email}' already exists"
            )

        # Check for pending registration with same username
        pending_username_result = await db.execute(
            select(WorkerRegistrationRequest).where(
                func.lower(WorkerRegistrationRequest.username) == request.username.lower(),
                WorkerRegistrationRequest.status == RegistrationStatus.pending
            )
        )
        if pending_username_result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Username '{request.username}' already has a pending registration request"
            )

        # Check for pending registration with same email
        pending_email_result = await db.execute(
            select(WorkerRegistrationRequest).where(
                func.lower(WorkerRegistrationRequest.email) == request.email.lower(),
                WorkerRegistrationRequest.status == RegistrationStatus.pending
            )
        )
        if pending_email_result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Email '{request.email}' already has a pending registration request"
            )

        # Hash password
        hashed_password = hash_password(request.password)

        # Generate unique access code
        access_code = await generate_worker_access_code(db)

        # Create registration request
        registration_request = WorkerRegistrationRequest(
            username=request.username,
            email=request.email,
            hashed_password=hashed_password,
            access_code=access_code,
            status=RegistrationStatus.pending
        )

        db.add(registration_request)
        await db.commit()
        await db.refresh(registration_request)

        # Broadcast worker registration request via WebSocket
        try:
            request_data = {
                "request_id": str(registration_request.id),
                "username": registration_request.username,
                "email": registration_request.email,
                "access_code": registration_request.access_code,
                "status": "pending",
                "created_at": registration_request.created_at.isoformat()
            }
            await ws_manager.broadcast_worker_request_created(request_data)
        except HTTPException:
            raise
        except Exception as e:
            logger.warning(f"Failed to broadcast worker registration: {e}")

        logger.info(f"Worker registration request created: {request.username} with access code {access_code}")

        return WorkerRegisterResponse(
            message="Worker registration request submitted successfully. Awaiting admin approval.",
            access_code=access_code,
            status="pending"
        )

    except HTTPException:
        raise
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error creating worker registration request: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create worker registration request"
        )
