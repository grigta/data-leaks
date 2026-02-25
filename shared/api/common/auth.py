"""
Authentication utilities for JWT token management and password hashing.
"""
import os
import secrets
from datetime import datetime, timedelta
from typing import Optional
from decimal import Decimal
from passlib.context import CryptContext
from jose import jwt, JWTError
from fastapi import HTTPException, status
from pydantic import BaseModel, EmailStr, Field


# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT configuration
JWT_SECRET = os.getenv('JWT_SECRET', 'change_me_long_random_string_min_32_chars')
JWT_ALGORITHM = os.getenv('JWT_ALGORITHM', 'HS256')
JWT_EXPIRATION_HOURS = int(os.getenv('JWT_EXPIRATION_HOURS', '24'))


# Pydantic models
class TokenData(BaseModel):
    """Token payload data."""
    username: Optional[str] = None
    user_id: Optional[str] = None


class Token(BaseModel):
    """Token response model."""
    access_token: str
    token_type: str = "bearer"


class UserCreate(BaseModel):
    """User registration request model - simple registration without password."""
    pass


class UserLogin(BaseModel):
    """User login request model - login with access code."""
    access_code: str = Field(min_length=15, max_length=15)


class UserResponse(BaseModel):
    """User response model."""
    id: str
    username: str
    email: Optional[str] = None
    telegram: Optional[str] = None
    jabber: Optional[str] = None
    balance: float
    access_code: Optional[str] = None
    is_admin: Optional[bool] = False
    is_banned: Optional[bool] = False
    ban_reason: Optional[str] = None
    banned_at: Optional[datetime] = None
    instant_ssn_rules_accepted: Optional[bool] = False
    invitation_code: Optional[str] = None
    invited_by: Optional[str] = None
    invitation_bonus_received: Optional[bool] = False
    search_price: Optional[float] = None
    created_at: datetime

    class Config:
        from_attributes = True
        json_encoders = {
            Decimal: lambda v: float(v) if v is not None else None
        }


class AdminLoginRequest(BaseModel):
    """Admin login request model."""
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=8)


class AdminUserResponse(BaseModel):
    """Admin user response model."""
    id: str
    username: str
    email: str
    is_admin: bool
    totp_enabled: bool
    created_at: datetime

    class Config:
        from_attributes = True


# Access code utilities
def generate_access_code() -> str:
    """
    Generate a random 12-digit access code in format XXX-XXX-XXX-XXX.

    Returns:
        12-digit access code with dashes
    """
    # Generate 12 random digits
    digits = ''.join([str(secrets.randbelow(10)) for _ in range(12)])
    # Format as XXX-XXX-XXX-XXX
    return f"{digits[0:3]}-{digits[3:6]}-{digits[6:9]}-{digits[9:12]}"


# Password utilities
def hash_password(password: str) -> str:
    """
    Hash a password using bcrypt.

    Args:
        password: Plain text password

    Returns:
        Hashed password
    """
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a password against its hash.

    Args:
        plain_password: Plain text password
        hashed_password: Hashed password

    Returns:
        True if password matches, False otherwise
    """
    return pwd_context.verify(plain_password, hashed_password)


# JWT utilities
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a JWT access token.

    Args:
        data: Data to encode in token
        expires_delta: Token expiration time (default: 24 hours)

    Returns:
        Encoded JWT token
    """
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS)

    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)

    return encoded_jwt


def decode_access_token(token: str) -> dict:
    """
    Decode and validate a JWT access token.

    Args:
        token: JWT token to decode

    Returns:
        Token payload

    Raises:
        HTTPException: If token is invalid or expired
    """
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
