"""
Worker authentication router.
"""
import logging
import os
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.util import get_remote_address

from api.common.database import get_postgres_session as get_db
from api.common.models_postgres import User
from api.common.auth import create_access_token, Token
from api.worker.dependencies import get_current_worker_user

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Worker Authentication"])


def _get_client_ip(request: Request) -> str:
    """Extract real client IP from Cloudflare or proxy headers."""
    return (
        request.headers.get("cf-connecting-ip")
        or request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        or (request.client.host if request.client else "unknown")
    )


_redis_url = os.getenv("REDIS_URL", "")
if _redis_url:
    try:
        from slowapi import Limiter
        from limits.storage import RedisStorage
        worker_limiter = Limiter(key_func=_get_client_ip, storage_uri=_redis_url)
    except Exception:
        worker_limiter = Limiter(key_func=_get_client_ip)
else:
    worker_limiter = Limiter(key_func=_get_client_ip)


class WorkerUserResponse(BaseModel):
    """Worker user info response."""
    username: str
    email: str
    worker_role: bool
    wallet_address: Optional[str] = None
    wallet_network: Optional[str] = None


class AccessCodeLogin(BaseModel):
    """Login request with access code."""
    access_code: str


@router.post("/login", response_model=Token)
@worker_limiter.limit("5/minute")
async def worker_login(
    request: Request,
    body: AccessCodeLogin,
    db: AsyncSession = Depends(get_db)
):
    """
    Worker login endpoint.
    Authenticates by access code generated in admin panel.
    """
    result = await db.execute(
        select(User).where(User.access_code == body.access_code)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access code",
        )

    if not user.worker_role:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Worker access required",
        )

    if user.is_banned:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is banned",
        )

    token_data = {
        "sub": user.username,
        "user_id": str(user.id),
        "worker_role": user.worker_role
    }
    access_token = create_access_token(token_data)

    logger.info(f"Worker {user.username} logged in via access code")
    return Token(access_token=access_token, token_type="bearer")


@router.get("/me", response_model=WorkerUserResponse)
async def get_worker_me(
    current_user: User = Depends(get_current_worker_user)
):
    """Get current worker user information."""
    return WorkerUserResponse(
        username=current_user.username,
        email=current_user.email or "",
        worker_role=current_user.worker_role,
        wallet_address=current_user.wallet_address,
        wallet_network=current_user.wallet_network,
    )
