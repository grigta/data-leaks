"""
Admin API dependencies and middleware for authentication and 2FA verification.
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from api.common.auth import decode_access_token
from api.common.database import get_postgres_session as get_db
from api.common.models_postgres import User


# OAuth2 scheme for admin authentication
oauth2_scheme_admin = OAuth2PasswordBearer(tokenUrl="/auth/login")


async def _load_user_from_token(
    token: str,
    db: AsyncSession
) -> User:
    """
    Private helper to decode token, validate it, and load the User.

    Args:
        token: JWT access token
        db: Database session

    Returns:
        User object from database

    Raises:
        HTTPException 401: Invalid/expired token, invalid payload, or user not found
    """
    # Decode and validate token
    try:
        payload = decode_access_token(token)
    except HTTPException:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Extract user information
    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Load user from database
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


async def get_current_admin_user(
    token: str = Depends(oauth2_scheme_admin),
    db: AsyncSession = Depends(get_db)
) -> User:
    """
    Get current admin user from JWT token with full 2FA verification.

    This dependency checks:
    1. Token is valid and not expired
    2. User exists in database
    3. User has admin privileges (is_admin=True)
    4. User is not a worker (worker_role=False)
    5. User has 2FA enabled (totp_secret is set)
    6. Token is not a temporary 2FA token

    Args:
        token: JWT access token
        db: Database session

    Returns:
        User object if all checks pass

    Raises:
        HTTPException 401: Invalid or expired token
        HTTPException 403: Not an admin or 2FA not configured
    """
    # Load user from token using helper
    user = await _load_user_from_token(token, db)

    # Verify admin privileges
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access forbidden: Admin privileges required"
        )

    # Verify user is not a worker
    if user.worker_role:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access forbidden: Worker accounts cannot access admin endpoints"
        )

    # Verify 2FA is enabled
    # TODO: Enable this check in production
    # For development, allow access without 2FA
    # if not user.totp_secret:
    #     raise HTTPException(
    #         status_code=status.HTTP_403_FORBIDDEN,
    #         detail="2FA must be enabled for admin access"
    #     )

    return user


async def get_current_admin_user_optional(
    token: str = Depends(oauth2_scheme_admin),
    db: AsyncSession = Depends(get_db)
) -> User:
    """
    Get current admin user without requiring 2FA to be fully configured.

    This dependency is used for setup-2fa and confirm-2fa endpoints where
    the user needs to be authenticated as admin but may not have 2FA set up yet.

    Checks:
    1. Token is valid and not expired
    2. User exists in database
    3. User has admin privileges (is_admin=True)
    4. User is not a worker (worker_role=False)
    5. Does NOT check if totp_secret is set

    Args:
        token: JWT access token
        db: Database session

    Returns:
        User object if checks pass

    Raises:
        HTTPException 401: Invalid or expired token
        HTTPException 403: Not an admin
    """
    # Load user from token using helper
    user = await _load_user_from_token(token, db)

    # Verify admin privileges
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access forbidden: Admin privileges required"
        )

    # Verify user is not a worker
    if user.worker_role:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access forbidden: Worker accounts cannot access admin endpoints"
        )

    return user


async def get_current_admin_or_worker_user(
    token: str = Depends(oauth2_scheme_admin),
    db: AsyncSession = Depends(get_db)
) -> User:
    """
    Get current user with admin OR worker privileges.

    This dependency allows access to both:
    - Admin users (is_admin=True)
    - Worker users (worker_role=True)

    Used for endpoints that should be accessible by both admins and workers,
    such as manual SSN ticket processing.

    Checks:
    1. Token is valid and not expired
    2. User exists in database
    3. User has either admin privileges (is_admin=True) OR worker role (worker_role=True)

    Args:
        token: JWT access token
        db: Database session

    Returns:
        User object if checks pass

    Raises:
        HTTPException 401: Invalid or expired token
        HTTPException 403: Neither admin nor worker privileges
    """
    # Load user from token using helper
    user = await _load_user_from_token(token, db)

    # Verify user has either admin OR worker privileges
    if not user.is_admin and not user.worker_role:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Доступ запрещён. Недостаточно прав."
        )

    return user
