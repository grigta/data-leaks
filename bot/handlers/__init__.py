"""Handlers registration module."""
import logging
from aiogram import Dispatcher

from handlers.login_handler import register_login_handlers
from handlers.mode_handler import register_mode_handlers
from handlers.balance_handler import register_balance_handlers
from handlers.message_handler import register_message_handlers


logger = logging.getLogger(__name__)


def register_handlers(dp: Dispatcher) -> None:
    """Register all handlers.

    Args:
        dp: Dispatcher instance.
    """
    # Register handlers in correct order
    # 1. Login handler first (for /login command)
    register_login_handlers(dp)

    # 2. Mode handler second (for /mode command)
    register_mode_handlers(dp)

    # 3. Balance handler third (for /balance command)
    register_balance_handlers(dp)

    # 4. Message handler fourth (for mentions)
    register_message_handlers(dp)

    logger.info("All handlers registered successfully")
