"""
FastAPI dependencies for Enrichment API.
"""
from database.data_manager import DataManager
from database.db_schema import DEFAULT_DB_PATH
from typing import Optional
import os
import logging


logger = logging.getLogger(__name__)


def get_data_manager() -> DataManager:
    """
    FastAPI dependency to get DataManager instance.

    Returns:
        DataManager instance
    """
    sqlite_path = os.getenv('SQLITE_PATH', DEFAULT_DB_PATH)
    return DataManager(db_path=sqlite_path)


def get_webhook_secret() -> Optional[str]:
    """
    Get webhook secret from environment variable.

    Returns:
        Webhook secret string or None if not configured

    Note:
        Returns None if WEBHOOK_SECRET is not set, which disables
        signature verification. This is useful for testing but should
        be enabled in production.
    """
    webhook_secret = os.getenv('WEBHOOK_SECRET')

    if not webhook_secret:
        logger.warning(
            "WEBHOOK_SECRET not configured - webhook signature verification disabled. "
            "This is OK for testing but should be enabled in production."
        )
        return None

    return webhook_secret
