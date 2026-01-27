"""
API Key authentication utilities for Enrichment API.
"""
import os
import secrets
from fastapi import Header, HTTPException, status


def get_valid_api_keys() -> set:
    """
    Load valid API keys from environment variable.

    Returns:
        Set of valid API keys
    """
    api_keys_str = os.getenv('ENRICHMENT_API_KEYS', '')
    if not api_keys_str:
        raise ValueError("ENRICHMENT_API_KEYS environment variable not set")

    return set(key.strip() for key in api_keys_str.split(',') if key.strip())


def validate_api_key(api_key: str) -> bool:
    """
    Validate API key using constant-time comparison.

    Args:
        api_key: API key to validate

    Returns:
        True if valid, False otherwise
    """
    valid_keys = get_valid_api_keys()

    # Use constant-time comparison to prevent timing attacks
    for valid_key in valid_keys:
        if secrets.compare_digest(api_key, valid_key):
            return True

    return False


async def get_api_key(x_api_key: str = Header(..., alias="X-API-Key")) -> str:
    """
    FastAPI dependency for API key authentication.

    Args:
        x_api_key: API key from X-API-Key header

    Returns:
        Valid API key

    Raises:
        HTTPException: If API key is invalid
    """
    if not validate_api_key(x_api_key):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key"
        )

    return x_api_key
