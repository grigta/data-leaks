"""
FastAPI dependencies for Public API.
"""
from fastapi import Depends, HTTPException, status, Request, WebSocket
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from api.common.database import get_postgres_session
from api.common.auth import decode_access_token
from api.common.models_postgres import User
from slowapi import Limiter
from slowapi.util import get_remote_address
from typing import Callable
import os


# OAuth2 scheme for JWT authentication
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_postgres_session)
) -> User:
    """
    FastAPI dependency to get current authenticated user.

    Args:
        token: JWT token from Authorization header
        db: PostgreSQL database session

    Returns:
        Current user

    Raises:
        HTTPException: If token is invalid or user not found
    """
    # Decode JWT token
    payload = decode_access_token(token)

    # Extract user_id from payload
    user_id = payload.get("user_id")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Load user from database
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


async def get_current_admin_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """
    FastAPI dependency to get current authenticated admin user.

    Args:
        current_user: Current authenticated user

    Returns:
        Current admin user

    Raises:
        HTTPException: If user is not an admin
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )

    return current_user


async def get_current_user_ws(
    websocket: WebSocket,
    db: AsyncSession = Depends(get_postgres_session)
) -> User:
    """
    FastAPI dependency to get current authenticated user from WebSocket.

    Args:
        websocket: WebSocket connection
        db: PostgreSQL database session

    Returns:
        Current user

    Raises:
        WebSocketException: If token is invalid or user not found
    """
    # Extract token from query parameters
    token = websocket.query_params.get("token")

    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Missing token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token"
        )

    # Decode JWT token
    try:
        payload = decode_access_token(token)
    except HTTPException:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token"
        )

    # Extract user_id from payload
    user_id = payload.get("user_id")
    if user_id is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid token payload")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials"
        )

    # Load user from database
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="User not found")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )

    return user


def get_user_id_for_rate_limit(request: Request) -> str:
    """
    Custom key function for rate limiting by user_id from JWT token.
    Falls back to IP address if no valid token is present.

    Args:
        request: FastAPI request object

    Returns:
        User ID or IP address as string identifier
    """
    try:
        # Try to extract token from Authorization header
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            payload = decode_access_token(token)
            user_id = payload.get("user_id")
            if user_id is not None:
                return f"user:{user_id}"
    except Exception:
        # If token is invalid or missing, fall back to IP
        pass

    # Fall back to IP address
    return get_remote_address(request)


# Create Limiter instance for rate limiting
# Use Redis storage if REDIS_URL is configured, otherwise fallback to in-memory
redis_url = os.getenv('REDIS_URL')
if redis_url:
    # Import redis storage only if needed
    from slowapi.util import get_remote_address
    from slowapi import Limiter
    from slowapi.middleware import SlowAPIMiddleware
    from limits.storage import RedisStorage

    storage_uri = redis_url
    limiter = Limiter(
        key_func=get_user_id_for_rate_limit,
        default_limits=["100/hour"],
        headers_enabled=True,
        storage_uri=storage_uri
    )
else:
    # Fallback to in-memory storage (only for development/testing)
    limiter = Limiter(
        key_func=get_user_id_for_rate_limit,
        default_limits=["100/hour"],
        headers_enabled=True
    )
