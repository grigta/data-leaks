"""
Worker API dependencies for authentication.
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from api.common.auth import decode_access_token
from api.common.database import get_postgres_session as get_db
from api.common.models_postgres import User


oauth2_scheme_worker = OAuth2PasswordBearer(tokenUrl="/auth/login")


async def _load_user_from_token(
    token: str,
    db: AsyncSession
) -> User:
    """Load user from JWT token."""
    try:
        payload = decode_access_token(token)
    except HTTPException:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )

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


async def get_current_worker_user(
    token: str = Depends(oauth2_scheme_worker),
    db: AsyncSession = Depends(get_db)
) -> User:
    """
    Get current worker user from JWT token.

    Checks:
    1. Token is valid and not expired
    2. User exists in database
    3. User has worker_role=True
    """
    user = await _load_user_from_token(token, db)

    if not user.worker_role:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Worker access required"
        )

    return user
